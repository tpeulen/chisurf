"""The filter calculator's numerical workflows, driven on the emtk model (no widget).

These are the scenarios the retired Qt filter-calculator widget's tests covered, run on
``gui.model.FilterModel``: the example, unmixing, nuisance filters, fit ranges, stacked mode,
auto-fit through real fit objects, instrument calibration. What the Qt tests asserted about
widgets (docks, toolbar actions, list items, colour stability) is covered by the click tests
in ``test_emtk_filter_clicks.py`` and ``test_emtk_filter_parity.py``.
"""

import numpy as np
import pytest

from chisurf.plugins.fcs.fcs_filter_calculator.api import synthetic_decay
from chisurf.plugins.fcs.fcs_filter_calculator.gui.model import FilterModel

#: The detector setup the tests were written against: green, red and yellow detectors.
SEEDED_SETUP = {
    "detectors": {
        "green": {"chs": [0, 8]},
        "red": {"chs": [1, 9]},
        "yellow": {"chs": [2, 10]},
    }
}
DETECTORS = ["green", "red", "yellow"]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    for name, folder in (("CHISURF_SETTINGS_DIR", "settings"), ("MMFDB_SETTINGS_DIR", "mmfdb")):
        monkeypatch.setenv(name, str(tmp_path / folder))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def seeded_model() -> FilterModel:
    """The example on the seeded green/red/yellow setup, computed."""
    model = FilterModel(example=False)
    model.set_setup(SEEDED_SETUP)
    model.populate_example()
    model.compute()
    return model


def results(model):
    return [entry["result"] for entry in model.results()]


def set_irf(model, detector, path):
    model.detectors.values["irf"][f"{detector}|"] = str(path)


def autofit_model(tmp_path, n_components=2, kind="lifetime"):
    """A model with a two-exponential mixed decay and no components, auto-fitted."""
    fast = synthetic_decay(256, 1.2, bin_width=0.05, normalize=True)
    slow = synthetic_decay(256, 4.0, bin_width=0.05, normalize=True)
    tmp_path.mkdir(parents=True, exist_ok=True)
    total_path = tmp_path / "mix.txt"
    np.savetxt(total_path, 60000.0 * fast + 40000.0 * slow)
    model = FilterModel(example=False)
    model.detectors.selected = []  # no detector IRF: fit the ideal decay
    model.options_model.scatter_irf = False
    model.options_model.fit_background = False
    model.set_total_paths([total_path])
    model._auto_fit_settings["kind"] = kind
    model._auto_fit_components(n_components=n_components)
    return model


# -- the example ---------------------------------------------------------------------------------


def test_the_example_is_two_components_and_a_convolved_total():
    model = FilterModel()
    model.compute()
    assert len(model.components) == 2
    assert model._total_vector is not None
    assert np.all(model._total_vector == np.floor(model._total_vector))
    assert abs(model._total_vector.sum() - 100_000) < 2_000
    assert model.total_label.startswith("Convolved example")
    assert model.options_model.scatter_irf is True
    detector_names = model.detectors.selected or ["default"]
    assert len(model._total_vectors_by_detector) == len(detector_names)
    # The scatter/IRF nuisance pattern is taken from each detector's own IRF.
    assert set(model._irf_by_detector) == set(detector_names)
    assert not model._synthetic_scatter_fits
    assert model.results()


def test_the_seeded_setup_gives_green_red_and_yellow_detectors():
    """Guardrail: the tests below depend on these detectors being listed."""
    model = seeded_model()
    assert model.detectors.selected == DETECTORS


def test_preloaded_patterns_are_convolved_per_detector():
    model = seeded_model()
    totals = list(model._total_vectors_by_detector.values())
    fast = model.components[0].source
    assert not np.array_equal(totals[0], totals[1])
    assert not np.allclose(
        fast["patterns_by_detector"]["green"], fast["patterns_by_detector"]["red"]
    )
    assert set(model._irf_by_detector) >= {"green", "red"}


def test_example_mixture_survives_project_roundtrip(tmp_path):
    project = tmp_path / "example.json"
    source = FilterModel()
    source.compute()
    expected = source._total_vector.copy()
    irf_path = tmp_path / "scatter_irf.txt"
    np.savetxt(irf_path, [0.0, 1.0, 0.5])
    source.options_model.scatter_irf = True
    detector = (source.detectors.selected or ["green"])[0]
    set_irf(source, detector, irf_path)
    source.save_project(project)

    restored = FilterModel(example=False)
    restored.load_project(project)

    assert np.allclose(restored._total_vector, expected)
    assert len(restored.components) == 2
    assert restored.options_model.fit_background is True
    assert restored.options_model.scatter_irf is True
    assert restored.detectors.irf_path(detector) == str(irf_path)
    assert set(restored._total_vectors_by_detector) == set(source._total_vectors_by_detector)


# -- unmixing and nuisance filters -----------------------------------------------------------------


def test_model_unmixes_total_with_synthetic_components(tmp_path):
    total = 7500.0 * synthetic_decay(128, 1.0, bin_width=0.1) + 2500.0 * synthetic_decay(
        128, 4.0, bin_width=0.1
    )
    total_path = tmp_path / "mixed_decay.txt"
    np.savetxt(total_path, total)

    model = FilterModel(example=False)
    model.set_total_paths([total_path])
    for name, tau in (("fast", 1.0), ("slow", 4.0)):
        model.add_component(
            {"type": "synthetic", "model": "lifetime", "name": name, "lifetime": tau, "bin_width": 0.1}
        )
    model.unmix()

    assert model._unmix_result is not None
    assert np.allclose(model._unmix_result.fractions, [0.75, 0.25])
    found = results(model)
    assert found
    assert all("unmixing" in result.metadata for result in found)


def test_irf_scatter_is_added_as_a_hidden_nuisance_filter(tmp_path):
    irf_path = tmp_path / "irf.txt"
    x = np.arange(256, dtype=float)
    np.savetxt(irf_path, np.exp(-0.5 * ((x - 12.0) / 2.0) ** 2))

    model = seeded_model()
    # A measured IRF for the first detector only (the rest stay synthetic).
    set_irf(model, model.detectors.selected[0], irf_path)
    model.options_model.scatter_irf = True
    model.compute()

    found = results(model)
    assert found
    assert all(result.n_filters == result.n_species + 2 for result in found)
    assert all(result.nuisance_labels[0] == "Afterpulse / constant" for result in found)
    assert all(result.nuisance_labels[1].startswith("Scatter / IRF (") for result in found)
    assert found[0].nuisance_labels[1].endswith(", measured)")
    # Detectors without a measured IRF use their (synthetic) detector IRF as the scatter shape.
    assert all(result.nuisance_labels[1].endswith(", detector-IRF)") for result in found[1:])
    assert all(result.to_channel_filters().shape[0] == result.n_species for result in found)


def test_nuisance_scatter_fit_ignores_zero_emission_species():
    """A species that emits nothing in a detector must not break the scatter fit."""
    model = FilterModel()
    model.options_model.scatter_irf = True  # synthetic (no measured IRF loaded)
    x = np.arange(256, dtype=float)
    total = np.exp(-x / 25.0) + 0.01
    real = np.exp(-x / 40.0) + 0.01
    zero = np.zeros_like(x)

    detector = (model.detectors.selected or ["green"])[0]
    patterns, labels = model._nuisance_patterns(total, [real, zero], detector)

    assert any(label.startswith("Scatter / IRF (") for label in labels)
    scatter = patterns[labels.index(next(l for l in labels if l.startswith("Scatter")))]
    assert scatter.size == total.size
    assert np.all(np.isfinite(scatter)) and scatter.sum() > 0.0


def test_fit_pattern_source_selects_detector_specific_snapshot():
    model = FilterModel(example=False)
    model.add_component(
        {
            "type": "synthetic",
            "model": "lifetime_spectrum",
            "name": "fit component",
            "amplitudes": [1.0],
            "lifetimes": [3.0],
            "bin_width": 0.1,
            "patterns_by_detector": {
                "green": [4.0, 2.0, 1.0],
                "red": [1.0, 0.5, 0.25],
                "__default__": [4.0, 2.0, 1.0],
            },
        }
    )
    component = model.components[0]
    green, _ = model._species_item_pattern(component, 3, ["green"])
    red, _ = model._species_item_pattern(component, 3, ["red"])
    assert np.allclose(green, [4.0, 2.0, 1.0])
    assert np.allclose(red, [1.0, 0.5, 0.25])


def test_micro_time_axis_from_data_and_binning():
    class _Header:
        micro_time_resolution = 32e-12  # 32 ps, in seconds

    model = FilterModel()
    mt = np.arange(0, 4096)
    # No binning: dt = resolution (ns) = 0.032; channel count unchanged.
    _, n_tac = model._micro_time_axis(_Header(), mt.copy(), 4096)
    assert n_tac == 4096
    assert abs(model._pattern_bin_width_ns() - 0.032) < 1e-9
    # Binning by 4 coarsens the axis and widens the bin width x4.
    model._micro_time_binning = 4
    out_mt, n_tac = model._micro_time_axis(_Header(), mt.copy(), 4096)
    assert n_tac == 1024
    assert out_mt.max() == 1023
    assert abs(model._pattern_bin_width_ns() - 0.128) < 1e-9


# -- stacked mode -----------------------------------------------------------------------------------


def test_stacked_mode_computes_global_filters_split_per_detector():
    model = seeded_model()
    detectors = list(model.detectors.selected)
    assert len(detectors) > 1
    # Default is independent per-detector filters.
    assert not model.stacked
    assert model._result_multi_detector
    assert all(
        entry["result"].metadata.get("filter_mode") != "stacked"
        for entry in model._result_multi_detector
    )

    model.stacked = True
    model.compute()
    found = model._result_multi_detector
    assert found and len(found) == len(detectors)
    for entry in found:
        result = entry["result"]
        assert result.metadata.get("filter_mode") == "stacked"
        assert result.metadata.get("stacked_detectors") == detectors
        assert result.n_bins == found[0]["result"].n_bins
        assert np.all(np.isfinite(result.filters))
        assert result.to_channel_filters().shape[0] == result.n_species


def test_stacked_mode_uses_the_interdetector_coupling():
    model = seeded_model()
    first = model.detectors.selected[0]

    def first_detector_filters():
        model.compute()
        entry = next(e for e in model._result_multi_detector if e["detector"] == first)
        return np.asarray(entry["result"].to_channel_filters(), dtype=float)

    model.stacked = False
    independent = first_detector_filters()
    model.stacked = True
    stacked = first_detector_filters()
    assert independent.shape == stacked.shape
    assert not np.allclose(independent, stacked)


# -- fit ranges -------------------------------------------------------------------------------------


def test_the_fit_range_drives_fit_range():
    model = FilterModel()
    model._fit_bounds = (30, 200)
    assert model._fit_range(256) == (30, 200)


def test_filters_computed_over_the_detector_fit_range_window():
    """Filters are solved on the fit-range slice: zero outside, and the reconstruction tracks the total there."""
    model = seeded_model()
    first = model.detectors.selected[0]
    model._detector_fit_ranges[first] = (40, 200)
    model.compute()
    result = next(e for e in model._result_multi_detector if e["detector"] == first)["result"]
    filters = np.asarray(result.filters)
    assert np.all(filters[:, :40] == 0.0) and np.all(filters[:, 200:] == 0.0)
    reconstruction, total = np.asarray(result.reconstruction), np.asarray(result.total_decay)
    assert np.allclose(reconstruction[:40], total[:40])
    assert np.allclose(reconstruction[200:], total[200:])


def test_filters_are_zeroed_outside_a_per_detector_fit_range():
    model = seeded_model()
    first = model.detectors.selected[0]
    model._detector_fit_ranges[first] = (50, 150)
    model.compute()
    filters = np.asarray(
        next(e for e in model._result_multi_detector if e["detector"] == first)["result"].filters
    )
    assert np.all(filters[:, :50] == 0.0) and np.all(filters[:, 150:] == 0.0)
    assert np.any(filters[:, 50:150] != 0.0)


def test_a_fit_range_change_re_zeros_the_stored_filters_without_a_refit():
    """Narrow then widen: the cached un-zeroed filters bring the columns back."""
    model = seeded_model()
    first = model.detectors.selected[0]

    def filters():
        entry = next(x for x in model._result_multi_detector if x["detector"] == first)
        return np.asarray(entry["result"].filters), entry["result"]

    model._fit_bounds = (60, 180)
    _, result = filters()
    model._apply_range_to_result(result, first)
    narrow, _ = filters()
    assert np.all(narrow[:, :60] == 0.0) and np.all(narrow[:, 180:] == 0.0)

    model._fit_bounds = (10, 250)
    model._apply_range_to_result(result, first)
    wide, _ = filters()
    assert np.any(wide[:, 10:60] != 0.0)
    assert np.all(wide[:, :10] == 0.0) and np.all(wide[:, 250:] == 0.0)


def test_residuals_are_masked_to_the_fit_range():
    model = FilterModel()
    model._fit_bounds = (30, 200)
    masked = model._mask_to_fit_range(np.ones(256, dtype=float))
    assert np.isnan(masked[:30]).all()
    assert np.isfinite(masked[30:200]).all()
    assert np.isnan(masked[200:]).all()


def test_a_masked_residual_range_is_not_drawn_across(qapp):
    """Residuals outside the fit window are NaN and must read as a gap (chiplot breaks lines at them)."""
    from chisurf.gui import chiplot as cp

    plot = cp.Plot()
    y = np.array([1.0, 2.0, np.nan, 4.0])
    handle = plot.line(np.arange(y.size), y)
    _, drawn = handle.get_data()
    assert np.isnan(drawn[2]) and np.isfinite(drawn[[0, 1, 3]]).all()


def test_fit_range_resets_for_new_data(tmp_path):
    total = 50000.0 * synthetic_decay(2000, 2.0, bin_width=0.05, normalize=True)
    path = tmp_path / "big.txt"
    np.savetxt(path, total)
    model = FilterModel()
    model.set_total_paths([path])
    # The range spans the new (2000-bin) data, not the stale 256-bin example.
    assert model._fit_bounds[1] > 500


def test_the_detector_irf_shift_moves_the_prompt_and_persists():
    model = FilterModel()
    detectors = model.detectors
    detector = detectors.selected[0]
    detectors.set_width(detector, 0.2)
    detectors.set_shift(detector, 0.0)  # the example starts with a small offset
    dt = model._pattern_bin_width_ns()

    peak0 = int(np.argmax(model._detector_irf(detector)))
    detectors.set_shift(detector, 0.5)  # +0.5 ns -> later by 0.5/dt bins
    peak1 = int(np.argmax(model._detector_irf(detector)))
    assert peak1 - peak0 == round(0.5 / dt)

    state = detectors.export_state()
    assert "shift" in state
    detectors.set_shift(detector, 0.0)
    detectors.import_state(state)
    assert abs(detectors.shift(detector) - 0.5) < 1e-9


# -- instrument -------------------------------------------------------------------------------------


def test_the_laser_period_drives_the_periodic_convolution():
    model = FilterModel()
    for attr in (
        "alpha", "beta", "gamma", "delta", "g_factor", "l1", "l2",
        "forster_radius", "period_ns", "periodic",
    ):  # fmt: skip
        assert hasattr(model.instrument_model, attr)
    # Periodic convolution: off -> None; on with 0 -> full micro-time window.
    assert model._fit_period_ns(256, 0.05) is None
    model.instrument_model.periodic = True
    assert model._fit_period_ns(256, 0.05) == 256 * 0.05
    model.instrument_model.period_ns = 12.5
    assert model._fit_period_ns(256, 0.05) == 12.5


def test_a_setup_calibration_prepopulates_the_instrument():
    model = FilterModel()
    model.set_setup(
        {
            "detectors": {"green": {}},
            "calibration": {"alpha": 0.02, "gamma": 0.9, "g_factor": 1.15},
        }
    )
    assert model.instrument_model.alpha == 0.02
    assert model.instrument_model.gamma == 0.9
    assert model.instrument_model.g_factor == 1.15


def test_a_calibration_measured_once_arrives_here():
    """The Accurate FRET tool's alpha/beta/gamma/delta, stored on the setup, fill the instrument."""
    from chisurf.core.fluorescence.fret.calibration import (
        CalibrationParameters,
        calibration_to_setup,
    )

    calib = CalibrationParameters()
    calib.gamma, calib.alpha, calib.beta, calib.delta, calib.r0 = 0.65, 0.08, 1.4, 0.06, 54.0
    model = FilterModel()
    model.set_setup(
        {"detectors": {"green": {}, "red": {}}, "fret_calibration": calibration_to_setup(calib)}
    )
    assert model.instrument_model.gamma == pytest.approx(0.65)
    assert model.instrument_model.alpha == pytest.approx(0.08)
    assert model.instrument_model.beta == pytest.approx(1.4)
    assert model.instrument_model.delta == pytest.approx(0.06)
    assert model.instrument_model.forster_radius == pytest.approx(54.0)  # stored as r0
    assert model._calibration_seed()["gamma"] == pytest.approx(0.65)


def test_the_acceptor_excitation_channel_is_not_switched_off_by_default():
    """beta is the excitation-flux ratio: it defaults to 1, or the yellow pattern comes out zero."""
    from chisurf.core.fluorescence.fret.species_decay import fret_species_detector_patterns
    from chisurf.plugins.fcs.fcs_filter_calculator.gui_parts.instrument_options import DEFAULTS

    assert DEFAULTS["beta"] == 1.0
    source = {
        "model": "fret_species",
        "state": "da",
        "donor_spectrum": [1.0, 4.0],
        "acceptor_spectrum": [1.0, 2.0],
        "fret_mode": "efficiency",
        "transfer_efficiency": 0.5,
        "bin_width": 0.032,
        "crosstalk": {k: DEFAULTS[k] for k in ("alpha", "beta", "gamma", "delta")},
    }
    patterns = fret_species_detector_patterns(source, DETECTORS, 256)
    assert np.sum(patterns["yellow"]) > 0.0


# -- auto-fit -------------------------------------------------------------------------------------


def lifetimes(model):
    return sorted(c.source["lifetimes"][0] for c in model.components)


def test_auto_fit_adds_lifetime_components(tmp_path):
    model = autofit_model(tmp_path)
    assert len(model.components) == 2
    taus = lifetimes(model)
    assert abs(taus[0] - 1.2) < 0.2
    assert abs(taus[1] - 4.0) < 0.4


def test_auto_fit_joint_irf_fit_resolves_distinct_components(tmp_path):
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    # An IRF-convolved bi-exponential with a real prompt at ~bin 14. With no measured IRF
    # loaded the IRF is fitted jointly and both lifetimes are resolved.
    t = np.arange(256) * 0.05
    irf = synthetic_irf(t, center_ns=0.7, fwhm_ns=0.35)
    total = 60000.0 * synthetic_decay(
        256, 1.2, bin_width=0.05, irf=irf, normalize=True
    ) + 40000.0 * synthetic_decay(256, 4.0, bin_width=0.05, irf=irf, normalize=True)
    total_path = tmp_path / "mix.txt"
    np.savetxt(total_path, total)

    model = FilterModel(example=False)
    model.detectors.selected = ["green"]
    model.set_total_paths([total_path])
    model._fit_bounds = (0, 255)
    width_before = model.detectors.width("green")
    model._auto_fit_components(n_components=2)

    assert len(model.components) == 2
    taus = lifetimes(model)
    assert abs(taus[0] - 1.2) < 0.3
    assert abs(taus[1] - 4.0) < 0.6
    assert taus[1] - taus[0] > 1.0  # two DISTINCT lifetimes, not collapsed to one
    # No measured IRF -> the IRF width was fitted and written back to the detector.
    assert abs(model.detectors.width("green") - width_before) > 1e-4
    source = model.components[0].source
    assert source["start_bin"] == 0
    assert "patterns_by_detector" in source


def test_auto_fit_fits_irf_when_no_measured_irf():
    model = FilterModel()
    names = list(model.detectors.selected)
    for name in names:
        assert model._measured_irf_vector(name) is None
    before = {n: model.detectors.width(n) for n in names}
    model._auto_fit_settings = {"kind": "lifetime", "n_components": 2, "tau_min": 0.2, "tau_max": 8.0}
    model._auto_fit_components(n_components=2)
    after = {n: model.detectors.width(n) for n in names}
    assert any(abs(after[n] - before[n]) > 1e-4 for n in names), "IRF width was not fitted"


def test_auto_fit_on_file_backed_total_with_nondefault_bins(tmp_path):
    """File-backed data whose bin count differs from 256 must not break the synthetic IRF."""
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    t = np.arange(2048) * 0.05
    irf = synthetic_irf(t, center_ns=0.9, fwhm_ns=0.3, shape=0.3)
    total = 60000.0 * synthetic_decay(
        2048, 1.2, bin_width=0.05, irf=irf, normalize=True
    ) + 40000.0 * synthetic_decay(2048, 4.0, bin_width=0.05, irf=irf, normalize=True)
    path = tmp_path / "mix.txt"
    np.savetxt(path, total)

    model = FilterModel(example=False)
    model.detectors.selected = list(DETECTORS)
    model.set_total_paths([path])
    assert model._total_vector is None and model._current_n_bins() == 2048
    model._auto_fit_components(n_components=2)  # must not raise
    assert len(model.components) == 2


def test_fret_autofit_creates_fret_species():
    model = FilterModel(example=False)
    # Fitted donor lifetimes 2.0 & 4.0 ns -> FRET species with E 0.5 and 0 (tau_D0 = 4).
    model._suspend_compute = True
    model._add_fret_autofit_species(
        amps=np.array([0.5, 0.5]),
        taus=np.array([2.0, 4.0]),
        scale=1.0,
        dt=0.05,
        start=5,
        n_bins=256,
        detector_names=DETECTORS,
    )
    model._suspend_compute = False
    assert len(model.components) == 2
    assert all(c.source["model"] == "fret_species" for c in model.components)
    efficiencies = sorted(c.source["transfer_efficiency"] for c in model.components)
    assert abs(efficiencies[0] - 0.0) < 1e-2 and abs(efficiencies[1] - 0.5) < 0.05
    assert all("patterns_by_detector" in c.source for c in model.components)


def test_auto_fit_settings_drive_kind_and_bounds(tmp_path):
    total = 60000.0 * synthetic_decay(1024, 1.5, bin_width=0.05, normalize=True) + 40000.0 * synthetic_decay(
        1024, 4.5, bin_width=0.05, normalize=True
    )
    path = tmp_path / "mix.txt"
    np.savetxt(path, total)
    model = FilterModel(example=False)
    model.detectors.selected = ["green"]
    model.set_total_paths([path])
    model._fit_bounds = (10, 1000)

    # Persistent settings default to 2 lifetime components.
    assert model._auto_fit_settings["kind"] == "lifetime"
    assert model._auto_fit_settings["n_components"] == 2

    # FRET mode via settings -> FRET species.
    model._auto_fit_settings["kind"] = "fret"
    model._auto_fit_components(n_components=2)
    assert {c.source["model"] for c in model.components} == {"fret_species"}


def test_auto_fit_runs_through_a_real_fit_object(tmp_path):
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.description import for_family

    result = autofit_model(tmp_path)._auto_fit_result
    assert isinstance(result["fit"], Fit)
    assert isinstance(result["model"], for_family("tcspc_lifetime"))


def fitted_parameters(model):
    """The rows the Auto-fit tab lists (the panel's own filter)."""
    from types import SimpleNamespace

    from chisurf.plugins.fcs.fcs_filter_calculator.gui.panel import FilterPanel  # noqa: F401

    panel = FilterPanel(SimpleNamespace(model=model, editing_blocked=False))
    return [row["_parameter"] for row in FilterPanel.parameter_rows(panel)]


def test_autofit_parameters_are_the_fitted_ones(tmp_path):
    from chisurf.core.fitting.parameter import FittingParameter

    model = autofit_model(tmp_path)
    names = {getattr(p, "name", "") for p in fitted_parameters(model)}
    # Two components -> two lifetimes and two amplitudes, and no third.
    assert {"t0", "t1", "a0", "a1"} <= names
    assert not names & {"t2", "a2"}
    assert all(
        isinstance(p, FittingParameter) for p in fitted_parameters(model) if p.name in {"t0", "a0"}
    )


def test_autofit_parameters_can_be_linked(tmp_path):
    """What the model-backed fit buys: results that link to another fit."""

    def tau0(model):
        return next(
            p
            for p in model._auto_fit_result["model"].parameters_all
            if getattr(p, "canonical_id", "") == "lifetime.tau.0"
        )

    target = tau0(autofit_model(tmp_path / "a"))
    follower = tau0(autofit_model(tmp_path / "b"))
    follower.link = target
    assert follower.is_linked
    target.value = 2.345
    assert follower.value == pytest.approx(2.345)


def test_fret_auto_fit_runs_through_a_real_fret_model(tmp_path):
    from chisurf.core.models.description import for_family

    model = autofit_model(tmp_path, n_components=2, kind="fret")
    result = model._auto_fit_result
    assert isinstance(result["model"], for_family("tcspc_fret_gaussian"))
    assert len(result["distances"]) == 2
    assert np.all(result["efficiencies"] >= 0) and np.all(result["efficiencies"] <= 1)
    sources = [c.source for c in model.components]
    assert sources and all(s["model"] == "fret_species" for s in sources)
    assert all("transfer_efficiency" in s for s in sources)


def test_fret_auto_fit_exposes_distances_as_linkable_parameters(tmp_path):
    from chisurf.core.fitting.parameter import FittingParameter

    model = autofit_model(tmp_path, n_components=2, kind="fret")
    means = [
        p
        for p in model._auto_fit_result["model"].parameters_all
        if getattr(p, "canonical_id", "").startswith("distance.mean.")
    ]
    assert len(means) == 3  # the model holds as many as it could use
    assert all(isinstance(p, FittingParameter) for p in means)
    names = {getattr(p, "name", "") for p in fitted_parameters(model)}
    assert {"RDA0", "RDA1"} <= names and "RDA2" not in names, names


def test_derived_fret_efficiencies_are_available_without_a_fret_fit():
    """The lifetime -> E fallback: E = 1 - tau/tau_D0 with tau_D0 = max(tau)."""
    taus = np.array([2.0, 4.0])
    derived = [float(np.clip(1.0 - t / 4.0, 0.0, 0.999)) for t in taus]
    assert derived == pytest.approx([0.5, 0.0])
    assert hasattr(FilterModel, "_add_fret_autofit_species")
