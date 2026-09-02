r"""Burst-wise photon-partition likelihood for three-colour PDA.

The observable is a burst's photon counts split across detection channels. For
a molecule with fixed transfer efficiencies the *signal* photons partition
**multinomially** — trinomially for the three channels open under blue
excitation, binomially for the two open under green excitation — and each
channel additionally collects uncorrelated **Poisson background**. This module
evaluates that convolution.

Writing $F$ for the observed counts, $b$ for the (unobserved) background counts
within them, $N=\sum_c F_c$ and $n=N-\sum_c b_c$ for the signal photon number,

.. math::

    L(F \mid p, B) = \sum_{b \le F}
        \Big[\prod_c \mathrm{Pois}(b_c; B_c)\Big]\,
        P(n)\; \mathrm{Multinom}(F - b;\, p).

Evaluated literally this is a nested sum over every channel's background count —
which is what the incumbent implementation does, and why it needs threaded C and
a GPU kernel. It does not have to be evaluated literally.

Factorisation
-------------
Only one thing couples the channels: the multinomial's leading $n!$, which
depends on the *total* background count $m=\sum_c b_c$ and not on how it is
distributed. Dividing through by the zero-background term
$\mathrm{Multinom}(F; p)$ and grouping by $m$,

.. math::

    L(F \mid p, B) = \mathrm{Multinom}(F;p) \sum_m w_m\, c_m,
    \qquad
    w_m = \frac{P(N-m)\,(N-m)!}{N!},
    \qquad
    c_m = \!\!\sum_{\sum_c b_c = m}\; \prod_c u_c(b_c),

with the per-channel series

.. math::

    u_c(b) = \mathrm{Pois}(b; B_c)\,\frac{F_c!}{(F_c-b)!}\, p_c^{-b}.

$c_m$ is the $m$-th coefficient of the product of the per-channel polynomials —
i.e. the **discrete convolution** of the $u_c$ sequences, which is how
:func:`log_background_correction` evaluates one burst.

Where the evaluation lives
--------------------------
:func:`burst_log_likelihood` is a thin adapter over
``tttrlib.PdaBurstLikelihood``, which carries the factorisation above in C++.
The NumPy implementation that used to live here — the background box, its GEMM
and its chunking — was removed once tttrlib matched it: it was 14-920x slower,
and it returned ``-inf`` where a channel has $p_c = 0$ but collected photons,
because the leading $\mathrm{Multinom}(F;p)$ is then zero and no finite
correction recovers the (perfectly possible) all-background answer. tttrlib
evaluates such bursts without factoring that term out, and agrees with
``_burst_log_likelihood_reference`` — the nested sum written out, frozen in
``test/models/test_pda3c_likelihood.py``. It has no production caller and is
only ever a test's oracle, so it lives beside the tests it checks rather than
beside the forwarder.

tttrlib also does not form the box at all: grouping by $m$ makes the
coefficients the convolution above, which is $O(K b m_{max})$ rather than
$O(\prod_c b_c)$ and needs no chunking.

What is still evaluated here
----------------------------
Only things tttrlib does not provide in the same shape:

- :func:`log_multinomial_pmf` — broadcasting, so a caller gets the whole
  (points × bursts) grid from one matrix product;
- :func:`log_background_correction`, :func:`background_series` and
  :func:`log_background_series` — the untruncated per-burst path, deliberately
  sharing no cutoff heuristic with the fast one;
- :func:`collapse_bursts` — data munging.

**The series may not be truncated on Poisson tail mass.** Where a channel
collected far more photons than the model allows, $F_c/(N p_c) \gg 1$ and the
terms *grow* for many steps before the Poisson factor turns them over — and
there the background explanation is the entire likelihood. Truncating on
$\mathrm{Pois}(b; B_c)$ alone silently discards the dominant terms and deforms
the likelihood surface away from the optimum, which is exactly the region a
sampler or a support-plane scan explores. tttrlib cuts at an effective rate
instead; see ``test/models/test_pda3c_likelihood.py``.

Conventions
-----------
``photon_number_pmf`` ($P(n)$ above) is optional. Supplied, the result is a
proper normalised distribution over count vectors and sums to one — this is what
the two-colour reduction test checks against the engine. Omitted, $P$ is taken
flat, which is the incumbent's convention: it conditions on the observed burst
size and drops a factor that is *almost* independent of the model.
"""

from __future__ import annotations

import numpy as np
from scipy.special import gammaln
from scipy.stats import poisson

__all__ = [
    "background_series",
    "burst_log_likelihood",
    "collapse_bursts",
    "log_background_correction",
    "log_background_series",
    "log_multinomial_pmf",
]

#: Smallest probability mass left in a truncated Poisson background tail.
DEFAULT_TOLERANCE = 1e-12


def log_multinomial_pmf(counts, p) -> np.ndarray:
    """Log multinomial probability of ``counts`` under channel probabilities ``p``.

    The zero-background term of the burst likelihood, and on its own the whole
    likelihood when the background is negligible. Broadcasting is the point:
    with ``counts`` of shape ``(n_bursts, K)`` and ``p`` of shape
    ``(n_points, K)`` the caller gets the full ``(n_points, n_bursts)`` grid
    from one matrix product.

    Parameters
    ----------
    counts : array_like
        Per-channel photon counts, shape ``(..., K)``.
    p : array_like
        Per-channel probabilities, shape ``(..., K)``; each row should sum to
        one. A zero probability is allowed as long as the matching count is
        zero (an impossible channel that saw nothing), and yields ``-inf``
        otherwise. A row carrying a **negative** entry is not a probability
        vector at all and yields ``-inf`` whatever the counts.

    Returns
    -------
    numpy.ndarray
        Log probabilities, broadcast over the leading axes.
    """
    counts = np.asarray(counts, dtype=float)
    p = np.asarray(p, dtype=float)

    # A negative entry would be floored to 1 below and so score its photons for
    # free (count * log 1 = 0), which can push the "log probability" above zero
    # and make an unphysical model point outscore every valid one. Reject the
    # whole row: with one entry negative the remaining channels no longer sum
    # to one either, so nothing about the row is a multinomial.
    invalid = np.any(p < 0.0, axis=-1)

    # 0 * log(0) is 0 here (an impossible channel that saw no photons). Take the
    # log of a floored p so the product never forms -inf * 0 (a nan), then put
    # the -inf back only where a photon actually landed in a p=0 channel.
    with np.errstate(divide="ignore"):
        log_p = np.log(np.where(p > 0.0, p, 1.0))
    term = counts * log_p
    term = np.where((p <= 0.0) & (counts > 0.0), -np.inf, term)

    n = counts.sum(axis=-1)
    out = gammaln(n + 1.0) - gammaln(counts + 1.0).sum(axis=-1) + term.sum(axis=-1)
    if np.any(invalid):
        out = np.where(invalid, -np.inf, out)
    return out


def log_background_series(count: int, rate: float, p: float):
    r"""Return :math:`\log u(b)`, the per-channel series of the factorisation.

    The log form is the primitive one: where a channel collected far more
    photons than the model allows, the terms grow like ``(F/(N p))**b`` and the
    linear series overflows to ``inf`` — on exactly the *dominant* terms, since
    the growth is what makes them dominant. Staying in logs keeps that regime
    representable; :func:`background_series` is the linear view of the same
    numbers.

    Parameters
    ----------
    count : int
        Observed photons in this channel.
    rate : float
        Mean background photons in this channel.
    p : float
        Channel probability under the multinomial; must be positive when
        ``count`` is.

    Returns
    -------
    numpy.ndarray
        ``log u(b)`` for ``b = 0 … count``, normalised so ``log u(0) = 0``.
        Terms that are exactly zero are ``-inf``.
    """
    count = int(count)
    if rate <= 0.0 or count <= 0:
        return np.zeros(1, dtype=float)

    b = np.arange(count + 1, dtype=float)
    if p <= 0.0:
        # An impossible channel cannot hold signal, so every observed photon in
        # it is background; the series degenerates to that single term.
        out = np.full(count + 1, -np.inf)
        out[count] = poisson.logpmf(count, rate)
        return out

    # falling_factorial(count, b) = count!/(count-b)!
    log_u = (
        poisson.logpmf(b, rate)
        + gammaln(count + 1.0)
        - gammaln(count - b + 1.0)
        - b * np.log(p)
    )
    # Normalise out u(0) = Pois(0; rate) so the series starts at 1 and the
    # discarded constant reappears in `log_background_correction`.
    return log_u - log_u[0]


def background_series(count: int, rate: float, p: float):
    """Return the per-channel series :math:`u(b)` of the factorisation, untruncated.

    ``u(b) = Pois(b; rate) * falling_factorial(count, b) / p**b`` for every
    ``b = 0 … count``. ``u(0) = 1`` always, so a channel with no background
    contributes the identity of the convolution.

    This backs the per-burst reference path and deliberately does **not**
    truncate: a reference that shares the fast path's cutoff heuristic cannot
    catch a mistake in it, and this one did not. (The cutoff now lives in
    tttrlib, which is a second reason to keep this side of it independent.)
    Summing to ``count`` is exact and cheap enough for one burst at a time.

    Parameters
    ----------
    count : int
        Observed photons in this channel.
    rate : float
        Mean background photons in this channel.
    p : float
        Channel probability under the multinomial; must be positive when
        ``count`` is.

    Returns
    -------
    numpy.ndarray
        The series, indexed by background count.

    Notes
    -----
    This is a *view* of :func:`log_background_series` and overflows to ``inf``
    wherever that one exceeds ``log(np.finfo(float).max)`` — which happens on
    the dominant terms of a channel the model calls nearly impossible. Consumers
    that sum the series must work from the log form.
    """
    return np.exp(log_background_series(count, rate, p))


def _log_convolve(log_a, log_b):
    """Discrete convolution of two non-negative sequences, in log space.

    ``exp(_log_convolve(log(a), log(b))) == convolve(a, b)`` up to rounding,
    without ever forming ``a`` or ``b`` themselves.

    Parameters
    ----------
    log_a, log_b : numpy.ndarray
        Logarithms of the two sequences; ``-inf`` marks an exactly zero term.

    Returns
    -------
    numpy.ndarray
        Logarithm of the convolution, of length ``log_a.size + log_b.size - 1``.
    """
    out = np.full(log_a.size + log_b.size - 1, -np.inf)
    for i, term in enumerate(log_a):
        if term == -np.inf:
            continue
        window = slice(i, i + log_b.size)
        out[window] = np.logaddexp(out[window], term + log_b)
    return out


def log_background_correction(
        counts,
        background,
        p,
        photon_number_pmf=None,
) -> float:
    r"""Log of the factor by which background multiplies the zero-background term.

    Implements :math:`\log \sum_m w_m c_m` of the module docstring for one
    burst and one set of channel probabilities: ``c`` by convolving the
    per-channel :func:`log_background_series`, ``w`` from the falling factorial of
    the observed total (times the photon-number distribution when given).

    Parameters
    ----------
    counts : array_like
        Per-channel photon counts of one burst, shape ``(K,)``.
    background : array_like
        Per-channel mean background counts, shape ``(K,)``.
    p : array_like
        Per-channel probabilities, shape ``(K,)``.
    photon_number_pmf : array_like, optional
        ``P(n)`` for the *signal* photon number. Omitted, ``P`` is flat.
    tolerance : float
        Poisson tail mass to discard per channel.

    Returns
    -------
    float
        The log correction; ``0.0`` when every background rate is zero and no
        photon-number distribution is supplied.
    """
    counts = np.asarray(counts, dtype=float)
    background = np.asarray(background, dtype=float)
    p = np.asarray(p, dtype=float)

    # c = convolution of the per-channel series, each normalised to start at 1.
    # Convolved in log space: the series is unbounded above (see
    # `log_background_series`) and its dominant terms overflow a float64.
    log_c = np.zeros(1, dtype=float)
    log_offset = 0.0
    for k in range(counts.size):
        log_u = log_background_series(int(counts[k]), float(background[k]), float(p[k]))
        # Pois(0; rate) was divided out of each series; put it back once.
        log_offset += -float(background[k])
        log_c = _log_convolve(log_c, log_u)

    total = float(counts.sum())
    m = np.arange(log_c.size, dtype=float)
    keep = m <= total
    log_c = log_c[keep]
    m = m[keep]

    # w_m = P(N-m) (N-m)! / N!  — the reciprocal falling factorial of the total.
    log_w = gammaln(total - m + 1.0) - gammaln(total + 1.0)
    if photon_number_pmf is not None:
        pn = np.asarray(photon_number_pmf, dtype=float)
        n_signal = (total - m).astype(int)
        weights = np.where(n_signal < pn.size, pn[np.clip(n_signal, 0, pn.size - 1)], 0.0)
        with np.errstate(divide="ignore"):
            log_w = log_w + np.log(weights)

    # Only exactly-zero terms are dropped. A `+inf` must *not* be masked away
    # here — it would silently return a finite sum over the sub-dominant tail.
    terms = log_w + log_c
    kept = ~np.isneginf(terms)
    if not np.any(kept):
        return -np.inf
    peak = terms[kept].max()
    return float(log_offset + peak + np.log(np.exp(terms[kept] - peak).sum()))



#: tttrlib's PdaBurstLikelihood, keyed on the burst-side inputs. The constructor
#: precomputes everything that does not depend on the model point -- the falling
#: factorials, the Poisson series, the multinomial constant -- and a fit calls
#: this with the same bursts and a new `p` on every iteration, so the object has
#: to outlive the call for that precompute to be worth anything.
_LIKELIHOOD_CACHE: dict = {}
_LIKELIHOOD_CACHE_MAX = 8


def _tttrlib_likelihood(counts, background, photon_number_pmf, tolerance):
    """Return a cached tttrlib evaluator for these bursts."""
    try:
        import tttrlib
    except ImportError as exc:                            # pragma: no cover
        raise ImportError(
            "PDA3c requires tttrlib. The NumPy implementation it used to fall "
            "back to was removed once tttrlib carried the same factorisation."
        ) from exc
    if not hasattr(tttrlib, "PdaBurstLikelihood"):        # pragma: no cover
        raise ImportError(
            "PDA3c requires a tttrlib with PdaBurstLikelihood; the installed "
            f"tttrlib {getattr(tttrlib, '__version__', '?')} predates it."
        )
    counts = np.asarray(counts)
    if not np.all(np.isfinite(counts)) or np.any(counts < 0):
        raise ValueError("photon counts must be finite and non-negative")
    if np.any(counts != np.rint(counts)):
        raise ValueError("photon counts must be integral")
    ci = np.ascontiguousarray(np.rint(counts), dtype=np.int32)
    bg = None if background is None else np.asarray(background, dtype=float)
    pn = None if photon_number_pmf is None else np.asarray(photon_number_pmf, dtype=float)

    key = (
        ci.shape, ci.tobytes(),
        None if bg is None else bg.tobytes(),
        None if pn is None else pn.tobytes(),
        float(tolerance),
    )
    obj = _LIKELIHOOD_CACHE.get(key)
    if obj is None:
        obj = tttrlib.PdaBurstLikelihood(
            ci,
            [] if bg is None else list(bg),
            [] if pn is None else list(pn),
            float(tolerance),
        )
        if len(_LIKELIHOOD_CACHE) >= _LIKELIHOOD_CACHE_MAX:
            _LIKELIHOOD_CACHE.clear()
        _LIKELIHOOD_CACHE[key] = obj
    return obj


def burst_log_likelihood(
        counts,
        p,
        background=None,
        photon_number_pmf=None,
        tolerance: float = DEFAULT_TOLERANCE,
) -> np.ndarray:
    r"""Log likelihood of every burst under every set of channel probabilities.

    Evaluated by ``tttrlib.PdaBurstLikelihood``. The burst-side tables live on
    that object and survive between calls, so a fit pays for them once.

    Parameters
    ----------
    counts : array_like
        Per-burst photon counts, shape ``(n_bursts, K)``. Must be integral.
    p : array_like
        Channel probabilities, shape ``(n_points, K)`` (or ``(K,)`` for one).
    background : array_like, optional
        Per-channel mean background counts, shape ``(K,)``. ``None`` or all
        zeros takes the fast path.
    photon_number_pmf : array_like, optional
        ``P(n)`` for the signal photon number; see the module docstring.
    tolerance : float
        Poisson tail mass to discard per channel.

    Returns
    -------
    numpy.ndarray
        Shape ``(n_points, n_bursts)``.

    Raises
    ------
    ImportError
        If tttrlib is missing or predates ``PdaBurstLikelihood``.
    """
    counts = np.atleast_2d(np.asarray(counts, dtype=float))
    p = np.atleast_2d(np.asarray(p, dtype=float))
    obj = _tttrlib_likelihood(counts, background, photon_number_pmf, tolerance)
    return obj.log_likelihood_grid(np.ascontiguousarray(p, dtype=float))


def collapse_bursts(counts):
    """Group bursts that share a count vector, since they share a likelihood.

    The likelihood depends on a burst only through its counts, so evaluating
    once per *distinct* count vector and weighting by multiplicity is exact and
    strictly cheaper. The saving grows with the dataset: burst counts are
    bounded by the photon budget, so the number of distinct vectors saturates
    while the burst count does not.

    Parameters
    ----------
    counts : array_like
        Per-burst photon counts, shape ``(n_bursts, K)``.

    Returns
    -------
    unique : numpy.ndarray
        Distinct count vectors, shape ``(n_unique, K)``.
    multiplicity : numpy.ndarray
        How many bursts carry each, shape ``(n_unique,)``.
    """
    counts = np.atleast_2d(np.asarray(counts))
    unique, multiplicity = np.unique(counts, axis=0, return_counts=True)
    return unique, multiplicity
