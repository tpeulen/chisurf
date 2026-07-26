"""Time-binned dynamic PDA: the exchange rate as a rate (PRD-50).

A dynamic PDA histogram depends on exchange only through ``K = (k1 + k2) * T``,
the mean number of transitions per observation. One dataset therefore cannot say
whether it saw fast exchange briefly or slow exchange for longer — a fact these
tests pin down before using it, because it is the whole reason the analysis needs
more than one bin width.

Cutting the same photon stream into several fixed-width time bins and fitting
those together with one linked rate is what turns that into a measurement. Not
because one bin width cannot yield a rate -- it can, once the observation time is
recorded -- but because one bin width cannot *test* it. A single histogram is fit
well by some exchange parameter whether or not two-state exchange is the right
description; requiring one rate to reproduce several bin widths is a constraint
the data can fail, and here does, by a factor of 500 in chi2r.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats


@pytest.fixture(scope="module")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _pda_data(observation_time: float, nmax: int = 60, nmin: int = 5):
    """Return a synthetic PDA dataset segmented into fixed bins of ``observation_time``."""
    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.data import DataCurve

    n = np.arange(nmax + 1)
    ps = stats.poisson.pmf(n, mu=20.0).astype(float)
    ps /= ps.sum()
    s1s2 = np.zeros((nmax + 1, nmax + 1), dtype=float)
    for total in range(nmin, nmax + 1):
        g = np.arange(total + 1)
        s1s2[g, total - g] += ps[total] * stats.binom.pmf(g, total, 0.6) * 1000.0

    ny, nx = s1s2.shape
    rows, cols = np.indices((ny, nx))
    y = s1s2.ravel(order="C")
    return DataCurve(
        name=f"pda-T{observation_time * 1e3:g}ms",
        load_filename_on_init=False,
        pda={
            "maximum_number_of_photons": nmax,
            "minimum_number_of_photons": nmin,
            "minimum_time_window_length": observation_time,
            "segmentation": "time-bins",
            "observation_time": observation_time,
            "channels": ([0], [1]),
            "s1s2": s1s2,
            "ps": ps,
            "row_indices": rows.ravel().tolist(),
            "col_indices": cols.ravel().tolist(),
            "ndim": 2,
            "shape": (ny, nx),
            "size": int(y.size),
            "tttr_indices": None,
        },
        y=y,
        x=np.arange(y.size),
        ey=tcspc.counting_noise(y),
    )


def _dynamic_fit(observation_time, rate, total=3e5, seed=1, states=(40.0, 62.0, 0.5)):
    """Return a dynamic two-state fit whose data was generated at ``rate`` (Hz)."""
    import chisurf.core.fitting.fit as fit_mod
    import chisurf.core.fluorescence.tcspc as tcspc
    from chisurf.core.models.pda.dynamic import PdaDynamicTwoStateModel

    fit = fit_mod.Fit(model_class=PdaDynamicTwoStateModel, data=_pda_data(observation_time))
    model = fit.model
    r1, r2, x1 = states
    model.states._R1.value, model.states._s1.value = r1, 4.0
    model.states._R2.value, model.states._s2.value = r2, 4.0
    model.states._x1.value = x1
    model.states._kex.value = rate
    model.update()
    _ = model.get_wres(fit)

    s1s2 = np.asarray(model.pda.get_S1S2_matrix(), dtype=float)
    ny, nx = fit.data.pda["shape"]
    s1s2 = s1s2[:ny, :nx]
    s1s2 = s1s2 / max(s1s2.sum(), 1e-12) * total
    noisy = np.random.default_rng(seed).poisson(s1s2).astype(float)
    fit.data.pda["s1s2"] = noisy
    fit.data.y = noisy.ravel(order="C")
    fit.data.ey = tcspc.counting_noise(fit.data.y)
    return fit, model


# --- the observation time is data, not a setting ------------------------------------


def test_the_model_takes_its_observation_time_from_the_dataset(qapp):
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.pda.dynamic import PdaDynamicTwoStateModel

    for window in (1e-3, 4e-3):
        fit = fit_mod.Fit(model_class=PdaDynamicTwoStateModel, data=_pda_data(window))
        assert fit.model.observation_time == pytest.approx(window)
        fit.model.states._kex.value = 500.0
        assert fit.model.transitions_per_window == pytest.approx(500.0 * window)


def test_data_without_an_observation_time_falls_back_to_the_window_bound(qapp):
    """Datasets read before the field existed must still load and compute."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.pda.dynamic import PdaDynamicTwoStateModel

    data = _pda_data(2e-3)
    del data.pda["observation_time"]
    del data.pda["segmentation"]
    fit = fit_mod.Fit(model_class=PdaDynamicTwoStateModel, data=data)
    assert fit.model.observation_time == pytest.approx(2e-3)
    fit.model.update()
    assert np.all(np.isfinite(np.asarray(fit.model.y)))


# --- the degeneracy one dataset cannot break ----------------------------------------


def test_one_dataset_cannot_tell_a_fast_rate_from_a_long_window(qapp):
    """Equal ``rate * T`` gives an identical histogram — hence the need for several.

    This is not a defect being documented away: it is the statement that a single
    PDA histogram measures transitions per observation, and it is what the
    global fit below is built to get around.
    """
    _, fast = _dynamic_fit(1e-3, 2000.0)     # K = 2
    _, slow = _dynamic_fit(4e-3, 500.0)      # K = 2, same product
    assert fast.transitions_per_window == pytest.approx(slow.transitions_per_window)
    assert np.allclose(np.asarray(fast.y), np.asarray(slow.y), rtol=1e-9)

    # A different product does change the histogram, so the shape is sensitive
    # to K even though it is blind to the factorisation.
    _, other = _dynamic_fit(1e-3, 500.0)     # K = 0.5
    assert not np.allclose(np.asarray(fast.y), np.asarray(other.y), rtol=1e-3)


# --- what several bin widths buy ------------------------------------------------------


def _joint_rate_fit(rate_short, rate_long, start=1500.0):
    """Fit two bin widths with one linked rate; return the rate and the chi2r's."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.global_model.globalfit import GlobalFitModel

    short, short_model = _dynamic_fit(1e-3, rate_short, seed=3)
    long, long_model = _dynamic_fit(4e-3, rate_long, seed=4)
    for model in (short_model, long_model):
        model.find_parameters()
        for parameter in model.parameters_all:
            parameter.fixed = True
    short_model.states._kex.fixed = False
    short_model.states._kex.value = start                  # start well away
    long_model.states._kex.link = short_model.states._kex  # one rate for both
    short_model.find_parameters()
    long_model.find_parameters()

    host = fit_mod.Fit(model_class=GlobalFitModel, data=short.data)
    host.model.fits = [short, long]
    host.model.find_parameters()
    assert short_model.states._kex.name in [p.name for p in host.model.parameters]
    host.run()
    return short_model, long_model, host.chi2r


@pytest.mark.slow
def test_a_global_fit_over_two_bin_widths_recovers_one_absolute_rate(qapp):
    """PRD-50: the time-binned analysis. One rate, several observation times.

    The two datasets are generated from the *same* rate at bin widths differing
    by 4x, so their dimensionless exchange differs by 4x. One rate has to
    reproduce both, and does.
    """
    true_rate = 600.0
    short_model, long_model, chi2r = _joint_rate_fit(true_rate, true_rate)

    assert float(short_model.states.k_ex) == pytest.approx(true_rate, rel=0.2)
    assert chi2r < 1.5
    # The shared rate means a different transitions-per-window per dataset --
    # which is the information the second bin width carries.
    assert long_model.transitions_per_window == pytest.approx(
        4.0 * short_model.transitions_per_window, rel=1e-6
    )


@pytest.mark.slow
def test_bin_widths_that_disagree_on_the_rate_are_rejected_together(qapp):
    """The diagnostic a single bin width cannot perform.

    Each histogram on its own is fit perfectly by *some* exchange parameter --
    that is exactly the degeneracy above, and it means a good chi2r from one
    time window is no evidence that the kinetic model is right. Requiring one
    rate to explain several bin widths is a real constraint: data whose windows
    imply different rates fits each window and fails the pair.
    """
    short_model, long_model, chi2r_bad = _joint_rate_fit(600.0, 2400.0)
    _, _, chi2r_good = _joint_rate_fit(600.0, 600.0)

    # Each dataset alone is fit well; measured 0.92 and 1.01.
    for window, rate, seed in ((1e-3, 600.0, 3), (4e-3, 2400.0, 4)):
        fit, model = _dynamic_fit(window, rate, seed=seed)
        model.find_parameters()
        for parameter in model.parameters_all:
            parameter.fixed = True
        model.states._kex.fixed = False
        model.states._kex.value = 1500.0
        model.find_parameters()
        fit.run()
        assert fit.chi2r < 1.5
        assert float(model.states.k_ex) == pytest.approx(rate, rel=0.2)

    # Jointly they cannot be reconciled. Measured 0.92 against 492.
    assert chi2r_good < 1.5
    assert chi2r_bad > 50.0 * chi2r_good


# --- fixed-width binning in the reader ------------------------------------------------


def _synthetic_tttr(rate_hz=2e4, duration=1.0, p_green=0.6, seed=0):
    """Return a two-channel Poisson photon stream as a tttrlib TTTR object."""
    tttrlib = pytest.importorskip("tttrlib")
    rng = np.random.default_rng(seed)
    n = int(rate_hz * duration)
    resolution = 1e-8                                  # 10 ns macro-time tick
    times = np.sort(rng.uniform(0, duration / resolution, n)).astype(np.uint64)
    channels = np.where(rng.random(n) < p_green, 0, 1).astype(np.int8)
    tttr = tttrlib.TTTR()
    tttr.append_events(
        macro_times=times.tolist(),
        micro_times=[0] * n,
        routing_channels=channels.tolist(),
        event_types=[0] * n,
    )
    tttr.header.set_macro_time_resolution(resolution)
    return tttr


def test_fixed_width_binning_produces_bins_of_the_requested_width(qapp):
    from chisurf.core.experiments.pda.reader import PdaReader

    tttr = _synthetic_tttr(rate_hz=2e4, duration=1.0)
    reader = PdaReader(channels=([0], [1]), micro_time_ranges=[(0, 2 ** 15)],
                       segmentation="time-bins")
    window = 2e-3
    s1s2, ps, first = reader.time_binned_histograms(
        tttr, [0], [1], window_length=window,
        minimum_number_of_photons=1, maximum_number_of_photons=200)

    # 1 s of stream at 2 ms per bin, at 20 kHz -> ~40 photons a bin, all kept.
    n_bins = int(s1s2.sum())
    assert n_bins == pytest.approx(1.0 / window, rel=0.02)
    assert ps.sum() == pytest.approx(1.0)
    assert first.size == n_bins

    # Mean photons per bin is the count rate times the bin width, by definition
    # of a fixed-width bin -- which is the property a burst search does not have.
    totals = np.arange(ps.size)
    assert float(totals @ ps) == pytest.approx(2e4 * window, rel=0.05)

    # Rows are channel 1, columns channel 2: the model's orientation.
    s1 = (s1s2.sum(axis=1) * np.arange(s1s2.shape[0])).sum()
    s2 = (s1s2.sum(axis=0) * np.arange(s1s2.shape[1])).sum()
    assert s1 / (s1 + s2) == pytest.approx(0.6, abs=0.02)


def test_wider_bins_hold_proportionally_more_photons(qapp):
    from chisurf.core.experiments.pda.reader import PdaReader

    tttr = _synthetic_tttr(rate_hz=2e4, duration=1.0)
    reader = PdaReader(channels=([0], [1]), micro_time_ranges=[(0, 2 ** 15)],
                       segmentation="time-bins")
    means = []
    for window in (1e-3, 2e-3, 4e-3):
        _, ps, _ = reader.time_binned_histograms(
            tttr, [0], [1], window_length=window,
            minimum_number_of_photons=0, maximum_number_of_photons=400)
        means.append(float(np.arange(ps.size) @ ps))
    assert means[1] == pytest.approx(2 * means[0], rel=0.05)
    assert means[2] == pytest.approx(4 * means[0], rel=0.05)


def test_the_photon_count_limits_drop_bins_outside_them(qapp):
    from chisurf.core.experiments.pda.reader import PdaReader

    tttr = _synthetic_tttr(rate_hz=2e4, duration=1.0)
    reader = PdaReader(channels=([0], [1]), micro_time_ranges=[(0, 2 ** 15)],
                       segmentation="time-bins")
    kwargs = dict(window_length=2e-3, maximum_number_of_photons=200)
    loose, _, _ = reader.time_binned_histograms(
        tttr, [0], [1], minimum_number_of_photons=1, **kwargs)
    strict, _, _ = reader.time_binned_histograms(
        tttr, [0], [1], minimum_number_of_photons=45, **kwargs)
    assert strict.sum() < loose.sum()
    # Nothing below the threshold survives.
    totals = np.add.outer(np.arange(strict.shape[0]), np.arange(strict.shape[1]))
    assert strict[totals < 45].sum() == 0


def test_an_empty_stream_gives_an_empty_histogram_rather_than_raising(qapp):
    tttrlib = pytest.importorskip("tttrlib")
    from chisurf.core.experiments.pda.reader import PdaReader

    reader = PdaReader(channels=([0], [1]), micro_time_ranges=[(0, 2 ** 15)],
                       segmentation="time-bins")
    s1s2, ps, first = reader.time_binned_histograms(
        tttrlib.TTTR(), [0], [1], window_length=1e-3,
        minimum_number_of_photons=1, maximum_number_of_photons=30)
    assert s1s2.shape == (31, 31) and s1s2.sum() == 0
    assert ps.size == 31 and first.size == 0


# --- arbitrary N-state schemes --------------------------------------------------------


def _n_state_fit(n_states=3):
    """Return a dynamic N-state PDA fit on the synthetic dataset."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.pda.dynamic_mc import PdaDynamicNStateModel

    fit = fit_mod.Fit(model_class=PdaDynamicNStateModel, data=_pda_data(2e-3))
    fit.model.n_states = n_states
    return fit, fit.model


@pytest.mark.parametrize("n_states", [2, 3, 4, 5])
def test_the_scheme_takes_any_number_of_states(qapp, n_states):
    _, model = _n_state_fit(n_states)
    assert model.states.rate_matrix().shape == (n_states, n_states)
    assert model.states.distances.size == n_states
    model.update()
    y = np.asarray(model.y)
    assert y.size and np.all(np.isfinite(y)) and float(np.sum(y)) > 0.0


@pytest.mark.parametrize("n_states", [2, 3, 4])
def test_every_off_diagonal_rate_is_a_discoverable_fitting_parameter(qapp, n_states):
    """A rate the optimiser cannot see is a constant, whatever its fixed flag says.

    Regression: the rates used to live in a dict, and ``find_objects`` recurses
    into lists only -- so none of them were ever offered to the optimiser.
    """
    _, model = _n_state_fit(n_states)
    model.find_parameters()
    found = {p.name for p in model.parameters_all}
    expected = {f"k{i}_{j}"
                for i in range(1, n_states + 1)
                for j in range(1, n_states + 1) if i != j}
    assert expected <= found, sorted(expected - found)
    assert len(expected) == n_states * (n_states - 1)


def test_freeing_a_rate_offers_it_to_the_optimiser(qapp):
    _, model = _n_state_fit(3)
    model.find_parameters()
    assert "k1_2" not in [p.name for p in model.parameters]   # fixed by default
    dict(model.states.rates_by_name())["k1_2"].fixed = False
    model.find_parameters()
    assert "k1_2" in [p.name for p in model.parameters]


def test_the_rate_matrix_places_each_rate_at_target_source(qapp):
    """k_ij is i->j, and the matrix is indexed [target, source]."""
    _, model = _n_state_fit(3)
    rates = dict(model.states.rates_by_name())
    for parameter in rates.values():
        parameter.value = 0.0
    rates["k1_2"].value = 250.0
    rates["k3_1"].value = 40.0

    K = model.states.rate_matrix()
    assert K[1, 0] == pytest.approx(250.0)     # 1 -> 2
    assert K[0, 2] == pytest.approx(40.0)      # 3 -> 1
    assert K.sum() == pytest.approx(290.0)


def test_a_linear_chain_is_just_a_cycle_with_two_rates_at_zero(qapp):
    """Scheme topology is set by the rates, not by a separate model."""
    from chisurf.core.fluorescence.kinetics import equilibrium_populations

    _, model = _n_state_fit(3)
    rates = dict(model.states.rates_by_name())
    for name, value in (("k1_2", 100.0), ("k2_1", 100.0),
                        ("k2_3", 50.0), ("k3_2", 200.0),
                        ("k1_3", 0.0), ("k3_1", 0.0)):
        rates[name].value = value

    K = model.states.rate_matrix()
    assert K[2, 0] == 0.0 and K[0, 2] == 0.0        # no direct 1 <-> 3
    populations = equilibrium_populations(K)
    assert populations.sum() == pytest.approx(1.0)
    assert np.all(populations > 0)                   # the chain still connects all three
    model.update()
    assert np.all(np.isfinite(np.asarray(model.y)))


def test_resizing_keeps_the_rates_that_survive(qapp):
    _, model = _n_state_fit(3)
    dict(model.states.rates_by_name())["k1_2"].value = 777.0

    model.n_states = 4
    assert dict(model.states.rates_by_name())["k1_2"].value == pytest.approx(777.0)
    assert "k1_4" in dict(model.states.rates_by_name())

    model.n_states = 2
    surviving = dict(model.states.rates_by_name())
    assert surviving["k1_2"].value == pytest.approx(777.0)
    assert "k1_3" not in surviving
    assert model.states.rate_matrix().shape == (2, 2)


def test_the_grid_view_and_the_parameters_are_the_same_numbers(qapp):
    """The editable matrix is a view on the parameters, not a second copy."""
    _, model = _n_state_fit(3)
    rates = dict(model.states.rates_by_name())
    rates["k2_3"].value = 321.0
    flat = model.rate_values
    assert flat[(2 - 1) * 3 + (3 - 1)] == pytest.approx(321.0)
    assert all(flat[i * 3 + i] == 0.0 for i in range(3))     # diagonal stays empty

    grid = list(flat)
    grid[(3 - 1) * 3 + (1 - 1)] = 654.0                      # edit k3_1 in the grid
    model.rate_values = grid
    assert rates["k3_1"].value == pytest.approx(654.0)


def _two_state_pair(rate, method, window=2e-3):
    """Return (N-state model at N=2, exact two-state model) for the same kinetics."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.models.pda.dynamic import PdaDynamicTwoStateModel

    _, n_model = _n_state_fit(2)
    n_model.method = method
    n_model.states._R[0].value, n_model.states._s[0].value = 40.0, 4.0
    n_model.states._R[1].value, n_model.states._s[1].value = 62.0, 4.0
    rates = n_model.states.rates_by_name()
    rates["k1_2"].value = rate / 2.0        # symmetric: x1 = 0.5, k1 + k2 = rate
    rates["k2_1"].value = rate / 2.0
    n_model.update()

    fit = fit_mod.Fit(model_class=PdaDynamicTwoStateModel, data=_pda_data(window))
    two = fit.model
    two.states._R1.value, two.states._s1.value = 40.0, 4.0
    two.states._R2.value, two.states._s2.value = 62.0, 4.0
    two.states._x1.value, two.states._kex.value = 0.5, rate
    two.update()

    a = np.asarray(n_model.y, dtype=float)
    b = np.asarray(two.y, dtype=float)
    return 0.5 * np.abs(a / a.sum() - b / b.sum()).sum()


def test_the_sampled_n_state_route_reproduces_the_exact_two_state_law(qapp):
    """At N=2 there is a closed-form answer, so the general route can be checked.

    Every other validation of the N-state path is against sampling; this one is
    against the exact occupation-time law of the two-state process.
    """
    for rate in (200.0, 800.0, 4e3, 2e4):
        assert _two_state_pair(rate, "monte-carlo") < 0.03, rate


def test_the_moment_match_fails_exactly_where_the_boundary_atoms_carry_the_mass(qapp):
    """Why the default route has a slow-exchange limit, measured against the truth.

    The Szabo-Gopich route matches a *density* to two moments, and the exact
    occupation-time law is not a density: a molecule that never switched sits on
    a point mass at f = 0 or f = 1. Those atoms hold 82% of the distribution at
    K = 0.4 and nothing at K = 40, and the error tracks them:

    ======  =============  ===========  ============
    K       szabo-gopich   sampled      atom mass
    ======  =============  ===========  ============
    0.4     0.242          0.012        0.819
    1.6     0.121          0.017        0.450
    8       0.013          0.009        0.018
    40      0.001          0.003        0.000
    ======  =============  ===========  ============

    So the guidance is not a rule of thumb: switch to ``monte-carlo`` when the
    exchange is slow enough that molecules survive the window without switching.
    """
    from chisurf.core.models.pda.dynamic import two_state_occupation_quadrature

    window = 2e-3
    slow, fast = 200.0, 2e4
    atoms_slow = two_state_occupation_quadrature(0.5, slow * window, 512)[1]
    atoms_fast = two_state_occupation_quadrature(0.5, fast * window, 512)[1]
    assert atoms_slow[0] + atoms_slow[-1] > 0.7        # nearly all mass is atoms
    assert atoms_fast[0] + atoms_fast[-1] < 1e-6       # none is

    assert _two_state_pair(slow, "szabo-gopich") > 0.1      # cannot follow them
    assert _two_state_pair(slow, "monte-carlo") < 0.03      # sampling can
    assert _two_state_pair(fast, "szabo-gopich") < 0.01     # nothing left to miss
