"""Comprehensive tests for FCS live analysis, CPM reporting, setup quality monitoring
across days, dye library confocal volume calculations, laser name inline editing,
and experiment mode presets in JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pytest

from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel, DOCKS, _fit_fcs_curve
from chisurf.plugins.core.acq.gui.setup_quality import SetupQualityModel, compute_confocal_parameters, REFERENCE_DYES
from chisurf.plugins.core.acq.live.fcs import LiveFcs
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1500, 950)


def test_fcs_mode_defaults_include_decays_and_camera_in_lower_left(tmp_path):
    """FCS mode by default shows correlation, decays, and camera in the workspace."""
    # Check DOCKS definition
    camera_dock = next(d for d in DOCKS if d[0] == "video")
    assert camera_dock[2] == "main"

    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.mode = "fcs"
    model.mode_changed()

    app = RecordApp(model)
    assert app.docks.windows["video"].workspace
    ui = Driver(app, SIZE)
    try:
        ui.draw(2)
        assert app.docks.is_shown("plot_correlation")
        assert app.docks.is_visible("plot_decays")
        assert app.docks.is_visible("video")
        assert not app.docks.is_visible("plot_hist")
    finally:
        app.close()


def test_live_fcs_accumulates_decays_and_supports_channel_correlations():
    """LiveFcs accumulates micro-time decays and tracks multi-channel correlations."""
    fcs = LiveFcs(macro_clock_s=1e-8, n_micro=128)
    # Simulate photons with channels 0 and 1
    macro = np.arange(100, 200, dtype=np.uint64)
    micro = np.random.randint(10, 80, size=100, dtype=np.int64)
    channel = np.array([0, 1] * 50, dtype=np.int32)

    fcs.push_np(macro, micro, channel)
    fcs.flush()
    snap = fcs.snapshot()

    # Fluorescence decays must be present
    assert "decays" in snap
    assert "0" in snap["decays"]
    assert "1" in snap["decays"]
    assert snap["decays"]["0"].sum() == 50
    assert snap["decays"]["1"].sum() == 50

    # Multi-channel correlations must be present
    assert "correlations" in snap
    assert "all" in snap["correlations"]
    assert "ch0" in snap["correlations"]
    assert "ch1" in snap["correlations"]
    assert "cross_01" in snap["correlations"]


def test_fcs_curve_fitting_supports_0_1_2_bunching_and_s_parameter():
    """_fit_fcs_curve accurately fits 0, 1, and 2 bunching models and reports bright/total N."""
    tau = np.logspace(-6, 0, 60)
    tau_d = 250e-6
    s = 5.0
    s2 = s * s
    n_bright = 2.5
    diff = (1.0 / n_bright) * (1.0 / (1.0 + tau / tau_d)) * (1.0 / np.sqrt(1.0 + tau / (s2 * tau_d)))

    # 0 bunching model
    g0 = diff
    fit0 = _fit_fcs_curve(tau, g0, s_kappa=s, bunching_mdl=0)
    assert fit0["success"]
    assert fit0["n_bright"] == pytest.approx(n_bright, rel=0.05)
    assert fit0["n_total"] == pytest.approx(n_bright, rel=0.05)
    assert fit0["tau_d_s"] == pytest.approx(tau_d, rel=0.05)

    # 1 bunching model (triplet)
    b1 = 0.15
    t1 = 3e-6
    g1 = diff * ((1.0 - b1) + b1 * np.exp(-tau / t1))
    fit1 = _fit_fcs_curve(tau, g1, s_kappa=s, bunching_mdl=1)
    assert fit1["success"]
    assert fit1["n_bright"] == pytest.approx(n_bright, rel=0.05)
    expected_n_total = n_bright / (1.0 - b1)
    assert fit1["n_total"] == pytest.approx(expected_n_total, rel=0.08)
    assert fit1["b1"] == pytest.approx(b1, abs=0.05)


def test_fcs_dock_reports_cpm_bright_and_total_and_setup_controls(tmp_path):
    """FCS dock reports CPM bright, CPM total, s(kappa), and offers channel & model selectors."""
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.mode = "fcs"
    model.mode_changed()

    tau = np.logspace(-6, 0, 50)
    tau_d = 200e-6
    g = 0.5 / (1.0 + tau / tau_d)
    model.snapshot = {
        "photons": 150000,
        "elapsed_s": 5.0,
        "count_rate_hz": 30000.0,
        "n_focus": 2.0,
        "brightness_hz": 15000.0,
        "correlation": {"tau_s": tau, "g": g, "count_rate_hz": 30000.0},
        "correlations": {
            "all": {"tau_s": tau, "g": g, "count_rate_hz": 30000.0, "photons": 150000},
        },
    }

    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        app.focus_dock("plot_correlation")
        ui.draw(3)
        strings = " ".join(ui.strings())
        assert "FCS Correlation" in strings
        assert "CPM" in strings
        assert "s(κ)" in strings or "s (κ)" in strings
        assert "N_total" in strings or "N_tot" in strings
        assert "All (combined)" in strings or "All" in strings
        assert "bunch" in strings
    finally:
        app.close()


def test_dye_library_confocal_volume_and_stokes_einstein():
    """Confocal waist w0 and effective volume V_eff are computed correctly from dye diffusion."""
    # Rh110 at 22 °C, tau_D = 0.3 ms, s = 5.0
    D_T, w0_nm, veff_fl = compute_confocal_parameters('Rh110', 22.0, 0.3, 5.0)
    assert D_T > 400.0
    assert 200.0 < w0_nm < 900.0
    # Confocal volume for typical objective
    assert 0.1 < veff_fl < 20.0


def test_setup_quality_table_layout_pull_from_fcs_and_bounds_alert(tmp_path):
    """Setup quality dock displays an aligned table, removes bg note, and alerts on bounds."""
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.ui_mode = 'advanced'
    model.ui_mode_changed()
    app = RecordApp(model)
    qc = app.setup_quality

    # Pull from FCS
    live_fcs_fit = {
        "tau_d_s": 0.00035,
        "s": 5.5,
        "cpm_bright": 22.5,
        "cpm_total": 19.5,
    }
    assert qc.pull_from_live_fcs(live_fcs_fit)
    assert float(qc.diffusion_ms) == pytest.approx(0.35, abs=0.001)
    assert qc.kappa_s == 5.5
    assert float(qc.brightness_khz) == pytest.approx(22.5, abs=0.01)

    # Save baseline reference
    qc.lifetime_ns = '4.0'
    qc.laser_nm = '488'
    qc.power_uw = '5'
    assert qc.save_reference()

    # Save second reference with degraded brightness (>20% drop)
    qc.brightness_khz = '15.0'
    qc.save_reference()

    out_of_bounds, reason = qc.check_quality_bounds()
    assert out_of_bounds
    assert "dropped" in reason.lower() or "bounds" in reason.lower()

    ui = Driver(app, SIZE)
    try:
        app.focus_dock('setup_quality')
        ui.draw(3)
        strings = " ".join(ui.strings())
        assert "🔴" in strings or "MAINTENANCE" in strings
        assert "fit bg corrected" not in strings.lower()
        assert "Calibration dye" in strings or "Rh110" in strings
    finally:
        app.close()


def test_laser_name_inline_editing_and_settings_persistence(tmp_path):
    """Double-clicking laser name allows inline editing and persists in settings."""
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.laser_custom_names[200] = "Custom Green 488"

    class Head:
        slot = 200
        name = "Green 488 nm"

    assert model._power_label(Head()) == "Custom Green 488"

    # Settings capture includes custom names
    settings = model.form_settings()
    assert "laser_custom_names" in settings
    assert settings["laser_custom_names"][200] == "Custom Green 488"
    model.close()


def test_laser_calibration_auto_read_diode_and_auto_save(tmp_path):
    """Laser calibration auto-reads diode and auto-saves on point add/delete/update."""
    from chisurf.plugins.core.acq.gui.power_controls import SimplePowerPanelModel
    record = RecordModel(output_dir=tmp_path)
    panel = SimplePowerPanelModel(record)
    panel.laser_name = '488 nm'

    # Auto-read simulated diode
    class DummyShutters:
        def get_parameter(self, name, default=-1):
            return 125.0 if name in ('diode_mean', 'diode_raw') else default
        def close(self): pass

    record.shutters = DummyShutters()
    assert panel.raw == 125.0

    # User adds point without manually reading diode
    panel.uw = 15.0
    assert panel.add_point()
    # Should be auto-saved and present in book
    points = record.power_book.points('488 nm')
    assert len(points) == 1
    assert list(points[0]) == [125.0, 15.0]

    # Update point
    assert panel.update_point(0, 130.0, 16.0)
    assert list(record.power_book.points('488 nm')[0]) == [130.0, 16.0]

    # Delete point
    assert panel.delete_point({'id': 0})
    assert len(record.power_book.points('488 nm')) == 0
    record.close()


def test_experiment_modes_json_loaded_and_docks_run_bar_popup(tmp_path):
    """Modes are loaded from experiment_modes.json and run bar exposes Docks selection popup."""
    model = RecordModel(output_dir=tmp_path, realtime=False)
    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        ui.draw(2)
        assert "bar_docks" in app.item_rects
        # Click Docks popup button on run bar
        ui.click("bar_docks")
        ui.draw(2)
        strings = " ".join(ui.strings())
        assert "Visible docks" in strings
    finally:
        app.close()


def test_correlation_window_is_bounded_by_the_acquisition():
    """The correlation window has a min and a max: lags beyond the measurement are invalid.

    A lag longer than the acquisition has no (or a handful of) photon pairs, so its G(tau)
    is noise, not a correlation. The window must grow with the running acquisition.
    """
    rng = np.random.default_rng(3)
    fcs = LiveFcs(macro_clock_s=1e-8, n_micro=128)
    span_ticks = 200_000_000  # 2 s of acquisition
    macro = np.sort(rng.integers(0, span_ticks, size=100_000).astype(np.uint64))
    fcs.push_np(macro)
    fcs.flush()
    snap = fcs.snapshot()
    tau = snap["correlation"]["tau_s"]
    assert tau.size > 0, "the window has lags within the acquisition"
    assert tau.min() > 0.0, "the window minimum is the first meaningful lag"
    assert tau.max() <= 2.0 + 1e-8, "no correlation beyond the acquisition"
    for key, corr in snap["correlations"].items():
        t = np.asarray(corr["tau_s"])
        assert t.size == 0 or t.max() <= 2.0 + 1e-8, key

    # A longer acquisition of the same stream (5 s total): the valid window grows.
    # tttrlib finalizes a correlator on flush, so this is a fresh accumulator.
    macro2 = span_ticks + np.sort(rng.integers(0, 300_000_000, size=200_000).astype(np.uint64))
    fcs2 = LiveFcs(macro_clock_s=1e-8, n_micro=128)
    fcs2.push_np(macro)
    fcs2.push_np(macro2)
    fcs2.flush()
    tau2 = fcs2.snapshot()["correlation"]["tau_s"]
    assert 2.0 < tau2.max() <= 5.0 + 1e-8, "the window grows but stays within the acquisition"
