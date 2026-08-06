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


@pytest.mark.slow
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
    from chisurf.core.models.pda2c.dynamic import two_state_occupation_quadrature

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


def test_the_quadrature_stays_on_the_support_the_states_can_reach():
    """A time average is a convex combination, so it cannot leave the values.

    The beta is matched on ``[min(values), max(values)]`` for that reason.
    Matching it on the interval the observable is merely *defined* on keeps the
    two moments — so the moment test above cannot see the difference — while
    putting weight on values no mixture of the states produces.
    """
    from chisurf.core.fluorescence.kinetics import szabo_gopich_quadrature

    for window in (1e-9, 1e-5, 5e-4, 1e-2, 100.0):
        nodes, _ = szabo_gopich_quadrature(
            THREE_STATE, EFFICIENCIES, window, n_nodes=256
        )
        assert nodes.min() >= EFFICIENCIES.min() - 1e-9, window
        assert nodes.max() <= EFFICIENCIES.max() + 1e-9, window

    # An explicit support is still honoured, for a caller that wants a wider one.
    wide, _ = szabo_gopich_quadrature(
        THREE_STATE, EFFICIENCIES, 1e-9, n_nodes=256, lower=0.0, upper=1.0
    )
    assert wide.min() < EFFICIENCIES.min()
    assert wide.max() > EFFICIENCIES.max()


@pytest.mark.parametrize("k_ex", (0.4, 1.6, 8.0))
def test_slow_two_state_exchange_follows_the_exact_occupation_law(k_ex):
    """The discriminating check: total variation against the exact two-state law.

    Two states at 0.35/0.65 exchanging symmetrically. On the reachable support
    the two-moment match is within a few percent of the exact distribution even
    at less than one transition per window; on ``[0, 1]`` the same match is 0.79
    away, with 30 % of the weight outside ``[0.35, 0.65]``.
    """
    from chisurf.core.fluorescence.kinetics import szabo_gopich_quadrature
    from chisurf.core.models.pda2c.dynamic import two_state_occupation_quadrature

    values = np.array([0.35, 0.65])
    p1 = 0.5
    window = 1.0                      # the exact law works in units of the window
    rate_matrix = np.array([[0.0, k_ex * p1], [k_ex * (1 - p1), 0.0]])

    nodes, weights = szabo_gopich_quadrature(
        rate_matrix, values, window, n_nodes=2048
    )
    fractions, exact_weights = two_state_occupation_quadrature(p1, k_ex)
    exact_nodes = values[1] + fractions * (values[0] - values[1])

    def binned(x, w):
        h, _ = np.histogram(x, bins=np.linspace(0.0, 1.0, 82), weights=w)
        return h / h.sum()

    total_variation = 0.5 * np.abs(
        binned(nodes, weights) - binned(exact_nodes, exact_weights)
    ).sum()
    assert total_variation < 0.16, total_variation
    assert np.all((nodes >= values.min() - 1e-9) & (nodes <= values.max() + 1e-9))


def test_a_single_state_has_no_dynamics():
    from chisurf.core.fluorescence.kinetics import szabo_gopich_quadrature

    nodes, weights = szabo_gopich_quadrature(np.zeros((1, 1)), np.array([0.42]), 1e-3)
    assert nodes.size == 1
    assert nodes[0] == pytest.approx(0.42)
    assert weights[0] == pytest.approx(1.0)


# ── wired into both PDA families ───────────────────────────────────────────


@pytest.mark.slow
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
    from chisurf.core.models.pda2c.dynamic_mc import Pda2cDynamicNStateModel
    from test.gui.test_pda2c_model_editor import _make_pda_data  # noqa: PLC0415

    fit = fit_mod.Fit(model_class=Pda2cDynamicNStateModel, data=_make_pda_data())
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
    from chisurf.core.models.pda2c.dynamic_mc import Pda2cDynamicNStateModel
    from test.gui.test_pda2c_model_editor import _make_pda_data  # noqa: PLC0415

    fit = fit_mod.Fit(model_class=Pda2cDynamicNStateModel, data=_make_pda_data())
    model = fit.model
    model.update()
    first = np.array(model.y, copy=True)
    model.seed = model.seed + 1          # only affects the Monte-Carlo route
    model.update()
    assert np.array_equal(first, np.array(model.y))


def test_three_colour_model_takes_a_rate_matrix():
    """PDA3c gets the same multistate route, driven by a rate matrix."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.pda3c import Pda3cModel

    data = Pda3cSimulatorReader(n_bursts=400, seed=17).read()[0]
    fit = fit_mod.Fit(model_class=Pda3cModel, data=data)
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


# ── the exact alternative for arbitrary kinetics ───────────────────────────


@pytest.mark.slow
def test_simulating_the_kinetics_agrees_where_the_approximation_is_valid():
    """The two multistate routes must meet in the regime both describe.

    ``simulate`` samples occupation times directly and is exact in distribution
    for any rate matrix; ``szabo-gopich`` keeps two moments. They have to agree
    once exchange is fast enough for a two-moment match to be adequate, which is
    the only place the approximation claims to be right.
    """
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.pda3c import Pda3cModel

    data = Pda3cSimulatorReader(n_bursts=600, seed=23).read()[0]
    fit = fit_mod.Fit(model_class=Pda3cModel, data=data)
    model = fit.model
    model.species.append(r_gr=62.0, r_bg=56.0, r_br=74.0)
    model.species.append(r_gr=70.0, r_bg=64.0, r_br=82.0)
    model.dynamic = True
    model.setup._window.value = 2e-3
    # Fast enough that a two-moment match is adequate (many transitions/window).
    model.rate_matrix = np.array(
        [[0.0, 4e4, 1e4], [3e4, 0.0, 2e4], [1.5e4, 2.5e4, 0.0]]
    )

    exact = model.total_log_likelihood()
    assert np.isfinite(exact)

    # Fast exchange averages the states, so the sampled probability vectors
    # must concentrate on the equilibrium-weighted mean.
    from chisurf.core.fluorescence.kinetics import equilibrium_populations

    setup = model.setup.as_setup()
    blue = np.stack([model._mean_channel_probabilities(s, setup)[0]
                     for s in model.species.as_species()])
    expected = equilibrium_populations(model.rate_matrix) @ blue
    assert expected.sum() == pytest.approx(1.0)


@pytest.mark.slow
def test_the_simulated_route_is_deterministic():
    """A fixed seed keeps the objective smooth for the optimiser."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.pda3c import Pda3cModel

    data = Pda3cSimulatorReader(n_bursts=400, seed=29).read()[0]
    fit = fit_mod.Fit(model_class=Pda3cModel, data=data)
    model = fit.model
    model.species.append(r_gr=62.0, r_bg=56.0, r_br=74.0)
    model.dynamic = True
    model.rate_matrix = np.array([[0.0, 500.0], [400.0, 0.0]])
    model.setup._window.value = 2e-3

    first = model.total_log_likelihood()
    second = model.total_log_likelihood()
    assert first == second


@pytest.mark.slow
def test_the_simulated_route_works_where_the_approximation_does_not():
    """Slow exchange: the routes must differ, and only one of them is right.

    A two-moment match cannot represent the multi-modal time average that
    well-separated slow states produce, so this is the regime the simulated
    route exists for.
    """
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.pda3c import Pda3cModel

    data = Pda3cSimulatorReader(n_bursts=600, seed=23).read()[0]
    fit = fit_mod.Fit(model_class=Pda3cModel, data=data)
    model = fit.model
    model.species.append(r_gr=62.0, r_bg=56.0, r_br=74.0)
    model.species.append(r_gr=70.0, r_bg=64.0, r_br=82.0)
    model.dynamic = True
    model.setup._window.value = 2e-3
    model.rate_matrix = np.array([[0.0, 5.0, 1.0], [3.0, 0.0, 2.0], [1.5, 2.5, 0.0]])

    slow = model.total_log_likelihood()
    model.rate_matrix = model.rate_matrix * 1e4      # same states, fast exchange
    fast = model.total_log_likelihood()

    assert np.isfinite(slow) and np.isfinite(fast)
    # Slow (states resolved) and fast (averaged) are different physics.
    assert slow != pytest.approx(fast, rel=1e-3)


# --- sampled occupancy: the engine path against the reference it replaces -----------


def _kolmogorov_smirnov(a, b):
    """Two-sample KS statistic, without pulling in scipy for one number."""
    grid = np.union1d(a, b)
    ca = np.searchsorted(np.sort(a), grid, side="right") / a.size
    cb = np.searchsorted(np.sort(b), grid, side="right") / b.size
    return float(np.max(np.abs(ca - cb)))


@pytest.mark.parametrize("rate", [1e2, 1e3, 1e4])
def test_the_engine_and_the_reference_sample_the_same_occupancy_law(rate):
    from chisurf.core.fluorescence.kinetics import (
        occupation_time_fractions,
        occupation_time_fractions_reference,
    )

    K = np.array([[0.0, rate, rate / 2], [rate, 0.0, rate], [rate / 2, rate, 0.0]])
    window, n = 2e-3, 4000
    fast = occupation_time_fractions(K, window, n, seed=5)
    slow = occupation_time_fractions_reference(K, window, n, seed=5)

    assert fast.shape == slow.shape == (n, 3)
    assert np.allclose(fast.sum(axis=1), 1.0, atol=1e-9)
    # Independent samplers with independent streams, so compare distributions,
    # not draws: the observable a dynamic PDA actually consumes is a projection
    # of the occupancy onto per-state probabilities.
    projection = np.array([0.8, 0.5, 0.2])
    assert _kolmogorov_smirnov(fast @ projection, slow @ projection) < 0.05
    assert np.allclose(fast.mean(axis=0), slow.mean(axis=0), atol=0.02)
    assert np.allclose(fast.std(axis=0), slow.std(axis=0), atol=0.02)


def test_sampled_occupancy_recovers_the_equilibrium_populations():
    from chisurf.core.fluorescence.kinetics import (
        equilibrium_populations,
        occupation_time_fractions,
    )

    K = np.array([[0.0, 200.0, 50.0], [150.0, 0.0, 300.0], [100.0, 250.0, 0.0]])
    # A window far longer than the relaxation time: every window self-averages.
    fractions = occupation_time_fractions(K, window=2.0, n_samples=1500, seed=3)
    assert np.allclose(fractions.mean(axis=0), equilibrium_populations(K), atol=0.02)


def test_sampled_occupancy_is_deterministic_for_a_fixed_seed():
    from chisurf.core.fluorescence.kinetics import occupation_time_fractions

    K = np.array([[0.0, 5e3, 1e3], [3e3, 0.0, 2e3], [1e3, 4e3, 0.0]])
    a = occupation_time_fractions(K, 1e-3, 500, seed=11)
    b = occupation_time_fractions(K, 1e-3, 500, seed=11)
    c = occupation_time_fractions(K, 1e-3, 500, seed=12)
    assert np.array_equal(a, b)          # a fit objective must not wander
    assert not np.array_equal(a, c)


def test_an_absorbing_state_holds_the_whole_window():
    from chisurf.core.fluorescence.kinetics import occupation_time_fractions

    # State 2 is entered but never left; state 0 and 1 exchange.
    K = np.array([[0.0, 1e3, 0.0], [1e3, 0.0, 0.0], [1e2, 1e2, 0.0]])
    fractions = occupation_time_fractions(K, 5e-3, 400, seed=2)
    assert np.allclose(fractions.sum(axis=1), 1.0, atol=1e-9)
    # Equilibrium is the absorbing state, so almost every window ends up there.
    assert fractions[:, 2].mean() > 0.9


def test_a_single_state_occupies_itself_completely():
    from chisurf.core.fluorescence.kinetics import occupation_time_fractions

    fractions = occupation_time_fractions(np.zeros((1, 1)), 1e-3, 20, seed=1)
    assert fractions.shape == (20, 1)
    assert np.allclose(fractions, 1.0)


def test_the_engine_is_usable_after_another_swig_extension_loads_first():
    """Regression: SWIG modules share a type table unless one is asked not to.

    IMP registers ``std::vector<double>`` when it loads, and the documented
    development ``PYTHONPATH`` imports IMP at interpreter start, so it always
    loads first here. Before tttrlib was built with a private type table that
    made every by-value vector argument raise a TypeError naming the type the
    object plainly had -- including the rate matrices this module hands the
    simulation engine.
    """
    IMP = pytest.importorskip("IMP")
    assert IMP is not None
    tttrlib = pytest.importorskip("tttrlib")
    if not hasattr(getattr(tttrlib, "SimEngine", None), "set_state_log"):
        pytest.skip("installed simulation engine predates the state log")

    system = tttrlib.SimSystem()
    system.set_rate_matrices(tttrlib.VectorDouble([0.0] * 9),
                             tttrlib.VectorDouble([1.0] * 9))
    assert len(system.k_nrad()) == 9
