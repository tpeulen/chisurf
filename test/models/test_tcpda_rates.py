"""Three-colour PDA: the exchange scheme as fitting parameters.

Guards the property that motivated the change — a rate the optimiser can
actually see. The two-colour model shipped its scheme in a dict, where
``find_objects`` (which recurses into lists only) never found it, so no rate was
ever offered to the optimiser however its ``fixed`` flag read. These tests fail
loudly if the three-colour scheme regresses the same way.
"""

import numpy as np
import pytest

WINDOW = 2e-3


def _model(n_extra_species: int = 1, n_bursts: int = 200, seed: int = 3):
    """Return a tcPDA model with ``1 + n_extra_species`` distance populations."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.experiments.pda3c import Pda3cSimulatorReader
    from chisurf.core.models.pda3c.tcpda import TcPdaModel

    data = Pda3cSimulatorReader(n_bursts=n_bursts, seed=seed).read()[0]
    model = fit_mod.Fit(model_class=TcPdaModel, data=data).model
    for index in range(n_extra_species):
        model.species.append(r_gr=62.0 + 8 * index, r_bg=56.0 + 8 * index,
                             r_br=74.0 + 8 * index)
    model.setup._window.value = WINDOW
    model.find_parameters()
    return model


def _rate_names(model):
    """Return the discovered rate-parameter names, sorted."""
    return sorted(p.name for p in model.parameters_all
                  if p.name.startswith("k") and "_" in p.name)


# -- discovery: the whole point ---------------------------------------------


@pytest.mark.parametrize("n_species, n_rates", [(2, 2), (3, 6), (4, 12)])
def test_every_rate_is_discovered(n_species, n_rates):
    """All ``n(n-1)`` off-diagonal rates reach the optimiser's parameter list."""
    model = _model(n_extra_species=n_species - 1)
    names = _rate_names(model)
    assert len(names) == n_rates
    assert names == sorted(f"k{i}_{j}"
                           for i in range(1, n_species + 1)
                           for j in range(1, n_species + 1) if i != j)


def test_a_freed_rate_becomes_a_free_parameter():
    """Freeing a rate puts it in ``parameters``, which is what the fit varies."""
    model = _model(n_extra_species=1)
    assert "k1_2" not in [p.name for p in model.parameters]
    model.rates_by_name()["k1_2"].fixed = False
    model.find_parameters()
    assert "k1_2" in [p.name for p in model.parameters]


def test_the_objective_moves_when_a_rate_does():
    """A rate the optimiser can see must change the objective it minimises.

    Discovery alone is not enough — a parameter can be listed and still be
    ignored by the likelihood, which looks exactly like a converged fit.
    """
    model = _model(n_extra_species=1)
    model.dynamic = True
    model.rate_matrix = np.array([[0.0, 300.0], [200.0, 0.0]])
    before = model.total_log_likelihood()
    model.rates_by_name()["k1_2"].value = 2000.0
    assert model.total_log_likelihood() != pytest.approx(before)


# -- the scheme is data, not code -------------------------------------------


def test_k_ij_lands_at_target_source():
    """``k_ij`` is the rate i -> j, stored at ``K[j-1, i-1]``."""
    model = _model(n_extra_species=2)
    rates = model.rates_by_name()
    for p in rates.values():
        p.value = 0.0
    rates["k1_2"].value = 111.0
    rates["k3_2"].value = 222.0
    K = model.rate_matrix
    assert K[1, 0] == pytest.approx(111.0)
    assert K[1, 2] == pytest.approx(222.0)
    assert np.count_nonzero(K) == 2


def test_a_linear_chain_is_a_scheme_with_zeros():
    """Topology is expressed by zeroing transitions, not by a scheme switch."""
    model = _model(n_extra_species=2)
    rates = model.rates_by_name()
    for name in ("k1_3", "k3_1"):
        rates[name].value = 0.0
    for name in ("k1_2", "k2_1", "k2_3", "k3_2"):
        rates[name].value = 100.0
    K = model.rate_matrix
    assert K[2, 0] == 0.0 and K[0, 2] == 0.0        # no direct 1 <-> 3
    assert K[1, 0] > 0.0 and K[2, 1] > 0.0          # 1 -> 2 -> 3 intact


def test_the_grid_round_trips_through_the_parameters():
    """The editable grid and the fitting parameters are one object."""
    model = _model(n_extra_species=2)
    model.rate_values = [0, 10, 20, 30, 0, 40, 50, 60, 0]
    rates = model.rates_by_name()
    assert rates["k1_2"].value == pytest.approx(10.0)
    assert rates["k3_2"].value == pytest.approx(60.0)
    assert model.rate_values == pytest.approx([0, 10, 20, 30, 0, 40, 50, 60, 0])


# -- size tracks the species ------------------------------------------------


def test_the_scheme_follows_the_species_count():
    """Adding a species adds a row and a column, keeping the rates entered."""
    model = _model(n_extra_species=1)
    model.rates_by_name()["k1_2"].value = 321.0
    model.species.append(r_gr=80.0, r_bg=70.0, r_br=90.0)
    model.find_parameters()
    assert model.n_states == 3
    assert len(_rate_names(model)) == 6
    assert model.rates_by_name()["k1_2"].value == pytest.approx(321.0)


def test_a_scheme_of_the_wrong_size_is_reported():
    """A mismatch must raise, not average over the wrong number of states.

    Silently mixing the wrong count produces a finite, plausible, wrong
    likelihood — the failure mode worth being noisy about.
    """
    model = _model(n_extra_species=2)
    with pytest.raises(ValueError, match="species"):
        model.rate_matrix = np.eye(2)


# -- an empty scheme means no scheme ----------------------------------------


def test_no_rates_entered_reads_as_no_scheme():
    """A model nobody entered rates into stays on the route it always used."""
    model = _model(n_extra_species=1)
    assert model.rate_matrix is None
    model.dynamic = True
    assert np.isfinite(model.total_log_likelihood())   # the K_ex two-state route


def test_clearing_the_scheme_restores_the_static_route():
    """Assigning ``None`` zeroes the rates rather than deleting the parameters."""
    model = _model(n_extra_species=1)
    model.rate_matrix = np.array([[0.0, 300.0], [200.0, 0.0]])
    assert model.rate_matrix is not None
    model.rate_matrix = None
    assert model.rate_matrix is None
    assert len(_rate_names(model)) == 2                # parameters still there


# -- transitions per window --------------------------------------------------


def test_transitions_per_window_does_not_depend_on_the_spelling():
    """One physical system, two spellings of its matrix, one exchange speed.

    ``dynamic_max_transitions`` decides whether the model samples trajectories
    or short-circuits to the equilibrium occupancy, so a matrix carrying its
    generator diagonal must not measure twice the escape rate of the same
    matrix written off-diagonal-only.
    """
    from chisurf.core.fluorescence.kinetics import transitions_per_window

    off_diagonal = np.array([[0.0, 3e5], [3e5, 0.0]])
    generator = off_diagonal.copy()
    np.fill_diagonal(generator, [-3e5, -3e5])

    expected = 3e5 * WINDOW
    assert transitions_per_window(off_diagonal, WINDOW) == pytest.approx(expected)
    assert transitions_per_window(generator, WINDOW) == pytest.approx(expected)


def test_transitions_per_window_takes_the_fastest_state():
    """The estimate is the largest escape rate, not an average over states."""
    from chisurf.core.fluorescence.kinetics import transitions_per_window

    # State 2 escapes at 100 + 400 = 500 Hz; state 1 at 10 Hz.
    K = np.array([[0.0, 100.0, 0.0], [10.0, 0.0, 0.0], [0.0, 400.0, 0.0]])
    assert transitions_per_window(K, 1.0) == pytest.approx(500.0)


# -- bounded cost ------------------------------------------------------------


def test_the_node_ceiling_coarsens_and_says_so(caplog):
    """The likelihood grid is (nodes x bursts); the node count must be bounded.

    The occupancy grid bounds the node count only combinatorially, so with many
    trajectories and several states the distinct nodes approach
    ``dynamic_samples``. Coarsening merges trajectories that spent nearly the
    same time in each state — interchangeable under the smooth
    occupancy-to-probability map — rather than dropping nodes, which would
    silently reweight the occupation distribution.
    """
    model = _model(n_extra_species=2, n_bursts=150)
    model.dynamic = True
    model.rate_matrix = np.array([[0.0, 300.0, 100.0],
                                  [200.0, 0.0, 250.0],
                                  [150.0, 220.0, 0.0]])
    model.dynamic_samples, model.dynamic_resolution = 2000, 128
    model.dynamic_max_nodes = 40

    with caplog.at_level("WARNING"):
        assert np.isfinite(model.total_log_likelihood())

    messages = [r.getMessage() for r in caplog.records if "dynamic_max_nodes" in r.getMessage()]
    assert len(messages) == 1, f"expected one summary warning, got {messages}"
    assert "coarsened to" in messages[0]


def test_a_ceiling_that_does_not_bind_changes_nothing():
    """Under the ceiling the quadrature must be untouched, bit for bit."""
    model = _model(n_extra_species=1, n_bursts=150)
    model.dynamic = True
    model.rate_matrix = np.array([[0.0, 300.0], [200.0, 0.0]])
    model.dynamic_samples, model.dynamic_resolution = 600, 24

    model.dynamic_max_nodes = 2000
    bounded = model.total_log_likelihood()
    model.dynamic_max_nodes = 10**9
    assert model.total_log_likelihood() == bounded


def test_the_burst_likelihood_chunks_over_bursts():
    """``burst_log_likelihood`` must not build a (points x bursts x K) block.

    The result is (points x bursts); the broadcast that builds it is a factor
    ``K`` larger and carries several temporaries of that size. Chunked, the
    answer has to be identical to the unchunked one.
    """
    from chisurf.core.fluorescence.pda3c import likelihood as lk

    rng = np.random.default_rng(0)
    counts = rng.integers(0, 12, size=(400, 3)).astype(float)
    p = rng.dirichlet(np.ones(3), size=37)

    full = lk.burst_log_likelihood(counts, p)
    original = lk._KERNEL_ELEMENT_BUDGET
    try:
        lk._KERNEL_ELEMENT_BUDGET = 64      # force many chunks
        chunked = lk.burst_log_likelihood(counts, p)
    finally:
        lk._KERNEL_ELEMENT_BUDGET = original

    assert chunked.shape == (37, 400)
    assert np.array_equal(full, chunked)


# -- the fit itself ----------------------------------------------------------


@pytest.mark.slow
def test_a_rate_is_recovered_from_a_wrong_start():
    """The optimiser walks a rate back from 4x too fast to near the truth.

    Bursts come from an independent forward route — a fresh distance triple per
    state per burst, mixed by sampled occupation times, then split
    multinomially — so this tests the fit rather than restating the model's own
    factorisation. Only ``k1_2`` is asserted: see the module docstring of
    ``tcpda.py`` for the measured bias in the recovered total rate, which is why
    the tolerance here is generous and the other rate is not checked.
    """
    from chisurf.core.fluorescence.kinetics import occupation_time_fractions
    from chisurf.core.fluorescence.pda3c import (
        BurstCounts,
        blue_channel_probabilities,
        green_channel_probabilities,
    )

    truth = np.array([[0.0, 300.0], [200.0, 0.0]])       # k1_2 = 200, k2_1 = 300
    model = _model(n_extra_species=1)
    for parameter, value in zip(model.species._means[:3], (45.0, 42.0, 58.0)):
        parameter.value = value
    model.species._means[3].value = 68.0
    model.species._means[4].value = 62.0
    model.species._means[5].value = 80.0
    model.dynamic = True
    model.rate_matrix = truth

    rng = np.random.default_rng(11)
    n = 6000
    setup = model.setup.as_setup()
    fractions = occupation_time_fractions(truth, WINDOW, n, 88)
    p_blue = np.zeros((n, 3))
    p_green = np.zeros((n, 2))
    for index, component in enumerate(model.species.as_species()):
        d = np.clip(rng.multivariate_normal(component.means, component.covariance,
                                            size=n), 1e-6, None)
        p_blue += fractions[:, index, None] * blue_channel_probabilities(
            d[:, 1], d[:, 2], d[:, 0], setup)
        p_green += fractions[:, index, None] * green_channel_probabilities(d[:, 0], setup)
    n_blue = rng.poisson(60.0, n)
    n_green = rng.poisson(50.0, n)
    counts = BurstCounts(
        blue=np.array([rng.multinomial(k, p) for k, p in zip(n_blue, p_blue)], float),
        green=np.array([rng.multinomial(k, p) for k, p in zip(n_green, p_green)], float),
    )
    model._counts_cache = counts.collapsed()
    model._pmf_cache = None

    model.rate_matrix = np.array([[0.0, 900.0], [1400.0, 0.0]])   # 4x too fast
    model.find_parameters()
    for parameter in model.parameters_all:
        parameter.fixed = parameter.name not in ("k1_2", "k2_1")
    model.find_parameters()
    model.fit.run()

    assert model.rates_by_name()["k1_2"].value == pytest.approx(200.0, rel=0.35)
