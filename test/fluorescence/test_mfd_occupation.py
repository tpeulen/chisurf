"""The occupation-time propagator, against three independent references.

``P(f | T, K)`` is the only way the kinetics reaches the forward model, so an error
here becomes an exchange rate and nothing else complains. It is therefore checked
against things that were derived separately:

* the **exact** mean and variance of any time-averaged observable, from
  :func:`chisurf.core.fluorescence.kinetics.time_averaged_moments`;
* a **closed form** for the two-state occupancy variance, derived from the telegraph
  autocovariance rather than from the propagator;
* a **Gillespie sampler** of the same process, which shares no code with either.

Plus convergence in the discretization, which PRD-71 asks be tested rather than
assumed.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.kinetics import (
    equilibrium_populations,
    occupation_time_fractions_reference,
    time_averaged_moments,
)
from chisurf.core.fluorescence.mfd.occupation import (
    occupation_time_distribution,
    recommended_steps,
    two_state_occupation_variance,
)


def _two_state(k01: float, k10: float) -> np.ndarray:
    """Return a two-state rate matrix in the shared ``K[target, source]`` convention."""
    return np.array([[0.0, k10], [k01, 0.0]])


# ──────────────────────────────────────────────────────────────────────────────
# Basic shape
# ──────────────────────────────────────────────────────────────────────────────
def test_grid_lives_on_the_simplex():
    """Every node is a set of fractions that sum to one, weighted to one."""
    grid = occupation_time_distribution(_two_state(500.0, 300.0), 2e-3, n_steps=32)
    assert grid.fractions.shape[1] == 2
    assert np.allclose(grid.fractions.sum(axis=1), 1.0)
    assert np.all(grid.fractions >= -1e-12)
    assert float(grid.weights.sum()) == pytest.approx(1.0)
    assert len(grid) > 1


def test_a_scheme_with_no_transitions_is_the_static_mixture():
    """No exchange means every burst spends the whole window in one state."""
    grid = occupation_time_distribution(np.zeros((2, 2)), 1e-3)
    assert np.allclose(grid.fractions, np.eye(2))
    assert np.allclose(grid.weights, [0.5, 0.5])


def test_a_zero_window_is_the_static_mixture_too():
    """No time to exchange in is the same statement as no exchange."""
    matrix = _two_state(1000.0, 1000.0)
    grid = occupation_time_distribution(matrix, 0.0)
    assert np.allclose(grid.fractions, np.eye(2))
    assert np.allclose(grid.weights, equilibrium_populations(matrix))


# ──────────────────────────────────────────────────────────────────────────────
# Against the exact moments
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("k01", "k10", "window"),
    [
        (100.0, 100.0, 1e-3),      # a few transitions per burst
        (2000.0, 800.0, 1e-3),     # fast exchange, strongly averaged
        (20.0, 60.0, 1e-3),        # slow exchange, nearly static
        (500.0, 500.0, 5e-4),
    ],
)
def test_mean_and_variance_match_the_exact_moments(k01, k10, window):
    """The exact answer for any observable, computed a completely different way."""
    matrix = _two_state(k01, k10)
    values = np.array([0.8, 0.2])
    grid = occupation_time_distribution(matrix, window, n_steps=128)
    mean, variance = time_averaged_moments(matrix, values, window)
    assert grid.average(values) == pytest.approx(mean, rel=1e-6)
    assert grid.variance(values) == pytest.approx(variance, rel=0.03)


def test_occupancy_variance_matches_the_closed_form():
    """The two-state occupation law, derived from the telegraph autocovariance."""
    for k01, k10 in ((300.0, 700.0), (1500.0, 1500.0), (30.0, 10.0)):
        matrix = _two_state(k01, k10)
        for window in (2e-4, 1e-3, 5e-3):
            grid = occupation_time_distribution(matrix, window, n_steps=128)
            mean, variance = two_state_occupation_variance(matrix, window)
            first = np.array([1.0, 0.0])
            assert grid.average(first) == pytest.approx(mean, rel=1e-6)
            assert grid.variance(first) == pytest.approx(variance, rel=0.03)


def test_the_closed_form_has_the_right_limits():
    """Static mixture when there is no time to exchange; zero spread when there is lots."""
    matrix = _two_state(400.0, 600.0)
    populations = equilibrium_populations(matrix)
    static = float(populations[0] * populations[1])
    _, short = two_state_occupation_variance(matrix, 1e-12)
    _, long = two_state_occupation_variance(matrix, 10.0)
    assert short == pytest.approx(static, rel=1e-6)
    assert long < static * 1e-2


# ──────────────────────────────────────────────────────────────────────────────
# Against an independent simulation
# ──────────────────────────────────────────────────────────────────────────────
def test_distribution_matches_a_gillespie_sampler():
    """The whole distribution, not just its moments, against sampled trajectories.

    The propagator's point is that it carries no Monte-Carlo noise into the
    objective. That claim is only worth anything if it agrees with the Monte Carlo
    it replaces.
    """
    matrix = _two_state(600.0, 400.0)
    window = 1.5e-3
    grid = occupation_time_distribution(matrix, window, n_steps=64)
    sampled = occupation_time_fractions_reference(matrix, window, 40_000, seed=3)

    edges = np.linspace(0.0, 1.0, 21)
    reference, _ = np.histogram(sampled[:, 0], bins=edges, density=False)
    reference = reference / reference.sum()
    predicted, _ = np.histogram(
        grid.fractions[:, 0], bins=edges, weights=grid.weights
    )
    # Total-variation distance; sampling noise alone is a few percent at 40k draws.
    assert 0.5 * np.abs(predicted - reference).sum() < 0.05


def test_slow_exchange_keeps_the_two_populations_apart():
    """Slow exchange must stay bimodal — the case a two-moment match cannot follow."""
    grid = occupation_time_distribution(_two_state(20.0, 20.0), 1e-3, n_steps=64)
    f = grid.fractions[:, 0]
    ends = float(grid.weights[(f < 0.05) | (f > 0.95)].sum())
    middle = float(grid.weights[(f > 0.4) & (f < 0.6)].sum())
    assert ends > 0.85
    assert middle < 0.02


def test_fast_exchange_collapses_onto_the_equilibrium_population():
    """Many transitions per burst average every burst to the same value."""
    matrix = _two_state(2e5, 1e5)
    grid = occupation_time_distribution(matrix, 1e-3)
    populations = equilibrium_populations(matrix)
    _, exact = two_state_occupation_variance(matrix, 1e-3)
    assert grid.average([1.0, 0.0]) == pytest.approx(float(populations[0]), rel=1e-6)
    assert np.sqrt(exact) < 0.05
    assert np.sqrt(grid.variance([1.0, 0.0])) == pytest.approx(np.sqrt(exact), rel=0.15)


def test_the_discretization_adapts_to_the_exchange_rate():
    """A fixed ``n`` cannot serve a fit loop, because the rates move.

    The transfer matrix places transitions at slice boundaries, so what must be
    resolved is the number of transitions *within* the burst. At 300 transitions
    per burst a 64-step grid reports a spread ~50% too wide — and that excess width
    would be read as static heterogeneity, i.e. as the very thing the kinetics is
    supposed to be distinguished from.
    """
    matrix = _two_state(2e5, 1e5)
    window = 1e-3
    _, exact = two_state_occupation_variance(matrix, window)

    coarse = occupation_time_distribution(matrix, window, n_steps=64)
    adaptive = occupation_time_distribution(matrix, window)

    assert recommended_steps(matrix, window) > 64
    assert coarse.variance([1.0, 0.0]) > exact * 1.8
    assert adaptive.variance([1.0, 0.0]) == pytest.approx(exact, rel=0.3)
    # A nearly static scheme does not pay for resolution it cannot use.
    assert recommended_steps(_two_state(5.0, 5.0), window) == 16


# ──────────────────────────────────────────────────────────────────────────────
# Discretization
# ──────────────────────────────────────────────────────────────────────────────
def test_it_converges_in_the_number_of_steps():
    """Convergence in ``n`` is a test, not an assumption (PRD-71)."""
    matrix = _two_state(800.0, 500.0)
    window = 1e-3
    _, exact = two_state_occupation_variance(matrix, window)
    errors = []
    for n_steps in (8, 16, 32, 64, 128):
        grid = occupation_time_distribution(matrix, window, n_steps=n_steps)
        errors.append(abs(grid.variance([1.0, 0.0]) - exact) / exact)
    assert errors[-1] < 0.02
    # Monotone improvement, allowing a little slack for the pruning threshold.
    assert all(b <= a * 1.15 for a, b in zip(errors, errors[1:]))


# ──────────────────────────────────────────────────────────────────────────────
# Three states
# ──────────────────────────────────────────────────────────────────────────────
def test_three_states_stay_on_the_simplex_and_match_the_exact_moments():
    """Three states is the case the deterministic route is still comfortable for."""
    matrix = np.array(
        [
            [0.0, 400.0, 100.0],
            [300.0, 0.0, 500.0],
            [200.0, 600.0, 0.0],
        ]
    )
    window = 1e-3
    grid = occupation_time_distribution(matrix, window, n_steps=32)
    assert grid.fractions.shape[1] == 3
    assert np.allclose(grid.fractions.sum(axis=1), 1.0)
    assert np.all(grid.fractions >= -1e-12)

    values = np.array([0.9, 0.5, 0.1])
    mean, variance = time_averaged_moments(matrix, values, window)
    assert grid.average(values) == pytest.approx(mean, rel=1e-5)
    assert grid.variance(values) == pytest.approx(variance, rel=0.06)


def test_a_single_state_scheme_is_refused():
    """One state has no kinetics; saying so beats returning a degenerate grid."""
    with pytest.raises(ValueError):
        occupation_time_distribution(np.zeros((1, 1)), 1e-3)
    with pytest.raises(ValueError):
        occupation_time_distribution(np.zeros((2, 3)), 1e-3)


# ──────────────────────────────────────────────────────────────────────────────
# Photons do not sample a burst uniformly in time
# ──────────────────────────────────────────────────────────────────────────────
def test_uniform_arrivals_reproduce_the_uniform_sampling_formula():
    """With photons spread evenly, the arrival-time form must agree with the old one.

    The guard against a "fix" that changes the answer everywhere rather than only
    where the assumption it replaces is violated.
    """
    from chisurf.core.fluorescence.mfd.occupation import (
        photon_weighted_occupation_variance,
        two_state_occupation_variance,
    )

    window = 2.0e-3
    times = np.linspace(0.0, window, 4000)
    for rate in (200.0, 1000.0, 5000.0):
        matrix = np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]])
        _, uniform = two_state_occupation_variance(matrix, window)
        assert photon_weighted_occupation_variance(times, rate) == pytest.approx(
            uniform, rel=0.02
        )


def test_photons_bunched_in_the_middle_average_less():
    """A burst brightest at its centre is less averaged than its span implies.

    This is the whole mechanism: the photons carry information about a shorter
    stretch of the state trajectory than the first-to-last span covers, so the
    occupancy they report scatters more and the effective window is shorter.
    """
    from chisurf.core.fluorescence.mfd.occupation import (
        effective_window,
        photon_weighted_occupation_variance,
        two_state_occupation_variance,
    )

    window, rate = 2.0e-3, 5000.0
    matrix = np.array([[0.0, rate / 2.0], [rate / 2.0, 0.0]])
    _, uniform = two_state_occupation_variance(matrix, window)

    # Same span, same photon count, concentrated near the centre.
    u = np.linspace(-1.0, 1.0, 4000)
    bunched = 0.5 * window * (1.0 + np.sign(u) * np.abs(u) ** 3)
    bunched = np.sort(bunched - bunched[0])

    assert photon_weighted_occupation_variance(bunched, rate) > uniform * 1.2
    assert effective_window(bunched, rate) < 0.75 * window
    # And an evenly-lit burst is unchanged, so nothing moves that should not.
    assert effective_window(np.linspace(0.0, window, 4000), rate) == pytest.approx(
        window, rel=0.05
    )
