"""Tests for experiment-type presets, dedicated docks (smFRET, FCS, Pol, Image),
real-time analysis cards, and layout switching.
"""
from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel, DOCKS
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1500, 950)


def test_mode_options_exposes_all_experiment_types(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    options = dict(model.mode_options())
    assert "point" in options
    assert "fcs" in options
    assert "pol" in options
    assert "image" in options
    assert "smFRET" in options["point"]
    assert "FCS" in options["fcs"]
    assert "Polarization" in options["pol"]
    model.close()


def test_docks_contain_dedicated_correlation_and_polarization_windows(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    app = RecordApp(model)
    try:
        dock_keys = [key for key, _title, _region in DOCKS]
        assert "plot_hist" in dock_keys
        assert "plot_correlation" in dock_keys
        assert "plot_polarization" in dock_keys
        assert "plot_image" in dock_keys
        assert app.docks.window("plot_correlation") is not None
        assert app.docks.window("plot_polarization") is not None
    finally:
        app.close()


def test_switching_modes_toggles_appropriate_dock_presets(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        ui.draw(2)
        # Default mode is point (smFRET)
        assert app.docks.is_shown("plot_hist")
        assert not app.docks.is_shown("plot_correlation")
        assert not app.docks.is_shown("plot_polarization")
        assert not app.docks.is_shown("plot_image")

        # Switch to FCS
        model.mode = "fcs"
        model.mode_changed()
        ui.draw(2)
        assert app.docks.is_shown("plot_correlation")
        assert app.docks.is_visible("plot_decays")
        assert app.docks.is_visible("video")
        assert not app.docks.is_visible("plot_hist")
        assert not app.docks.is_visible("plot_polarization")
        assert not app.docks.is_visible("plot_image")
        assert not app.docks.is_visible("plot_trace")

        # Switch to Polarization
        model.mode = "pol"
        model.mode_changed()
        ui.draw(2)
        assert app.docks.is_shown("plot_polarization")
        assert app.docks.is_visible("plot_decays")
        assert app.docks.is_visible("plot_trace")
        assert not app.docks.is_visible("plot_hist")
        assert not app.docks.is_visible("plot_correlation")
        assert not app.docks.is_visible("plot_image")

        # Switch to Image
        model.mode = "image"
        model.mode_changed()
        ui.draw(2)
        assert app.docks.is_shown("plot_image")
        assert app.docks.is_visible("points")
        assert not app.docks.is_visible("plot_hist")
        assert not app.docks.is_visible("plot_correlation")
        assert not app.docks.is_visible("plot_polarization")

        # Switch back to smFRET (point)
        model.mode = "point"
        model.mode_changed()
        ui.draw(2)
        assert app.docks.is_shown("plot_hist")
        assert app.docks.is_visible("plot_trace")
        assert app.docks.is_visible("plot_decays")
        assert not app.docks.is_visible("plot_correlation")
        assert not app.docks.is_shown("plot_polarization")
        assert not app.docks.is_shown("plot_image")
    finally:
        app.close()


def test_fcs_dock_displays_amplitude_brightness_diffusion_time_and_curve(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.mode = "fcs"
    model.mode_changed()

    tau = np.logspace(-6, 0, 50)
    # Synthetic correlation curve with G(0) = 0.5 (N = 2) and tau_D = 200 µs
    tau_d = 200e-6
    g = 0.5 / (1.0 + tau / tau_d)
    model.snapshot = {
        "photons": 150000,
        "elapsed_s": 5.0,
        "count_rate_hz": 30000.0,
        "n_focus": 2.0,
        "brightness_hz": 15000.0,
        "correlation": {"tau_s": tau, "g": g},
    }

    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        app.focus_dock("plot_correlation")
        ui.draw(3)
        strings = " ".join(ui.strings())
        assert "FCS Correlation" in strings
        assert "N ≈ 2" in strings
        assert "15.0 kHz/mol" in strings
        # Diffusion time should be estimated around 200 µs
        assert "µs" in strings
        assert "30.0 kHz" in strings
    finally:
        app.close()


def test_fcs_dock_displays_throttling_warning_under_heavy_load(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.mode = "fcs"
    model.mode_changed()
    model.snapshot = {
        "photons": 5000000,
        "elapsed_s": 2.0,
        "correlator_throttled": True,
        "correlation": {},
    }

    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        app.focus_dock("plot_correlation")
        ui.draw(3)
        strings = " ".join(ui.strings())
        assert "correlator throttled" in strings.lower()
        assert "Recorded photons are intact" in strings
    finally:
        app.close()


def test_polarization_dock_displays_anisotropy_lifetime_and_helper(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.mode = "pol"
    model.mode_changed()

    # Synthetic decays with 100 channels: parallel = 2400 cts, perp = 1000 cts
    decay_par = np.zeros(128, dtype=float)
    decay_perp = np.zeros(128, dtype=float)
    # Exponential decay tail
    t = np.arange(128)
    decay_par = 500.0 * np.exp(-t / 30.0)
    decay_perp = 250.0 * np.exp(-t / 30.0)

    model.snapshot = {
        "photons": 10000,
        "elapsed_s": 1.0,
        "decays": {
            "0": decay_par,
            "1": decay_perp,
        },
    }

    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        app.focus_dock("plot_polarization")
        ui.draw(3)
        strings = " ".join(ui.strings())
        assert "Polarization" in strings
        assert "r =" in strings
        assert "r_app =" in strings
        assert "τ ≈" in strings
        assert "G = 1.000" in strings
        assert "Ströhl" in strings or "2018" in strings
    finally:
        app.close()


def test_smfret_dock_displays_overload_warning_when_analysis_dropped(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.mode = "point"
    model.mode_changed()
    model.snapshot = {
        "photons": 1000000,
        "elapsed_s": 1.0,
        "bursts": 0,
        "burst_rate_hz": 0.0,
        "live_analysis_dropped": True,
    }

    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        app.focus_dock("plot_hist")
        ui.draw(3)
        strings = " ".join(ui.strings())
        assert "Live burst analysis not possible" in strings
        assert "raw photons are intact" in strings
    finally:
        app.close()


def test_laser_power_dock_does_not_render_duplicate_sliders_in_advanced_mode(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.ui_mode = "advanced"
    model.ui_mode_changed()

    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        app.focus_dock("laser")
        ui.draw(2)
        ui.click("connect_laser")
        ui.draw(2)
        assert model.laser_connected
        # Rects should have laser_drive_200 / 300 from cards
        assert "laser_drive_200" in app.item_rects or "laser_target_200" in app.item_rects
        # Verify laser_power rect is tracked
        assert "laser_power" in app.item_rects
    finally:
        app.close()


def test_run_bar_exposes_experiment_and_user_mode_selectors(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        ui.draw(2)
        assert "bar_mode" in app.item_rects
        assert "bar_ui_mode" in app.item_rects
        strings = " ".join(ui.strings())
        assert "Experiment:" in strings
        assert "Mode:" in strings

        # On narrow host (< 850px), toolbar keeps core buttons and omits extra dropdowns to prevent clipping
        ui_narrow = Driver(app, (700, 650))
        ui_narrow.draw(2)
        assert "bar_mode" not in app.item_rects
        assert "start_pause" in app.item_rects
        assert "stop" in app.item_rects
    finally:
        app.close()


def test_polarization_dock_helper_channels(tmp_path):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.mode = "pol"
    model.mode_changed()
    app = RecordApp(model)
    ui = Driver(app, SIZE)
    try:
        app.focus_dock("plot_polarization")
        ui.draw(2)
        ui.click_text("> Calibration helper: G-factor & l1/l2 (Ströhl et al. 2018)")
        ui.draw(2)
        strings = " ".join(ui.strings())
        assert "Parallel ch (∥)" in strings
        assert "Perp ch (⊥)" in strings
    finally:
        app.close()

