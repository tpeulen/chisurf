r"""Burst-wise photon-partition likelihood for three-colour PDA (PRD-65).

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

It goes one step further than that. Write $u_c(b)$ as a burst-determined factor
times $p_c^{-b}$: the burst part and the model part separate, so summing over
the whole background box is a **matrix product** between a
$(\text{bursts} \times \text{box})$ array and a
$(\text{points} \times \text{box})$ one. That is what
:func:`burst_log_likelihood` does, and it is why the background costs the same
kind of operation as the zero-background term rather than a different one.

Two things fall out of writing it this way:

- the zero-background limit is the leading factor exactly, so the fast
  no-background path (:func:`log_multinomial_pmf`, one matrix product over all
  bursts and model points) and the background correction **compose** instead of
  being separate code paths;
- near the optimum every term is an $O(1)$ ratio rather than a factorial,
  because $F_c \approx N p_c$ makes $w_m u_c(b) \sim (F_c/(N p_c))^b$.

That last point has a sharp edge, and it is the reason
:func:`_channel_boxes` exists: **the series may not be truncated on Poisson tail
mass.** Where a channel collected far more photons than the model allows,
$F_c/(N p_c) \gg 1$ and the terms *grow* for many steps before the Poisson
factor turns them over — and there the background explanation is the entire
likelihood. Truncating on $\mathrm{Pois}(b; B_c)$ alone silently discards the
dominant terms and deforms the likelihood surface away from the optimum, which
is exactly the region a sampler or a support-plane scan explores.

:func:`burst_log_likelihood_reference` implements the nested sum directly and
:func:`background_series` is deliberately untruncated, so both stay independent
of the fast path's cutoff heuristic; see ``test/models/test_pda3c_likelihood.py``.

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
    "burst_log_likelihood_reference",
    "collapse_bursts",
    "log_background_correction",
    "log_multinomial_pmf",
]

#: Smallest probability mass left in a truncated Poisson background tail.
DEFAULT_TOLERANCE = 1e-12

#: Peak elements allowed in one background-factor chunk (~64 MB of doubles).
#: The burst chunk is derived from this and the box size, so a wide box shrinks
#: the chunk instead of exhausting memory.
_KERNEL_ELEMENT_BUDGET = 8_000_000


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
        otherwise.

    Returns
    -------
    numpy.ndarray
        Log probabilities, broadcast over the leading axes.
    """
    counts = np.asarray(counts, dtype=float)
    p = np.asarray(p, dtype=float)

    # 0 * log(0) is 0 here (an impossible channel that saw no photons). Take the
    # log of a floored p so the product never forms -inf * 0 (a nan), then put
    # the -inf back only where a photon actually landed in a p=0 channel.
    with np.errstate(divide="ignore"):
        log_p = np.log(np.where(p > 0.0, p, 1.0))
    term = counts * log_p
    term = np.where((p == 0.0) & (counts > 0.0), -np.inf, term)

    n = counts.sum(axis=-1)
    return gammaln(n + 1.0) - gammaln(counts + 1.0).sum(axis=-1) + term.sum(axis=-1)


#: Hard ceiling for :func:`_tail_cutoff`, so a pathological rate cannot spin.
_MAX_CUTOFF = 10_000


def _tail_cutoff(rate: float, tolerance: float) -> int:
    """Return the smallest ``k`` with Poisson survival ``P(X > k) <= tolerance``.

    ``scipy``'s inverse survival function returns ``nan`` once the tolerance
    drops below what it can resolve, so an explicit walk past the mode is kept
    as a fallback.
    """
    if rate <= 0.0:
        return 0
    k = poisson.isf(tolerance, rate)
    if np.isfinite(k):
        return max(int(k), 0)
    log_tol = np.log(max(tolerance, 1e-300))
    k = int(rate) + 1
    while k < _MAX_CUTOFF and poisson.logpmf(k, rate) > log_tol:
        k += 1
    return k


def _channel_boxes(counts, background, p, tolerance):
    """Return the per-channel background box sizes the GEMM path must cover.

    Truncating each channel's series on **Poisson tail mass alone is wrong**.
    The summand is ``Pois(b;B_c) * falling(F_c,b) / p_c**b``, and once the
    reciprocal falling factorial of the total is folded in it behaves like
    ``Pois(b; B_c) * (F_c / (N p_c))**b``. That ratio is ~1 near the optimum —
    which is why the naive cutoff looks fine on well-fitting data — but it blows
    up wherever a channel collected far more photons than the model allows, and
    there the *background* explanation is the whole likelihood. Truncating early
    then discards the dominant terms and distorts the likelihood surface exactly
    where a sampler or a support-plane scan needs it to be right.

    So the cutoff is taken at an **effective rate** ``B_c * max(F_c/(N p_c))``
    over the bursts and model points in play, capped at the largest count the
    channel actually saw (no burst can hold more background than photons).

    Parameters
    ----------
    counts : numpy.ndarray
        Per-burst photon counts, shape ``(n_bursts, K)``.
    background : numpy.ndarray
        Per-channel mean background counts, shape ``(K,)``.
    p : numpy.ndarray
        Channel probabilities, shape ``(n_points, K)``.
    tolerance : float
        Tail mass to discard per channel.

    Returns
    -------
    list of int
        Number of background terms to keep per channel (at least 1).
    """
    totals = np.maximum(counts.sum(axis=1), 1.0)
    boxes = []
    for c in range(counts.shape[1]):
        max_count = int(counts[:, c].max(initial=0))
        if background[c] <= 0.0 or max_count == 0:
            boxes.append(1)
            continue
        p_c = p[:, c]
        p_min = float(np.min(p_c[p_c > 0.0])) if np.any(p_c > 0.0) else 1.0
        ratio = float(np.max(counts[:, c] / totals)) / max(p_min, 1e-300)
        effective = float(background[c]) * max(ratio, 1.0)
        boxes.append(min(max_count, _tail_cutoff(effective, tolerance)) + 1)
    return boxes


def background_series(count: int, rate: float, p: float):
    """Return the per-channel series :math:`u(b)` of the factorisation, untruncated.

    ``u(b) = Pois(b; rate) * falling_factorial(count, b) / p**b`` for every
    ``b = 0 … count``. ``u(0) = 1`` always, so a channel with no background
    contributes the identity of the convolution.

    This backs the per-burst reference path and deliberately does **not**
    truncate: a reference that shares the fast path's cutoff heuristic cannot
    catch a mistake in it, and this one did not (see :func:`_channel_boxes`).
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
    """
    count = int(count)
    if rate <= 0.0 or count <= 0:
        return np.ones(1, dtype=float)

    b_max = count
    b = np.arange(b_max + 1, dtype=float)
    if p <= 0.0:
        # An impossible channel cannot hold signal, so every observed photon in
        # it is background; the series degenerates to that single term.
        out = np.zeros(b_max + 1, dtype=float)
        if b_max >= count:
            out[count] = poisson.pmf(count, rate)
        return out

    # log form throughout: falling_factorial(count, b) = count!/(count-b)!
    log_u = (
        poisson.logpmf(b, rate)
        + gammaln(count + 1.0)
        - gammaln(count - b + 1.0)
        - b * np.log(p)
    )
    # Normalise out u(0) = Pois(0; rate) so the series starts at 1 and the
    # discarded constant reappears in `log_background_correction`.
    return np.exp(log_u - log_u[0])


def log_background_correction(
        counts,
        background,
        p,
        photon_number_pmf=None,
) -> float:
    r"""Log of the factor by which background multiplies the zero-background term.

    Implements :math:`\log \sum_m w_m c_m` of the module docstring for one
    burst and one set of channel probabilities: ``c`` by convolving the
    per-channel :func:`background_series`, ``w`` from the falling factorial of
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
    c = np.ones(1, dtype=float)
    log_offset = 0.0
    for k in range(counts.size):
        u = background_series(int(counts[k]), float(background[k]), float(p[k]))
        # Pois(0; rate) was divided out of each series; put it back once.
        log_offset += -float(background[k])
        c = np.convolve(c, u)

    total = float(counts.sum())
    m = np.arange(c.size, dtype=float)
    keep = m <= total
    c = c[keep]
    m = m[keep]

    # w_m = P(N-m) (N-m)! / N!  — the reciprocal falling factorial of the total.
    log_w = gammaln(total - m + 1.0) - gammaln(total + 1.0)
    if photon_number_pmf is not None:
        pn = np.asarray(photon_number_pmf, dtype=float)
        n_signal = (total - m).astype(int)
        weights = np.where(n_signal < pn.size, pn[np.clip(n_signal, 0, pn.size - 1)], 0.0)
        with np.errstate(divide="ignore"):
            log_w = log_w + np.log(weights)

    terms = log_w + np.log(np.maximum(c, 0.0), where=c > 0.0, out=np.full(c.shape, -np.inf))
    finite = np.isfinite(terms)
    if not np.any(finite):
        return -np.inf
    peak = terms[finite].max()
    return float(log_offset + peak + np.log(np.exp(terms[finite] - peak).sum()))


def _background_factors(counts, background, photon_number_pmf, boxes):
    r"""Return the burst-only part of the background correction.

    Separates the correction's summand into a burst-determined factor and a
    model-determined one, which is what lets :func:`burst_log_likelihood`
    evaluate it as a matrix product. From the module docstring,

    .. math::

        \sum_m w_m c_m = \sum_{b} \Big[\prod_c \mathrm{Pois}(b_c;B_c)
        \tfrac{F_c!}{(F_c-b_c)!}\Big] w_{\sum_c b_c}
        \;\times\; \prod_c p_c^{-b_c},

    and the bracket together with :math:`w` depends only on the burst while
    :math:`\prod_c p_c^{-b_c}` depends only on the model point.

    Parameters
    ----------
    counts : numpy.ndarray
        Per-burst photon counts, shape ``(n_bursts, K)``.
    background : numpy.ndarray
        Per-channel mean background counts, shape ``(K,)``.
    photon_number_pmf : array_like or None
        ``P(n)`` for the signal photon number.
    boxes : sequence of int
        Number of background terms to keep per channel, from
        :func:`_channel_boxes`.

    Returns
    -------
    kernel : numpy.ndarray
        Shape ``(n_bursts, prod(boxes))`` — the burst factor over the flattened
        background box.
    exponents : numpy.ndarray
        Shape ``(prod(boxes), K)`` — the background counts each column stands
        for.
    """
    n_bursts, n_ch = counts.shape

    # a[j, c, b] = Pois(b; B_c) * falling_factorial(F_jc, b), padded to the
    # widest channel box; a burst that cannot supply b photons gets a zero.
    width = max(boxes)
    b = np.arange(width, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        log_a = (
            poisson.logpmf(b[None, None, :], background[None, :, None])
            + gammaln(counts[:, :, None] + 1.0)
            - gammaln(counts[:, :, None] - b[None, None, :] + 1.0)
        )
    log_a = np.where(b[None, None, :] <= counts[:, :, None], log_a, -np.inf)
    a = np.exp(log_a)
    a[~np.isfinite(a)] = 0.0

    # Outer product over channels -> the (b_1, ..., b_K) box, per burst.
    kernel = a[:, 0, : boxes[0]]
    for c in range(1, n_ch):
        slab = a[:, c, : boxes[c]].reshape((n_bursts,) + (1,) * c + (boxes[c],))
        kernel = kernel[..., None] * slab
    kernel = kernel.reshape(n_bursts, -1)

    # Exponent bookkeeping for the box, and its total m per column.
    grids = np.meshgrid(*[np.arange(n) for n in boxes], indexing="ij")
    exponents = np.stack([g.ravel() for g in grids], axis=1)
    m = exponents.sum(axis=1)

    # w_m = P(N - m) (N - m)! / N!, zero where the burst has fewer photons.
    total = counts.sum(axis=1)
    valid = m[None, :] <= total[:, None]
    with np.errstate(invalid="ignore"):
        log_w = gammaln(total[:, None] - m[None, :] + 1.0) - gammaln(total[:, None] + 1.0)
    w = np.where(valid, np.exp(np.where(valid, log_w, 0.0)), 0.0)

    if photon_number_pmf is not None:
        pn = np.asarray(photon_number_pmf, dtype=float)
        n_signal = (total[:, None] - m[None, :]).astype(int)
        in_range = valid & (n_signal < pn.size)
        w = w * np.where(in_range, pn[np.clip(n_signal, 0, pn.size - 1)], 0.0)

    return kernel * w, exponents


def burst_log_likelihood(
        counts,
        p,
        background=None,
        photon_number_pmf=None,
        tolerance: float = DEFAULT_TOLERANCE,
) -> np.ndarray:
    r"""Log likelihood of every burst under every set of channel probabilities.

    Both halves are matrix products. The zero-background term is
    :func:`log_multinomial_pmf` broadcast over the whole
    ``(model points × bursts)`` grid. The background correction separates the
    same way — the summand splits into a burst-determined factor and a
    :math:`\prod_c p_c^{-b_c}` that depends only on the model point (see
    :func:`_background_factors`) — so it is a second GEMM over the small
    background box rather than a sum evaluated per cell.

    Parameters
    ----------
    counts : array_like
        Per-burst photon counts, shape ``(n_bursts, K)``.
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
    """
    counts = np.atleast_2d(np.asarray(counts, dtype=float))
    p = np.atleast_2d(np.asarray(p, dtype=float))

    # The result is (points x bursts), but the broadcast that builds it is
    # (points x bursts x channels) and carries several temporaries of that size
    # inside log_multinomial_pmf. Chunk over bursts under the same element
    # budget as the background path: the peak then depends on the budget rather
    # than on the caller's point count, which is what a dynamic model varies
    # (occupancy nodes) without any sense of how much memory that asks for.
    out = np.empty((p.shape[0], counts.shape[0]), dtype=float)
    chunk = max(1, _KERNEL_ELEMENT_BUDGET // max(p.shape[0] * p.shape[1], 1))
    for start in range(0, counts.shape[0], chunk):
        stop = min(start + chunk, counts.shape[0])
        out[:, start:stop] = log_multinomial_pmf(
            counts[None, start:stop, :], p[:, None, :]
        )

    if background is None:
        background = np.zeros(counts.shape[1], dtype=float)
    background = np.asarray(background, dtype=float)

    if not np.any(background > 0.0) and photon_number_pmf is None:
        return out

    if np.any(p <= 0.0):
        # p^-b is undefined; that channel's photons must all be background. Rare
        # and cheap enough to hand to the per-burst reference path.
        for i in range(p.shape[0]):
            for j in range(counts.shape[0]):
                out[i, j] += log_background_correction(
                    counts[j], background, p[i], photon_number_pmf
                )
        return out

    boxes = _channel_boxes(counts, background, p, tolerance)
    # model[i, col] = prod_c p[i, c] ** -exponents[col, c]; built once, since the
    # box is fixed for the whole call.
    _, exponents = _background_factors(counts[:1], background, photon_number_pmf, boxes)
    model = np.exp(-(np.log(p) @ exponents.T))

    # The burst factor is (n_bursts x prod(boxes)) and the box grows as the K-th
    # power of the cutoff, so chunk under a fixed element budget rather than a
    # fixed burst count — one of the two places this can exhaust memory (the
    # other is the multinomial broadcast above, chunked the same way).
    chunk = max(1, _KERNEL_ELEMENT_BUDGET // max(exponents.shape[0], 1))
    correction = np.empty(out.shape, dtype=float)
    for start in range(0, counts.shape[0], chunk):
        stop = min(start + chunk, counts.shape[0])
        kernel, _ = _background_factors(
            counts[start:stop], background, photon_number_pmf, boxes
        )
        correction[:, start:stop] = model @ kernel.T

    with np.errstate(divide="ignore"):
        out = out + np.log(correction)
    return out


def burst_log_likelihood_reference(
        counts,
        p,
        background=None,
        photon_number_pmf=None,
) -> np.ndarray:
    """Nested-sum reference implementation, for testing the fast path.

    Evaluates the definition literally — a full sum over every channel's
    background count, with no truncation and no factorisation. Exponential in
    the number of channels and only usable on small inputs; it exists so
    :func:`burst_log_likelihood` has something independent to be wrong against.

    Parameters
    ----------
    counts : array_like
        Per-burst photon counts, shape ``(n_bursts, K)``.
    p : array_like
        Channel probabilities, shape ``(n_points, K)``.
    background : array_like, optional
        Per-channel mean background counts.
    photon_number_pmf : array_like, optional
        ``P(n)`` for the signal photon number.

    Returns
    -------
    numpy.ndarray
        Shape ``(n_points, n_bursts)``.
    """
    import itertools

    counts = np.atleast_2d(np.asarray(counts, dtype=int))
    p = np.atleast_2d(np.asarray(p, dtype=float))
    n_ch = counts.shape[1]
    if background is None:
        background = np.zeros(n_ch, dtype=float)
    background = np.asarray(background, dtype=float)

    out = np.full((p.shape[0], counts.shape[0]), -np.inf, dtype=float)
    for j, f in enumerate(counts):
        ranges = [range(int(fc) + 1) for fc in f]
        for i, pi in enumerate(p):
            total = 0.0
            for b in itertools.product(*ranges):
                b = np.asarray(b, dtype=int)
                signal = f - b
                n = int(signal.sum())
                if photon_number_pmf is not None:
                    pn = np.asarray(photon_number_pmf, dtype=float)
                    weight = pn[n] if n < pn.size else 0.0
                    if weight <= 0.0:
                        continue
                else:
                    weight = 1.0
                log_bg = float(poisson.logpmf(b, background).sum())
                total += weight * np.exp(log_bg + log_multinomial_pmf(signal, pi))
            out[i, j] = np.log(total) if total > 0.0 else -np.inf
    return out


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
