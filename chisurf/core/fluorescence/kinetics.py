r"""Time-averaged observables of a multistate Markov system.

A molecule that interconverts while it is being observed does not report its
instantaneous state — it reports a **time average** over the observation window.
Everything downstream (dynamic PDA, dynamic tcPDA) needs the distribution of
that average, and this module supplies it for an arbitrary number of states.

Two routes, with different costs and different exactness:

**Exact, two states** — :func:`two_state_occupation_quadrature` in
:mod:`chisurf.core.models.pda.dynamic` builds the full occupation-time
distribution. Only available for two states, where the problem has a closed
characteristic function.

**Szabo–Gopich, any number of states** — this module. Rather than the full
distribution it computes its first two **moments** exactly and matches a
distribution to them. That is the approximation Gopich and Szabo introduced for
multistate single-molecule FRET: the shape of the time-averaged distribution
matters much less than its mean and width once shot noise is convolved in, and
the moments are available in closed form for any rate matrix where the full
distribution is not.

The variance is the part that carries the physics:

.. math::

    \sigma^2_{\bar x}(T) = \frac{2}{T^2}\int_0^T (T-t)\, C(t)\, dt,
    \qquad
    C(t) = \sum_{ij} p_i\, \delta x_i \big(e^{Kt}\big)_{ij}\, \delta x_j,

with :math:`\delta x_i = x_i - \bar x`. Diagonalising :math:`K` turns
:math:`C(t)` into a sum of exponentials and the integral into a closed form,
:math:`\frac{2}{(\lambda T)^2}\big(e^{\lambda T} - 1 - \lambda T\big)` per mode.

That factor is the whole story of dynamic broadening:

- **slow** (:math:`|\lambda| T \ll 1`) it tends to 1, so the variance is the
  full static heterogeneity — the states are resolved as separate populations;
- **fast** (:math:`|\lambda| T \gg 1`) it falls off as :math:`2/|\lambda| T`,
  motional narrowing — the states average into one;
- in between the width is intermediate, which is exactly the regime dynamic
  PDA exists to measure.

Where it is good, and where it is not
-------------------------------------
The moments are exact; the *shape* matched to them is not. Measured against
exact Monte-Carlo sampling on a symmetric three-state system (total variation
of the resulting S1S2 matrix):

======  ======
k T     TV
======  ======
0.002   0.19
0.2     0.11
2       0.010
20      0.0012
======  ======

So it is good to about 1% from roughly two transitions per observation window
upward, and degrades as exchange slows. That is inherent, not a defect: with
slow exchange three well-separated states give a **trimodal** distribution of
the time average, and no two-parameter shape represents three peaks. It is also
not a practical limitation, because slow exchange means the states are resolved
and the right description is a *static* mixture — which a multi-species fit
models directly and exactly.

Reference: Gopich & Szabo, *FRET efficiency distributions of multistate single
molecules*, J. Phys. Chem. B (2010) — used as documented prior art and
reimplemented here, not copied.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "equilibrium_populations",
    "generator_from_rate_matrix",
    "szabo_gopich_quadrature",
    "time_averaged_moments",
]


def generator_from_rate_matrix(rate_matrix) -> np.ndarray:
    """Return the CTMC generator for a rate matrix.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)`` with ``rate_matrix[target, source]`` the ``source -> target``
        rate in Hz. The diagonal is ignored and rebuilt, so a matrix with
        arbitrary diagonal entries is accepted.

    Returns
    -------
    numpy.ndarray
        Generator ``Q`` with ``Q[target, source]`` off-diagonal rates and
        ``Q[i, i] = -sum_j Q[j, i]``, so each column sums to zero.
    """
    matrix = np.array(rate_matrix, dtype=float)
    np.fill_diagonal(matrix, 0.0)
    matrix = np.clip(matrix, 0.0, None)
    generator = matrix.copy()
    for i in range(matrix.shape[0]):
        generator[i, i] = -matrix[:, i].sum()
    return generator


def equilibrium_populations(rate_matrix) -> np.ndarray:
    """Return the steady-state populations of a rate matrix.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)``; see :func:`generator_from_rate_matrix` for the convention.

    Returns
    -------
    numpy.ndarray
        Populations summing to one. A system with no transitions at all falls
        back to a uniform distribution, which is the only defensible answer
        when every state is absorbing.
    """
    generator = generator_from_rate_matrix(rate_matrix)
    n = generator.shape[0]
    augmented = np.vstack([generator, np.ones(n)])
    target = np.zeros(n + 1)
    target[-1] = 1.0
    populations, *_ = np.linalg.lstsq(augmented, target, rcond=None)
    populations = np.clip(populations, 0.0, None)
    total = populations.sum()
    return populations / total if total > 0 else np.full(n, 1.0 / n)


def time_averaged_moments(rate_matrix, values, window: float):
    """Return the mean and variance of a state observable averaged over a window.

    Both are **exact** for any number of states — it is only the *shape* of the
    distribution that the Szabo–Gopich treatment approximates, never these.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)`` rates in Hz; see :func:`generator_from_rate_matrix`.
    values : array_like
        ``(n,)`` value of the observable in each state (a FRET efficiency, a
        per-photon channel probability, …).
    window : float
        Observation time in seconds.

    Returns
    -------
    mean : float
        Equilibrium average; independent of the window, since the process is
        stationary.
    variance : float
        Variance of the time average over the window. Equals the static
        (equilibrium) variance as ``window -> 0`` and falls to zero as
        ``window -> inf``.
    """
    generator = generator_from_rate_matrix(rate_matrix)
    populations = equilibrium_populations(rate_matrix)
    values = np.asarray(values, dtype=float).ravel()

    mean = float(populations @ values)
    deviation = values - mean
    window = float(max(window, 0.0))
    if window <= 0.0:
        return mean, float(populations @ deviation ** 2)

    eigenvalues, eigenvectors = np.linalg.eig(generator)
    try:
        inverse = np.linalg.inv(eigenvectors)
    except np.linalg.LinAlgError:  # pragma: no cover - defective generator
        return mean, float(populations @ deviation ** 2)

    # C(t) = sum_k amplitude_k exp(lambda_k t), from the spectral decomposition.
    # The generator acts on populations as dp/dt = Q p, so exp(Qt) propagates a
    # population column and the correlation function is
    #     C(t) = delta^T exp(Qt) (p * delta),
    # with the equilibrium weight on the *initial* state. exp(Qt) is not
    # symmetric, so the two placements are different numbers -- putting the
    # weight on the wrong side understates the variance by ~26% on a two-state
    # system, which the cross-check against the exact occupation law catches.
    left = deviation @ eigenvectors
    right = inverse @ (populations * deviation)
    amplitudes = left * right

    lam = eigenvalues * window
    with np.errstate(over="ignore", invalid="ignore"):
        # 2/(lam^2) * (e^lam - 1 - lam), continuous at lam = 0 where it is 1.
        factor = np.where(
            np.abs(lam) < 1e-8,
            1.0 + lam / 3.0,
            2.0 * (np.exp(np.clip(lam.real, -700.0, 0.0) + 1j * lam.imag) - 1.0 - lam)
            / np.where(np.abs(lam) < 1e-8, 1.0, lam ** 2),
        )
    variance = float(np.real(amplitudes @ factor))
    static = float(populations @ deviation ** 2)
    return mean, float(np.clip(variance, 0.0, static))


def szabo_gopich_quadrature(rate_matrix, values, window: float, n_nodes: int = 32,
                            lower: float = 0.0, upper: float = 1.0):
    """Return nodes and weights over a time-averaged, bounded observable.

    The Szabo–Gopich step: keep the exact mean and variance from
    :func:`time_averaged_moments` and match a **beta** distribution to them on
    ``[lower, upper]``.

    A beta rather than the Gaussian of the original treatment, for one
    practical reason: the observable here is a probability or an efficiency and
    genuinely lives on a bounded interval, and in the slow-exchange limit the
    distribution piles up against both ends. A Gaussian put there spills outside
    the interval and has to be clipped, which distorts exactly the limit where
    dynamic PDA is compared against a static fit. The beta reproduces both
    limits — two spikes at the ends when slow, a narrow peak at the mean when
    fast — with the same two moments.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)`` rates in Hz.
    values : array_like
        ``(n,)`` observable per state; must lie within ``[lower, upper]``.
    window : float
        Observation time in seconds.
    n_nodes : int
        Number of quadrature nodes.
    lower, upper : float
        Support of the observable.

    Returns
    -------
    nodes : numpy.ndarray
        Values of the time-averaged observable.
    weights : numpy.ndarray
        Normalised weights summing to one.
    """
    mean, variance = time_averaged_moments(rate_matrix, values, window)
    span = float(upper - lower)
    if span <= 0.0:
        return np.array([mean]), np.array([1.0])

    scaled_mean = (mean - lower) / span
    scaled_variance = variance / (span * span)
    ceiling = scaled_mean * (1.0 - scaled_mean)

    # No spread left: the states have averaged out, so a point mass is the
    # honest answer rather than a beta with runaway shape parameters.
    if scaled_variance <= 1e-12 or ceiling <= 1e-12:
        return np.array([mean]), np.array([1.0])

    # Moment matching. concentration -> 0 is the fully-separated limit (mass at
    # the ends), large concentration the averaged one.
    concentration = max(ceiling / min(scaled_variance, ceiling * (1.0 - 1e-9)) - 1.0, 1e-9)
    alpha = scaled_mean * concentration
    beta_shape = (1.0 - scaled_mean) * concentration

    from scipy.stats import beta as beta_dist

    # Mid-point rule on the quantile scale: it puts nodes where the mass is,
    # which matters because in the slow limit the density is two spikes.
    probabilities = (np.arange(n_nodes) + 0.5) / n_nodes
    nodes = beta_dist.ppf(probabilities, alpha, beta_shape)
    nodes = lower + span * np.clip(np.nan_to_num(nodes, nan=scaled_mean), 0.0, 1.0)
    weights = np.full(n_nodes, 1.0 / n_nodes)
    return nodes, weights
