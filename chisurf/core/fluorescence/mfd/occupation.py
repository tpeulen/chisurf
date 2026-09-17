"""How long a burst spent in each state, as a distribution rather than a sample.

Given a state path, the channel counts and the micro times of a burst depend on
that path **only** through the vector of occupation-time fractions ``f`` — how much
of the burst was spent in each state, with ``Σf = 1``. That is exact, not an
approximation: ``f`` is the path's sufficient statistic for the histogram and
pooled-decay sources. So the kinetics enters the forward model as one object,
``P(f | T, K)``, and nothing else about the path matters.

It is computed **deterministically**, by propagating the joint distribution over
(state, occupation counts) with a transfer matrix. The alternative — sampling paths
— puts Monte-Carlo noise into the objective, and an optimizer will chase that noise
rather than the data. The cost is ``~ n · n^(M−1) · M²``: trivial for two states,
comfortable for three, and for four or more the sampled route in
:func:`chisurf.core.fluorescence.kinetics.occupation_time_fractions` remains the
fallback.

The rate matrix is the shared one, ``K[target, source]``
(:mod:`chisurf.core.fluorescence.kinetics`), never a private copy with its own
transposition convention.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.linalg import expm

from chisurf.core.fluorescence.kinetics import (
    equilibrium_populations,
    generator_from_rate_matrix,
)

__all__ = [
    "OccupationGrid",
    "occupation_time_distribution",
    "recommended_steps",
    "two_state_occupation_variance",
    "photon_weighted_occupation_variance",
    "effective_window",
    "photon_weighted_occupation_variances",
    "effective_window_scale",
    "relaxation_rate",
]

#: Transfer-matrix slices per expected transition. The discretization's error is
#: that a transition can only happen at a slice boundary, so what has to be resolved
#: is not the window but the *exchange within* it: a burst with 300 transitions
#: needs far more slices than one with three, and the same fixed ``n`` cannot serve
#: both — which matters because a fit loop moves the rates.
_STEPS_PER_TRANSITION = 4

#: Ceiling on the discretization. Past it the distribution has collapsed onto the
#: equilibrium average anyway, so the residual error is on a spread that is already
#: negligible next to the shot noise it sits inside.
_MAX_STEPS = 512

#: Floor, so that a nearly static scheme still has a grid to put weight on.
_MIN_STEPS = 16

#: Weights below this are dropped from the grid. The propagator spreads a little
#: probability into every reachable count, and carrying tens of thousands of nodes
#: with weight 1e-30 makes every downstream loop slower for no accuracy at all.
_PRUNE = 1e-10


@dataclass
class OccupationGrid:
    """A discrete approximation of ``P(f | T, K)``.

    Attributes
    ----------
    fractions : numpy.ndarray
        ``(n_nodes, n_states)`` occupation-time fractions; each row sums to one.
    weights : numpy.ndarray
        ``(n_nodes,)`` probabilities, summing to one.
    window : float
        The observation window this was computed for, seconds.
    n_steps : int
        Transfer-matrix discretization. Occupation fractions are multiples of
        ``1/n_steps``, so this is the resolution of the grid as well as its
        accuracy — convergence in it is a test, not an assumption.
    """

    fractions: np.ndarray
    weights: np.ndarray
    window: float
    n_steps: int

    def __len__(self) -> int:
        """Return the number of grid nodes."""
        return int(self.weights.size)

    def coarsen(self, n_nodes: int = 16) -> OccupationGrid:
        """Return the grid rebinned onto at most *n_nodes* occupation fractions.

        The propagator's resolution is ``1/n_steps``, which for fast exchange runs
        to several hundred nodes — and every node costs a pass through the nested
        background sum. Rebinning trades a resolution the histogram cannot see
        anyway for a cost it very much can: the fit is otherwise two orders of
        magnitude slower for a kinetic model than a static one.

        The rebinning preserves the total weight exactly and each occupied bin's
        *weighted mean* fraction, so the first moment of the occupation law — which
        is what sets the cloud's position — is unchanged. The second moment is
        slightly narrowed, which is why the default is generous.

        Parameters
        ----------
        n_nodes : int
            Target number of nodes along each of the first ``n_states - 1`` axes.

        Returns
        -------
        OccupationGrid
        """
        n_states = self.fractions.shape[1]
        if len(self) <= n_nodes or n_states != 2:
            return self
        edges = np.linspace(0.0, 1.0, int(n_nodes) + 1)
        index = np.clip(np.digitize(self.fractions[:, 0], edges[1:-1]), 0, n_nodes - 1)
        weights = np.bincount(index, weights=self.weights, minlength=n_nodes)
        centres = np.bincount(index, weights=self.weights * self.fractions[:, 0], minlength=n_nodes)
        occupied = weights > 0
        first = centres[occupied] / weights[occupied]
        fractions = np.column_stack([first, 1.0 - first])
        return OccupationGrid(
            fractions=fractions,
            weights=weights[occupied] / weights[occupied].sum(),
            window=self.window,
            n_steps=self.n_steps,
        )

    def average(self, values) -> float:
        """Return the mean of a per-state observable, time-averaged then ensemble-averaged.

        Parameters
        ----------
        values : array_like
            ``(n_states,)`` value of the observable in each state.

        Returns
        -------
        float
        """
        return float(self.weights @ (self.fractions @ np.asarray(values, dtype=float)))

    def variance(self, values) -> float:
        """Return the variance across bursts of a time-averaged observable.

        Parameters
        ----------
        values : array_like
            ``(n_states,)`` value of the observable in each state.

        Returns
        -------
        float
        """
        averaged = self.fractions @ np.asarray(values, dtype=float)
        mean = float(self.weights @ averaged)
        return float(self.weights @ (averaged - mean) ** 2)


def recommended_steps(rate_matrix, window: float, n_states: int | None = None) -> int:
    """Return a discretization that resolves the exchange inside the window.

    A transfer matrix can only place a transition at a slice boundary, so what has
    to be resolved is the number of transitions a burst actually makes — not the
    window. With a fixed ``n``, a scheme exchanging 300 times per burst comes out
    with a spread ~50% too wide while one exchanging three times is exact, and a fit
    loop visits both.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)`` rates in Hz, ``K[target, source]``.
    window : float
        Observation window, seconds.
    n_states : int, optional
        Used to lower the ceiling for three-state schemes, whose grid grows as
        ``n²``. Taken from the matrix when omitted.

    Returns
    -------
    int
    """
    matrix = np.array(rate_matrix, dtype=float)
    states = int(n_states or matrix.shape[0])
    off_diagonal = matrix[~np.eye(matrix.shape[0], dtype=bool)]
    fastest = float(np.max(off_diagonal)) if off_diagonal.size else 0.0
    transitions = fastest * float(max(window, 0.0))
    ceiling = _MAX_STEPS if states <= 2 else 64
    return int(np.clip(np.ceil(_STEPS_PER_TRANSITION * transitions), _MIN_STEPS, ceiling))


def occupation_time_distribution(
    rate_matrix,
    window: float,
    *,
    n_steps: int | None = None,
    prune: float = _PRUNE,
) -> OccupationGrid:
    """Return ``P(f | T, K)`` by transfer-matrix propagation.

    The window is cut into *n_steps* equal slices. The joint distribution over
    (current state, how many slices have been spent in each state) is propagated
    with the exact one-slice transition matrix ``exp(Q · T/n)``, so the only
    approximation is that a transition happens at a slice boundary — never any
    sampling noise.

    Starting state is drawn from the equilibrium populations, which is the right
    condition for a burst: the molecule was diffusing long before it entered the
    focus.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)`` rates in Hz, ``K[target, source]``.
    window : float
        Burst duration, seconds.
    n_steps : int, optional
        Discretization; occupation fractions come out as multiples of ``1/n_steps``.
        Chosen by :func:`recommended_steps` when omitted, which is the right default
        in a fit loop because the rates move.
    prune : float
        Drop nodes lighter than this, renormalising afterwards.

    Returns
    -------
    OccupationGrid

    Raises
    ------
    ValueError
        For a non-square matrix, or fewer than two states.
    """
    matrix = np.array(rate_matrix, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise ValueError("the rate matrix must be square")
    n_states = matrix.shape[0]
    if n_states < 2:
        raise ValueError("a kinetic scheme needs at least two states")

    populations = equilibrium_populations(matrix)
    window = float(max(window, 0.0))
    if n_steps is None:
        n_steps = recommended_steps(matrix, window, n_states)
    n_steps = int(max(n_steps, 1))

    # A window of zero, or a scheme with no transitions at all, is the static
    # mixture: each burst spends the whole window in one state. Returned exactly
    # rather than as the n -> 0 limit of the propagator.
    if window <= 0.0 or not np.any(matrix[~np.eye(n_states, dtype=bool)] > 0.0):
        return OccupationGrid(
            fractions=np.eye(n_states),
            weights=populations,
            window=window,
            n_steps=n_steps,
        )

    generator = generator_from_rate_matrix(matrix)
    step = expm(generator * (window / n_steps))

    # Counters for the first n-1 states; the last state's occupancy is whatever is
    # left, which is what keeps the grid on the simplex exactly rather than to
    # rounding.
    counter_shape = (n_steps + 1,) * (n_states - 1)
    joint = np.zeros((n_states,) + counter_shape)
    joint[(slice(None),) + (0,) * (n_states - 1)] = populations

    for _ in range(n_steps):
        advanced = np.zeros_like(joint)
        for state in range(n_states):
            if state == n_states - 1:
                advanced[state] = joint[state]
                continue
            # One more slice spent in `state`: shift that state's counter by one.
            source = [slice(None)] * (n_states - 1)
            target = [slice(None)] * (n_states - 1)
            source[state] = slice(0, n_steps)
            target[state] = slice(1, n_steps + 1)
            advanced[(state,) + tuple(target)] = joint[(state,) + tuple(source)]
        # Transition: step[j, i] is the probability of i -> j over one slice.
        joint = np.tensordot(step, advanced, axes=([1], [0]))

    occupancy = joint.sum(axis=0)
    counts = np.stack(
        np.meshgrid(*([np.arange(n_steps + 1)] * (n_states - 1)), indexing="ij"),
        axis=-1,
    ).reshape(-1, n_states - 1)
    weights = occupancy.reshape(-1)

    # Only counts that fit inside the window are reachable.
    feasible = counts.sum(axis=1) <= n_steps
    keep = feasible & (weights > prune)
    if not keep.any():
        keep = feasible & (weights == weights[feasible].max())

    counts = counts[keep]
    weights = weights[keep]
    weights = weights / weights.sum()

    fractions = np.empty((counts.shape[0], n_states))
    fractions[:, : n_states - 1] = counts / n_steps
    fractions[:, n_states - 1] = 1.0 - counts.sum(axis=1) / n_steps
    return OccupationGrid(fractions=fractions, weights=weights, window=window, n_steps=n_steps)


def two_state_occupation_variance(rate_matrix, window: float) -> tuple[float, float]:
    """Return the exact mean and variance of the occupancy of state 0, for two states.

    The correctness test of the propagator, in closed form. The indicator of state 0
    is a telegraph process whose autocovariance is ``π₀ π₁ e^{−k|Δt|}`` with
    ``k = k₀₁ + k₁₀``; integrating it twice over the window gives::

        Var(f) = 2 π₀ π₁ [ 1/(kT) − (1 − e^{−kT}) / (kT)² ]

    with the familiar limits: the static mixture variance ``π₀π₁`` as ``T → 0``, and
    zero as ``T → ∞`` where every burst averages to the equilibrium population.

    Parameters
    ----------
    rate_matrix : array_like
        ``(2, 2)`` rates in Hz, ``K[target, source]``.
    window : float
        Observation window, seconds.

    Returns
    -------
    mean, variance : float
    """
    matrix = np.array(rate_matrix, dtype=float)
    if matrix.shape != (2, 2):
        raise ValueError("this closed form is for two states")
    populations = equilibrium_populations(matrix)
    mean = float(populations[0])
    static = float(populations[0] * populations[1])

    total_rate = float(matrix[1, 0] + matrix[0, 1])
    x = total_rate * float(window)
    if x <= 0.0:
        return mean, static
    if x < 1e-8:
        # 2(1/x - (1-e^-x)/x^2) -> 1 - x/3 as x -> 0.
        return mean, static * (1.0 - x / 3.0)
    return mean, 2.0 * static * (1.0 / x - (1.0 - np.exp(-x)) / (x * x))


def photon_weighted_occupation_variance(times, rate: float) -> float:
    """Return the variance of a two-state occupancy **as the photons measure it**.

    Every forward model here treats a burst's photon-weighted state fraction as
    its time-weighted one — photons are handed out over the states in proportion
    to the time spent in each. A molecule is brightest at the centre of its
    transit, so its photons over-sample whichever state it held then, and the
    effective averaging window is shorter than the burst's span. The result is a
    histogram *less* averaged than the model predicts at the true rate, and a fit
    that lowers the rate to compensate: 20% low at 1 kHz, 33% at 5 kHz.

    Nothing about that requires an approximation. The state indicator is a
    telegraph process with covariance ``π₀π₁ e^{−k|Δt|}``, and a photon-weighted
    fraction is a plain average over the photons, so::

        Var(f) = π₀ π₁ · (1/N²) · Σᵢ Σⱼ exp(−k |tᵢ − tⱼ|)

    exactly, with no assumption about how the photons are spread. Against ground
    truth this reproduces the measured variance to 0.4% (1 kHz) and 0.1% (5 kHz),
    where assuming uniform sampling is 9.5% and 32.4% out.

    The double sum is evaluated in one pass rather than in ``O(N²)``: with the
    times sorted, ``Σᵢ<ⱼ e^{−k(tⱼ−tᵢ)}`` is a running quantity that each photon
    updates from its predecessor by the gap between them.

    Parameters
    ----------
    times : array_like
        Photon arrival times within one burst, in seconds, ascending. Only the
        gaps matter, so the origin is free.
    rate : float
        Relaxation rate ``k = k₀₁ + k₁₀`` in Hz.

    Returns
    -------
    float
        The variance for an equally populated two-state system (``π₀π₁ = ¼``).
        Scale by ``4 π₀ π₁`` for an unequal one.

    See Also
    --------
    two_state_occupation_variance : the same quantity assuming uniform sampling.
    """
    t = np.asarray(times, dtype=float)
    n = t.size
    if n < 2:
        return 0.25
    decay = np.exp(-float(rate) * np.diff(t))
    running = 0.0
    total = 0.0
    for step in decay:
        running = step * (1.0 + running)
        total += running
    return 0.25 * (n + 2.0 * total) / (n * n)


def effective_window(times, rate: float) -> float:
    """Return the burst duration that would average a burst as its photons do.

    The duration a burst's photons *behave* like, rather than the span between
    its first and last one. Defined as the ``T`` at which the uniform-sampling
    variance equals the photon-weighted one, so it drops into everything already
    written in terms of a window — the occupation grid, the propagator, the
    nuisance measure — without any of it having to learn about arrival times.

    It is always shorter than the span, and shortens further as the rate rises,
    which is why the recovery bias grows with the rate.

    Parameters
    ----------
    times : array_like
        Photon arrival times within one burst, in seconds, ascending.
    rate : float
        Relaxation rate ``k = k₀₁ + k₁₀`` in Hz.

    Returns
    -------
    float
        Effective window in seconds. Falls back to the span when the rate is zero
        or the burst has too few photons to say anything.
    """
    t = np.asarray(times, dtype=float)
    if t.size < 2 or rate <= 0.0:
        return float(t[-1] - t[0]) if t.size >= 2 else 0.0
    target = photon_weighted_occupation_variance(t, rate) / 0.25

    # h(x) = 2[1/x - (1-e^-x)/x^2] is the uniform-sampling variance in units of
    # pi0*pi1, monotone decreasing from 1 at x=0. Invert it by bisection: the
    # bracket is cheap and Newton would need guarding at both ends.
    def h(x):
        return 2.0 * (1.0 / x - (1.0 - np.exp(-x)) / (x * x))

    if target >= 1.0:
        return float(t[-1] - t[0])
    lo, hi = 1e-8, 1.0
    while h(hi) > target and hi < 1e8:
        hi *= 2.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if h(mid) > target:
            lo = mid
        else:
            hi = mid
    return float(0.5 * (lo + hi) / rate)


def photon_weighted_occupation_variances(gaps, valid, rate: float) -> np.ndarray:
    """Vectorised :func:`photon_weighted_occupation_variance`, over many bursts.

    A fit moves the rate, so this is evaluated once per iteration over every
    burst. The recursion is sequential in *photon* but independent across bursts,
    so it runs as one pass over the padded photon axis rather than a Python loop
    over bursts. Padding entries carry a zero decay factor, which both resets the
    running sum and contributes nothing.

    Parameters
    ----------
    gaps : numpy.ndarray
        ``(n_bursts, max_photons - 1)`` inter-photon gaps in seconds, zero-padded.
    valid : numpy.ndarray
        Boolean array of the same shape marking real gaps.
    rate : float
        Relaxation rate in Hz.

    Returns
    -------
    numpy.ndarray
        ``(n_bursts,)`` variances for an equally populated two-state system.
    """
    gaps = np.asarray(gaps, dtype=float)
    valid = np.asarray(valid, dtype=bool)
    decay = np.where(valid, np.exp(-float(rate) * gaps), 0.0)
    running = np.zeros(gaps.shape[0])
    total = np.zeros(gaps.shape[0])
    for column in range(gaps.shape[1]):
        running = decay[:, column] * (1.0 + running)
        total += running
    n = valid.sum(axis=1) + 1.0
    return 0.25 * (n + 2.0 * total) / (n * n)


def effective_window_scale(gaps, valid, durations, rate: float) -> float:
    """Return how much shorter a burst's photons make its window, on average.

    The ratio of :func:`effective_window` to the first-to-last-photon span,
    averaged over bursts. Applied to the binned nuisance measure's durations it
    corrects the occupation law for the fact that photons do not sample a burst
    uniformly in time, without the measure having to carry arrival times.

    A single ratio is used rather than one per nuisance cell because the ratio is
    a property of a burst's *shape* — how sharply its brightness peaks — which
    varies far less between bursts than their durations or photon counts do. Per
    cell would be more faithful and needs the cell index the binning does not
    currently return.

    Parameters
    ----------
    gaps, valid : numpy.ndarray
        Padded inter-photon gaps and their mask, as for
        :func:`photon_weighted_occupation_variances`.
    durations : numpy.ndarray
        ``(n_bursts,)`` first-to-last-photon spans in seconds.
    rate : float
        Relaxation rate in Hz.

    Returns
    -------
    float
        Ratio in ``(0, 1]``; 1 when the rate is zero or nothing can be measured.
    """
    durations = np.asarray(durations, dtype=float)
    if rate <= 0.0 or durations.size == 0:
        return 1.0
    variances = photon_weighted_occupation_variances(gaps, valid, rate) / 0.25

    # Invert h(x) = 2[1/x - (1-e^-x)/x^2], monotone decreasing from 1, by
    # bisection on every burst at once. The upper bracket is generous because a
    # bright, sharply peaked burst can look far shorter than it is.
    target = np.clip(variances, 1e-12, 1.0 - 1e-12)
    lo = np.full(target.shape, 1e-8)
    hi = np.full(target.shape, 1e6)
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        value = 2.0 * (1.0 / mid - (1.0 - np.exp(-mid)) / (mid * mid))
        high = value > target
        lo = np.where(high, mid, lo)
        hi = np.where(high, hi, mid)
    effective = 0.5 * (lo + hi) / rate

    usable = durations > 0
    if not np.any(usable):
        return 1.0
    return float(np.clip(np.mean(effective[usable] / durations[usable]), 1e-3, 1.0))


def relaxation_rate(rate_matrix) -> float:
    """Return the rate at which a scheme forgets which state it started in.

    The slowest non-zero relaxation of the generator — for two states exactly
    ``k₀₁ + k₁₀``, the constant in the telegraph covariance, and for more the
    eigenvalue that outlives the rest and therefore sets how much a burst
    averages.

    Parameters
    ----------
    rate_matrix : array_like
        ``(n, n)`` rates in Hz, ``K[target, source]``.

    Returns
    -------
    float
        Relaxation rate in Hz; ``0`` for a scheme with no exchange.
    """
    matrix = np.asarray(rate_matrix, dtype=float)
    if matrix.size == 0 or not np.any(matrix):
        return 0.0
    generator = matrix.copy()
    np.fill_diagonal(generator, 0.0)
    np.fill_diagonal(generator, -generator.sum(axis=0))
    magnitudes = np.abs(np.linalg.eigvals(generator))
    non_zero = magnitudes[magnitudes > magnitudes.max() * 1e-9]
    return float(non_zero.min()) if non_zero.size else 0.0
