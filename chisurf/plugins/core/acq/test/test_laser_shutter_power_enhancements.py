"""Tests for 1 mW max power calibration, Full pwr button, threshold warning,
combined Laser & Shutter dock, and foldable settings.
"""
from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_max_power_1mw_calibrated_on_start(tmp_path):
    """Simulator connects and calibrates max power to 1000 µW (1 mW) on start."""
    model = RecordModel(output_dir=tmp_path)
    assert model.connect_instrument_simulator()
    try:
        green_pts = model.power_book.points("Green 488 nm")
        red_pts = model.power_book.points("Red 640 nm")
        assert len(green_pts) >= 2
        assert green_pts[0][1] == 0.0
        assert green_pts[-1][1] == 1000.0  # 1 mW = 1000 µW
        assert len(red_pts) >= 2
        assert red_pts[-1][1] == 1000.0
    finally:
        model.close()


def test_calibrate_max_power_closes_detector_shutters(tmp_path):
    """During max power calibration, detector shutters must strictly be closed."""
    model = RecordModel(output_dir=tmp_path)
    assert model.connect_instrument_simulator()
    try:
        # Open all shutters initially
        model.set_shutter("Excitation", True)
        model.set_shutter("Green", True)
        model.set_shutter("Red", True)

        history = []
        orig_set_shutters = model._set_shutters

        def tracking_set_shutters(states):
            history.append(dict(states))
            return orig_set_shutters(states)

        model._set_shutters = tracking_set_shutters
        assert model.calibrate_max_power(max_uw=1000.0)

        # First call to _set_shutters inside calibrate_max_power should close detector shutters
        assert len(history) >= 2
        assert history[0].get("Green") is False
        assert history[0].get("Red") is False
    finally:
        model.close()


def test_full_power_button_calibrated(tmp_path):
    """Clicking 'Full pwr' on a calibrated laser requests max power (1000 µW)."""
    model = RecordModel(output_dir=tmp_path)
    assert model.connect_instrument_simulator()
    app = RecordApp(model)
    try:
        app.focus_dock("laser")
        ui = Driver(app, (1500, 950))
        ui.draw(3)

        assert "laser_full_200" in app.item_rects
        assert "laser_full_300" in app.item_rects

        # Click Full pwr on slot 200
        ui.click("laser_full_200")
        ui.draw(3)

        assert app._head_targets[200] == 1000.0
        assert model.power_target_uw == 1000.0
    finally:
        app.close()


def test_full_power_button_uncalibrated(tmp_path):
    """Clicking 'Full pwr' on an uncalibrated laser sets drive to 100%."""
    model = RecordModel(output_dir=tmp_path)
    assert model.connect_instrument_simulator()
    model.power_book.records.clear()  # uncalibrated
    app = RecordApp(model)
    try:
        app.focus_dock("laser")
        ui = Driver(app, (1500, 950))
        ui.draw(3)

        ui.click("laser_full_200")
        ui.draw(3)

        head = next(h for h in model.laser.state().heads if h.slot == 200)
        assert head.intensity_pct == 100.0
    finally:
        app.close()


def test_drive_percentage_shown_and_threshold_warning(tmp_path):
    """Calibrated laser displays drive percentage and warns when near threshold (<=45%)."""
    model = RecordModel(output_dir=tmp_path)
    assert model.connect_instrument_simulator()
    app = RecordApp(model)
    try:
        app.focus_dock("laser")
        ui = Driver(app, (1500, 950))
        ui.draw(3)

        # Drive percentage rect exists
        assert "laser_drive_pct_200" in app.item_rects

        # Initially at 0%, so stable / off
        assert any("Drive:" in s for s in ui.strings())

        # Set drive to 30% (threshold unstable regime: 0 < drive <= 45%)
        model.laser.set_head(200, intensity_pct=30.0)
        model.power_poll(force=True)
        ui.draw(2)

        strings = ui.strings()
        assert any("near threshold" in s for s in strings)
    finally:
        app.close()


def test_combined_laser_and_shutter_dock(tmp_path):
    """Laser and shutters are combined into 'Laser & Shutter' dock."""
    model = RecordModel(output_dir=tmp_path)
    assert model.connect_instrument_simulator()
    app = RecordApp(model)
    try:
        laser_win = app.docks.window("laser")
        assert laser_win is not None
        assert laser_win.title == "Laser & Shutter"

        # Alias works
        assert app.docks.window("shutters") is laser_win
        app.focus_dock("shutters")
        assert app.docks.is_shown("laser")

        ui = Driver(app, (1500, 950))
        ui.draw(3)

        # Both laser controls and shutter controls are rendered in the same dock
        strings = ui.strings()
        assert "Green 488 nm" in strings
        assert "Excitation" in strings
        assert "diode_raw" in strings
    finally:
        app.close()


def test_foldable_settings_present(tmp_path):
    """Session, Running trace, and Shutters & Diode expose foldable sections."""
    model = RecordModel(output_dir=tmp_path)
    assert model.connect_instrument_simulator()
    app = RecordApp(model)
    try:
        app.focus_dock("laser")
        ui = Driver(app, (1500, 950))
        ui.draw(3)

        assert "Shutters & Diode.fold" in app.item_rects

        app.focus_dock("acquisition")
        ui.draw(3)
        assert "Session.fold" in app.item_rects

        app.focus_dock("analysis")
        ui.draw(3)
        assert "Running trace.fold" in app.item_rects
    finally:
        app.close()
