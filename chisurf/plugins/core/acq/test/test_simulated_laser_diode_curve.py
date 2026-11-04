"""Tests for simulated laser diode minimum driver power thresholds (35% blue/green, 47% red)
and the physical laser diode L-I power curve.
"""
import pytest
from chisurf.plugins.core.acq.live.laser import HeadState, laser_diode_threshold
from chisurf.plugins.core.acq.live.instrument_sim import laser_diode_power_fraction
from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_laser_diode_threshold_resolution():
    """Wavelength / name determines the minimum driver power threshold."""
    # Blue / green diodes
    assert laser_diode_threshold("Green 488 nm") == 35.0
    assert laser_diode_threshold("Blue 405 nm", wavelength_nm=405) == 35.0
    assert laser_diode_threshold(HeadState(slot=200, name="Green 488 nm")) == 35.0

    # Red diodes
    assert laser_diode_threshold("Red 640 nm") == 47.0
    assert laser_diode_threshold("LDH-P-C-640", wavelength_nm=640) == 47.0
    assert laser_diode_threshold(HeadState(slot=300, name="Red 640 nm")) == 47.0

    # Explicit min_intensity_pct overrides heuristic
    custom_head = HeadState(slot=205, name="Custom Diode", min_intensity_pct=42.5)
    assert laser_diode_threshold(custom_head) == 42.5


def test_laser_diode_power_fraction_curve():
    """Curve follows typical laser diode L-I characteristics: spontaneous below threshold, stimulated above."""
    th_green = 35.0
    th_red = 47.0

    # Zero drive produces zero power
    assert laser_diode_power_fraction(0.0, th_green) == 0.0
    assert laser_diode_power_fraction(0.0, th_red) == 0.0

    # Below threshold: low spontaneous emission (linear in drive / threshold, <= 0.002)
    f_sub_green = laser_diode_power_fraction(20.0, th_green)
    assert 0.0 < f_sub_green <= 0.002
    assert f_sub_green == pytest.approx(0.002 * (20.0 / 35.0))

    f_sub_red = laser_diode_power_fraction(30.0, th_red)
    assert 0.0 < f_sub_red <= 0.002
    assert f_sub_red == pytest.approx(0.002 * (30.0 / 47.0))

    # At threshold: exactly spontaneous emission fraction
    assert laser_diode_power_fraction(th_green, th_green) == pytest.approx(0.002)
    assert laser_diode_power_fraction(th_red, th_red) == pytest.approx(0.002)

    # Above threshold: stimulated emission dominates and increases linearly to 1.0 at 100% drive
    assert laser_diode_power_fraction(100.0, th_green) == pytest.approx(1.0)
    assert laser_diode_power_fraction(100.0, th_red) == pytest.approx(1.0)

    # Midpoints
    f_mid_green = laser_diode_power_fraction(35.0 + 32.5, th_green)
    assert f_mid_green == pytest.approx(0.002 + 0.998 * 0.5)

    # Strictly monotonic
    drives = [0.0, 10.0, 25.0, 35.0, 45.0, 60.0, 80.0, 100.0]
    fracs = [laser_diode_power_fraction(d, th_green) for d in drives]
    assert all(b > a for a, b in zip(fracs[:-1], fracs[1:]))


def test_simulated_shutters_and_photodiode_follow_diode_curve(tmp_path):
    """SimShutters diode raw readback reflects the laser diode power curve."""
    m = RecordModel(output_dir=tmp_path)
    assert m.connect_instrument_simulator()
    try:
        m.set_shutter("Excitation", True)
        m.laser.set_emission(True)

        # Baseline dark reading when drives are 0
        m.laser.set_head(200, intensity_pct=0.0)
        m.laser.set_head(300, intensity_pct=0.0)
        assert m.shutters.get_parameter("diode_raw") == pytest.approx(20.0)

        # Drive Green at threshold (35%)
        m.laser.set_head(200, intensity_pct=35.0)
        # Green full span is 1000 counts; at threshold f=0.002 -> +2 counts over dark
        assert m.shutters.get_parameter("diode_raw") == pytest.approx(22.0)

        # Drive Red at threshold (47%)
        m.laser.set_head(200, intensity_pct=0.0)
        m.laser.set_head(300, intensity_pct=47.0)
        # Red full span is 800 counts; at threshold f=0.002 -> +1.6 counts over dark
        assert m.shutters.get_parameter("diode_raw") == pytest.approx(21.6)

        # Full power on both heads
        m.laser.set_head(200, intensity_pct=100.0)
        m.laser.set_head(300, intensity_pct=100.0)
        # Dark 20 + Green 1000 + Red 800 = 1820 counts
        assert m.shutters.get_parameter("diode_raw") == pytest.approx(1820.0)
    finally:
        m.close()


def test_ui_laser_cards_head_specific_threshold_warning(tmp_path):
    """Laser card UI indicates near-threshold warning according to head's own threshold."""
    m = RecordModel(output_dir=tmp_path)
    assert m.connect_instrument_simulator()
    app = RecordApp(m)
    try:
        app.focus_dock("laser")
        ui = Driver(app, (1500, 950))

        # Green head has threshold 35%; at 30% drive it is near/below threshold
        m.laser.set_head(200, intensity_pct=30.0)
        m.power_poll(force=True)
        ui.draw(2)
        strings = ui.strings()
        assert any("30.0% (near threshold)" in s for s in strings)

        # Increase Green to 50% drive (above 35% threshold) -> warning clears
        m.laser.set_head(200, intensity_pct=50.0)
        m.power_poll(force=True)
        ui.draw(2)
        strings = ui.strings()
        assert any("Drive: 50.0%" in s for s in strings)
        assert not any("50.0% (near threshold)" in s for s in strings)

        # Red head has threshold 47%; at 45% drive it is near/below threshold
        m.laser.set_head(300, intensity_pct=45.0)
        m.power_poll(force=True)
        ui.draw(2)
        strings = ui.strings()
        assert any("45.0% (near threshold)" in s for s in strings)

        # Increase Red to 65% drive (above 47% threshold) -> warning clears
        m.laser.set_head(300, intensity_pct=65.0)
        m.power_poll(force=True)
        ui.draw(2)
        strings = ui.strings()
        assert any("Drive: 65.0%" in s for s in strings)
        assert not any("65.0% (near threshold)" in s for s in strings)
    finally:
        app.close()
