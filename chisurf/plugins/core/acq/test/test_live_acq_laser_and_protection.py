"""Tests for:
1. Laser adjustments during acquisition (power target, drive, on/off).
2. Top-right Test Mode button (prevents disk writes) and acquisition indicator.
3. Auto-opening shutters on start and 1 MHz overcount protection in simple/basic mode with override.
4. Multi-laser diode offset compensation when adjusting power with other diodes on.
5. Laser controls UI (concise display with tooltips).
"""
import time
import pytest
import numpy as np

from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def make_app(tmp_path, ui_mode="simple"):
    m = RecordModel(output_dir=tmp_path, realtime=False)
    assert m.connect_instrument_simulator()
    m.ui_mode = ui_mode
    m.ui_mode_changed()
    app = RecordApp(m)
    return app, m


def test_adjust_laser_power_and_drive_during_acquisition(tmp_path):
    """Laser targets and drive can be adjusted during an active acquisition without dropping or stopping."""
    app, m = make_app(tmp_path, ui_mode="advanced")
    try:
        # Start an acquisition
        assert m.start(), m.status_detail
        assert m.running

        # 1. Adjust drive directly while running
        from chisurf.plugins.core.acq.gui.laser_cards import _set_drive, _request
        _set_drive(m, 200, 35.0)
        assert m.laser.state().heads[0].intensity_pct == pytest.approx(35.0)
        assert m.running

        # 2. Adjust target power while running (with other head off or on)
        assert _request(m, 200, 250.0), m.power_message
        assert m.power_servo is not None and m.power_servo.active
        # Settle the servo
        m.power_servo.settle_s = 0
        end = time.monotonic() + 5
        while m.power_servo.active and time.monotonic() < end:
            m.power_poll(force=True)
            time.sleep(0.005)
        assert m.power_servo.status == "reached", m.power_message
        assert m.running
    finally:
        if m.running:
            m.stop()
        app.close()


def test_test_mode_button_and_acq_indicator(tmp_path):
    """Test mode button in top right prevents disk writes; indicator shows TEST vs REC vs IDLE."""
    app, m = make_app(tmp_path, ui_mode="simple")
    ui = Driver(app, (1400, 850))
    try:
        ui.draw(3)
        # Verify test mode button and acq indicator rects exist
        assert "test_mode" in app.item_rects
        assert "acq_indicator" in app.item_rects

        # Initially idle
        assert any("○ IDLE" in s for s in ui.strings())
        assert not m.test_mode

        # Click test mode button
        ui.click("test_mode")
        assert m.test_mode is True

        # Start acquisition in test mode
        assert m.start()
        assert m.running
        assert m.saved_path is None
        assert not m.recorded_paths
        assert "Testing" in m.status_text or "Test" in m.status_detail

        ui.draw(2)
        strings = ui.strings()
        assert any("● TEST" in s for s in strings)
        assert not any("● REC" in s for s in strings)

        # Stop acquisition
        m.stop()
        if m.session:
            m.session.wait(5)
        m.poll(force=True)
        assert not m.running
        ui.draw(2)
        assert any("○ IDLE" in s for s in ui.strings())

        # Toggle test mode off
        ui.click("test_mode")
        assert m.test_mode is False

        # Start normal recording
        assert m.start()
        assert m.running
        assert m.saved_path is not None
        assert m.saved_path in m.recorded_paths
        assert "Recording" in m.status_text

        ui.draw(2)
        assert any("● REC" in s for s in ui.strings())
        m.stop()
        if m.session:
            m.session.wait(5)
    finally:
        if m.running:
            m.stop()
        app.close()


def test_auto_open_shutters_and_overcount_protection_simple_mode(tmp_path):
    """In simple/basic mode, starting acq opens shutters; count rate > 1 MHz closes excitation with override."""
    app, m = make_app(tmp_path, ui_mode="simple")
    ui = Driver(app, (1400, 850))
    try:
        # Initially close shutters
        m.set_shutter("Excitation", False)
        m.set_shutter("Green", False)
        m.set_shutter("Red", False)
        assert float(m.shutters.get_parameter("reported_excitation", 0)) == 0.0

        # Start acquisition in simple mode -> auto opens excitation and detector shutters
        assert m.start()
        assert m.running
        assert float(m.shutters.get_parameter("reported_excitation", 0)) == 1.0
        assert float(m.shutters.get_parameter("reported_green", 0)) == 1.0
        assert float(m.shutters.get_parameter("reported_red", 0)) == 1.0

        # Simulate count rate > 1 MHz (e.g. 1.5 MHz on channel 1)
        if hasattr(m.session.source, "_rates"):
            m.session.source._rates = [20e6, 1.5e6, 50e3]
        m.device_rates_hz = [20e6, 1.5e6, 50e3]  # sync 20MHz, det0 1.5MHz (> 1MHz)
        m._poll_runs(force=True)

        # Excitation shutter MUST be closed to protect detectors!
        assert m.overcount_alert is True
        assert float(m.shutters.get_parameter("reported_excitation", -1)) == 0.0
        assert "1 MHz" in m.overcount_message

        # UI displays warning banner and override button
        ui.draw(2)
        assert "overcount_override" in app.item_rects

        # User clicks override button
        ui.click("overcount_override")
        assert m.overcount_override is True
        assert m.overcount_alert is False
        # Excitation shutter is reopened upon override
        assert float(m.shutters.get_parameter("reported_excitation", -1)) == 1.0

        m.stop()
    finally:
        if m.running:
            m.stop()
        app.close()


def test_advanced_mode_has_no_overcount_protection(tmp_path):
    """In advanced mode, count rates above 1 MHz do not automatically close the shutter."""
    app, m = make_app(tmp_path, ui_mode="advanced")
    try:
        assert m.advanced is True
        assert m.start()
        assert m.running

        # Simulate count rate > 1 MHz
        m.device_rates_hz = [20e6, 2.5e6, 50e3]
        m._poll_runs(force=True)

        # In advanced mode, excitation shutter stays open; no auto-close
        assert m.overcount_alert is False
        assert float(m.shutters.get_parameter("reported_excitation", -1)) == 1.0

        m.stop()
    finally:
        if m.running:
            m.stop()
        app.close()


def test_multi_laser_power_adjustment_with_offset_compensation(tmp_path):
    """Adjusting Red power while Green is emitting uses Green's offset and keeps Green emitting."""
    app, m = make_app(tmp_path, ui_mode="advanced")
    try:
        # Turn Green on at ~47.9% drive (200 µW, offset 200 counts)
        d_green = 35.0 + (100.0 - 35.0) * (0.20 - 0.002) / (1.0 - 0.002)
        m.laser.set_head(200, enabled=True, intensity_pct=d_green)
        m.set_shutter("Excitation", True)
        m.laser.set_emission(True)

        # Check calculated offset for Green
        green_offset = m.calculate_diode_offset(exclude_slot=300)
        assert green_offset == pytest.approx(200.0, abs=2.0)

        # Adjust Red to 300 µW while Green is actively emitting
        m.power_selected_slot = 300
        assert m.request_power_target(300.0), m.power_message

        # Settle the servo
        m.power_servo.settle_s = 0
        end = time.monotonic() + 6
        while m.power_servo.active and time.monotonic() < end:
            m.power_poll(force=True)
            time.sleep(0.005)

        assert m.power_servo.status == "reached", m.power_message
        assert m.laser.state().heads[0].intensity_pct == pytest.approx(d_green), "Green stayed emitting at ~47.9%"
        d_red = 47.0 + (100.0 - 47.0) * (0.30 - 0.002) / (1.0 - 0.002)
        assert m.laser.state().heads[1].intensity_pct == pytest.approx(d_red, abs=0.5), "Red reached target"
        assert m.power_servo.context_offset == pytest.approx(200.0, abs=2.5)
    finally:
        app.close()
