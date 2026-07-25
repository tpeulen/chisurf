"""Szabo-Gopich time-averaged moments for multistate systems.

Dynamic PDA needs the distribution of a state observable *averaged over the
observation window*. Two states have an exact closed form; beyond that the
tractable route is Gopich and Szabo's — keep the first two moments, which are
exact for any rate matrix, and match a shape to them.

So the moments are checked hard (against direct simulation of the Markov
process, and against the exact two-state law where both apply), and the matched
shape is checked only for the properties it has to have.
"""

from __future__ import annotations

import numpy as np
import pytest


def _simulate_time_average(rate_matrix, values, window, n=20000, seed=0):
    """Directly simulate the time-averaged observable, stationary start."""
    from chisurf.core.fluorescence.kinetics import (
        equilibrium_populations,
        generator_from_rate_matrix,
    )

    rng = np.random.default_rng(seed)
    generator = generator_from_rate_matrix(rate_matrix)
    populations = equilibrium_populations(rate_matrix)
    values = np.asarray(values, dtype=float)
    n_states = values.size
    exit_rates = -np.diag(generator)

    out = np.empty(n)
    for i in range(n):
        state = rng.choice(n_states, p=populations)
        elapsed, total = 0.0, 0.0
        while elapsed < window:
            rate = exit_rates[state]
            dwell = rng.exponential(1.0 / rate) if rate > 0 else np.inf
            step = min(dwell, window - elapsed)
            total += values[state] * step
            elapsed += step
            if not np.isfinite(dwell):
                break
            targets = generator[:, state].copy()
            targets[state] = 0.0
            if targets.sum() <= 0:
                break
            state = rng.choice(n_states, p=targets / targets.sum())
        out[i] = total / window
    return out


THREE_STATE = np.array(
    [                       # [target, source], Hz
        [0.0, 800.0, 100.0],
        [500.0, 0.0, 600.0],
        [200.0, 300.0, 0.0],
    ]
)
EFFICIENCIES = np.array([0.15, 0.55, 0.85])


# ── the exact parts ────────────────────────────────────────────────────────


def test_equilibrium_populations_are_stationary():
    from chisurf.core.fluorescence.kinetics import (
        equilibrium_populations,
        generator_from_rate_matrix,
    )

    populations = equilibrium_populations(THREE_STATE)
    assert populations.sum() == pytest.approx(1.0)
    assert np.all(populations > 0)
    # Stationarity is the definition: Q p = 0.
    assert np.allclose(generator_from_rate_matrix(THREE_STATE) @ populations, 0.0,
                       atol=1e-10)


def test_the_mean_is_the_equilibrium_average_at_any_window():
    """A stationary process has a window-independent mean, by construction."""
    from chisurf.core.fluorescence.kinetics import (
        equilibrium_populations,
        time_averaged_moments,
    )

    expected = float(equilibrium_populations(THREE_STATE) @ EFFICIENCIES)
    for window in (1e-6, 1e-3, 1.0):
        mean, _ = time_averaged_moments(THREE_STATE, EFFICIENCIES, window)
        assert mean == pytest.approx(expected)


def test_the_variance_interpolates_between_static_and_averaged():
    """The two limits are what dynamic PDA distinguishes.

    A window far shorter than the exchange time resolves the states, so the
    variance is the full static heterogeneity. A window far longer averages them
    into one, so it goes to zero. Anything in between is the dynamic signal.
    """
    from chisurf.core.fluorescence.kinetics import (
        equilibrium_populations,
        time_averaged_moments,
    )

    populations = equilibrium_populations(THREE_STATE)
    mean = float(populations @ EFFICIENCIES)
    static = float(populations @ (EFFICIENCIES - mean) ** 2)

    _, fast_window = time_averaged_moments(THREE_STATE, EFFICIENCIES, 1e-9)
    assert fast_window == pytest.approx(static, rel=1e-3)

    _, slow_window = time_averaged_moments(THREE_STATE, EFFICIENCIES, 10.0)
    assert slow_window < 1e-3 * static

    windows = [1e-5, 1e-4, 1e-3, 1e-2]
    variances = [time_averaged_moments(THREE_STATE, EFFICIENCIES, w)[1] for w in windows]
    assert all(a > b for a, b in zip(variances, variances[1:])), variances


@pytest.mark.parametrize("window", (2e-4, 1e-3, 5e-3))
def test_the_moments_match_a_direct_simulation(window):
    """The claim that the moments are exact, checked against the process itself."""
    from chisurf.core.fluorescence.kinetics import time_averaged_moments

    mean, variance = time_averaged_moments(THREE_STATE, EFFICIENCIES, window)
    sample = _simulate_time_average(THREE_STATE, EFFICIENCIES, window, n=20000, seed=3)

    assert mean == pytest.approx(sample.mean(), abs=3e-3)
    assert np.sqrt(variance) == pytest.approx(sample.std(), rel=0.06)


def test_two_state_moments_agree_with_the_exact_occupation_law():
    """Where both apply they must agree — the moments are not an approximation.

    The exact two-state law gives the whole distribution; Szabo-Gopich gives its
    first two moments for any number of states. On two states the moments have
    to coincide, which ties the multistate route to the one already validated
    against simulation.
    """
    from chisurf.core.fluorescence.kinetics import time_averaged_moments
    from chisurf.core.models.pda.dynamic import two_state_occupation_quadrature

    p1, k_ex = 0.3, 4.0
    window = 1.0                      # the exact law works in units of the window
    # k_ex = (k1 + k2) * T, and k1 = k_ex * p2, k2 = k_ex * p1.
    rate_matrix = np.array([[0.0, k_ex * p1], [k_ex * (1 - p1), 0.0]])
    values = np.array([1.0, 0.0])     # observable = "is in state 1" -> time fraction

    mean, variance = time_averaged_moments(rate_matrix, values, window)
    fractions, weights = two_state_occupation_quadrature(p1, k_ex)
    exact_mean = float(weights @ fractions)
    exact_variance = float(weights @ (fractions - exact_mean) ** 2)

    assert mean == pytest.approx(exact_mean, abs=1e-3)
    assert variance == pytest.approx(exact_variance, rel=2e-2)


# ── the matched shape ──────────────────────────────────────────────────────


def test_the_quadrature_reproduces_the_moments_it_was_matched_to():
    from chisurf.core.fluorescence.kinetics import (
        szabo_gopich_quadrature,
        time_averaged_moments,
    )

    for window in (1e-5, 5e-4, 1e-2):
        mean, variance = time_averaged_moments(THREE_STATE, EFFICIENCIES, window)
        nodes, weights = szabo_gopich_quadrature(
            THREE_STATE, EFFICIENCIES, window, n_nodes=256
        )
        assert weights.sum() == pytest.approx(1.0)
        assert np.all((nodes >= 0.0) & (nodes <= 1.0))
        assert float(weights @ nodes) == pytest.approx(mean, abs=5e-3)
        recovered = float(weights @ (nodes - mean) ** 2)
        assert recovered == pytest.approx(variance, rel=0.15), (variance, recovered)


def test_fast_exchange_collapses_onto_the_average():
    """Once the states have averaged out there is almost nothing left to spread.

    The variance falls as ``2/(|lambda| T)`` and so never reaches exactly zero;
    what must hold is that the residual width is negligible against the state
    separation, and that the mass sits on the equilibrium average.
    """
    from chisurf.core.fluorescence.kinetics import (
        equilibrium_populations,
        szabo_gopich_quadrature,
    )

    nodes, weights = szabo_gopich_quadrature(THREE_STATE, EFFICIENCIES, 100.0)
    mean = float(equilibrium_populations(THREE_STATE) @ EFFICIENCIES)
    assert float(weights @ nodes) == pytest.approx(mean, abs=1e-3)
    separation = EFFICIENCIES.max() - EFFICIENCIES.min()
    assert np.sqrt(weights @ (nodes - mean) ** 2) < 0.01 * separation


def test_a_vanishing_variance_degenerates_to_one_node():
    """The point-mass fallback, rather than a beta with runaway shape."""
    from chisurf.core.fluorescence.kinetics import szabo_gopich_quadrature

    identical = np.array([0.4, 0.4, 0.4])
    nodes, weights = szabo_gopich_quadrature(THREE_STATE, identical, 1e-3)
    assert nodes.size == 1
    assert nodes[0] == pytest.approx(0.4)
    assert weights[0] == pytest.approx(1.0)


def test_slow_exchange_keeps_the_states_apart():
    """In the static limit the mass sits near the individual state values."""
    from chisurf.core.fluorescence.kinetics import szabo_gopich_quadrature

    nodes, weights = szabo_gopich_quadrature(
        THREE_STATE, EFFICIENCIES, 1e-9, n_nodes=256
    )
    # Bounded support, and a spread comparable to the state separation rather
    # than a narrow peak at the average.
    assert np.all((nodes >= 0.0) & (nodes <= 1.0))
    mean = float(weights @ nodes)
    assert np.sqrt(weights @ (nodes - mean) ** 2) > 0.15


def test_a_single_state_has_no_dynamics():
    from chisurf.core.fluorescence.kinetics import szabo_gopich_quadrature

    nodes, weights = szabo_gopich_quadrature(np.zeros((1, 1)), np.array([0.42]), 1e-3)
    assert nodes.size == 1
    assert nodes[0] == pytest.approx(0.42)
    assert weights[0] == pytest.approx(1.0)


# ── wired into both PDA families ───────────────────────────────────────────


def test_the_approximation_converges_where_it_should_and_says_so_where_it_does_not():
    """Where Szabo-Gopich agrees with exact sampling, and where it cannot.

    The analytic route keeps two moments and matches a shape; Monte-Carlo
    samples the true distribution. They must converge once the molecule
    actually exchanges, and they cannot agree in the slow limit — three
    well-separated states give a *trimodal* distribution of the time-averaged
    probability, and no two-parameter shape represents three peaks.

    Measured against the exact route (total variation of the S1S2 matrix):

    ======  ======
    k*T     TV
    ======  ======
    0.002   0.19
    0.2     0.11
    2       0.010
    20      0.0012
    ======  ======

    So the approximation is good to ~1% from roughly two transitions per window
    upward. Below that the right description is a *static* mixture anyway —
    slow exchange means the states are resolved, which is what a static
    multi-species fit models directly.
    """
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.pda.dynamic_mc import PdaDynamicThreeStateModel
    from test.gui.test_pda_model_editor import _make_pda_data  # noqa: PLC0415

    fit = fit_mod.Fit(model_class=PdaDynamicThreeStateModel, data=_make_pda_data())
    model = fit.model
    assert model.method == "szabo-gopich"
    base = model.states.rate_matrix().copy()

    def total_variation(scale):
        model.states.rate_matrix = (lambda b=base * scale: b)
        model.method = "szabo-gopich"
        model.update()
        analytic = np.array(model.y, copy=True)
        model.method = "monte-carlo"
        model.update()
        sampled = np.array(model.y, copy=True)
        assert np.all(np.isfinite(analytic)) and analytic.sum() > 0
        assert np.all(np.isfinite(sampled)) and sampled.sum() > 0
        return 0.5 * np.abs(
            analytic / analytic.sum() - sampled / sampled.sum()
        ).sum()

    # Exchanging: the two routes describe the same distribution.
    assert total_variation(10.0) < 0.03
    assert total_variation(100.0) < 0.01
    # Slow: they must not silently agree, or the docs above would be wrong.
    assert total_variation(0.01) > 0.10


def test_the_analytic_route_is_deterministic():
    """A stochastic objective makes an optimiser chase simulation noise."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.pda.dynamic_mc import PdaDynamicThreeStateModel
    from test.gui.test_pda_model_editor import _make_pda_data  # noqa: PLC0415

    fit = fit_mod.Fit(model_class=PdaDynamicThreeStateModel, data=_make_pda_data())
    model = fit.model
    model.update()
    first = np.array(model.y, copy=True)
    model.seed = model.seed + 1          # only affects the Monte-Carlo route
    model.update()
    assert np.array_equal(first, np.array(model.y))


def test_three_colour_model_takes_a_rate_matrix():
    """TcPDA gets the same multistate route, driven by a rate matrix."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.tcpda import TcPdaModel

    data = Pda3cSimulatorReader(n_bursts=400, seed=17).read()[0]
    fit = fit_mod.Fit(model_class=TcPdaModel, data=data)
    model = fit.model
    model.species.append(r_gr=62.0, r_bg=56.0, r_br=74.0)
    model.species.append(r_gr=70.0, r_bg=64.0, r_br=82.0)

    static = model.total_log_likelihood()

    model.dynamic = True
    model.rate_matrix = np.array(
        [[0.0, 400.0, 100.0], [300.0, 0.0, 200.0], [150.0, 250.0, 0.0]]
    )
    model.setup._window.value = 2e-3
    dynamic = model.total_log_likelihood()

    assert np.isfinite(dynamic)
    assert dynamic != pytest.approx(static)

    # Fast exchange must average the three states into one.
    model.rate_matrix = model.rate_matrix * 1e5
    fast = model.total_log_likelihood()
    assert np.isfinite(fast)
    assert fast != pytest.approx(dynamic)
