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
    "occupation_time_fractions",
    "occupation_time_fractions_reference",
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


def occupation_time_fractions_reference(rate_matrix, window: float, n_samples: int,
                                        seed: int = 1) -> np.ndarray:
    """Return per-window state occupancies by direct Gillespie sampling.

    The readable definition of what :func:`occupation_time_fractions` computes,
    and its fallback where the simulation engine is too old to record a state
    trajectory. Each of ``n_samples`` windows is an independent trajectory whose
    starting state is drawn from the equilibrium populations, so the rows are
    independent draws from the occupation-time law.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)`` rates in Hz; see :func:`generator_from_rate_matrix`.
    window : float
        Observation time in seconds.
    n_samples : int
        Number of independent windows.
    seed : int
        Random seed. Fixed by callers so a fit objective stays deterministic.

    Returns
    -------
    numpy.ndarray
        ``(n_samples, n)`` whose rows sum to one.
    """
    matrix = np.array(rate_matrix, dtype=float)
    np.fill_diagonal(matrix, 0.0)
    matrix = np.clip(matrix, 0.0, None)
    n = matrix.shape[0]
    exit_rates = matrix.sum(axis=0)          # column sums: total rate out of each state
    populations = equilibrium_populations(matrix)

    rng = np.random.default_rng(int(seed))
    initial = rng.choice(n, size=int(n_samples), p=populations)
    out = np.zeros((int(n_samples), n), dtype=float)

    for w in range(int(n_samples)):
        state = int(initial[w])
        elapsed = 0.0
        while elapsed < window:
            rate = exit_rates[state]
            if rate <= 0.0:                  # absorbing: the rest of the window is this state
                out[w, state] += window - elapsed
                break
            dwell = rng.exponential(1.0 / rate)
            if elapsed + dwell >= window:
                out[w, state] += window - elapsed
                break
            out[w, state] += dwell
            elapsed += dwell
            state = int(rng.choice(n, p=matrix[:, state] / rate))

    totals = out.sum(axis=1, keepdims=True)
    totals[totals == 0.0] = 1.0
    return out / totals


def _engine_records_state_trajectory() -> bool:
    """Whether the installed simulation engine can record a state trajectory."""
    try:
        import tttrlib
    except ImportError:                                          # pragma: no cover
        return False
    engine = getattr(tttrlib, "SimEngine", None)
    return engine is not None and hasattr(engine, "set_state_log")


def occupation_time_fractions(rate_matrix, window: float, n_samples: int,
                              seed: int = 1) -> np.ndarray:
    """Return per-window state occupancies of an arbitrary kinetic scheme.

    The general answer where :func:`szabo_gopich_quadrature` is only a two-moment
    approximation: sample the state kinetics and measure how long each window
    actually spent in each state. Slow exchange — where the moment match cannot
    follow a multimodal distribution — is exactly where this is exact.

    Sampling is delegated to the photon simulator's kinetics, which evolves the
    same continuous-time Markov chain in C++ across threads and records the
    transitions rather than snapshots, so occupation times are exact. Each window
    is one immobile, non-emitting molecule started from the equilibrium
    populations, which makes the rows independent draws — the scheme
    :func:`occupation_time_fractions_reference` spells out, and falls back to
    when the installed engine predates the state log.

    The two agree distribution-for-distribution; the engine is roughly an order
    of magnitude faster once there is more than a handful of transitions per
    window (measured 8x at 6 per window, 13x at 60, on a three-state scheme),
    which is the regime where sampling is needed at all.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)`` rates in Hz; see :func:`generator_from_rate_matrix`.
    window : float
        Observation time in seconds.
    n_samples : int
        Number of independent windows.
    seed : int
        Random seed. Fixed by callers so a fit objective stays deterministic —
        an optimiser would otherwise chase sampling scatter.

    Returns
    -------
    numpy.ndarray
        ``(n_samples, n)`` whose rows sum to one.
    """
    n_samples = int(n_samples)
    if not _engine_records_state_trajectory():
        return occupation_time_fractions_reference(rate_matrix, window, n_samples, seed)

    import tttrlib

    matrix = np.array(rate_matrix, dtype=float)
    np.fill_diagonal(matrix, 0.0)
    matrix = np.clip(matrix, 0.0, None)
    n = matrix.shape[0]
    populations = equilibrium_populations(matrix)

    sample = tttrlib.SimSystem()
    for _ in range(n):
        species = tttrlib.SimSpecies()
        species.D = 0.0                                  # immobile: no diffusion to simulate
        species.q = tttrlib.VectorDouble([0.0])          # dark: we want the states, not photons
        sample.add_species(species)
    # The engine's rate matrices are row-major source -> target, the transpose of the
    # convention used here. Plain lists, not VectorDouble: a by-value std::vector argument
    # rejects the proxy once another SWIG extension has claimed the shared type table.
    sample.set_rate_matrices([0.0] * (n * n), [float(v) for v in matrix.T.ravel()])
    sample.set_background([0.0])
    sample.set_box(50.0, 50.0)                           # irrelevant: nothing moves or emits

    rng = np.random.default_rng(int(seed))
    for state in rng.choice(n, size=n_samples, p=populations):
        sample.add_fluorophore(0.0, 0.0, 0.0, int(state), False)

    settings = tttrlib.SimIntegrator()
    settings.dt = float(window)                          # one macro-window IS the observation
    settings.n_channels = 1
    settings.n_ph_max = 10 ** 15                         # stop on windows, never on photons
    settings.max_windows = 1
    settings.seed_diffusion = int(seed)
    settings.seed_emission = int(seed) + 1
    engine = tttrlib.SimEngine(
        sample,
        tttrlib.SimGrid.gaussian3d(0.3, 2.0, 4.0, 8.0, 0.2, 1.0),
        tttrlib.VectorSimGrid([]),
        settings,
    )
    engine.set_state_log(True)
    engine.run()

    _, fractions = engine.state_occupancy(windows_per_bin=1)
    return np.ascontiguousarray(fractions[:, 0, :])
