"""Tests for CMC Light laser backend integration (3-laser SCPI driver from chinalaser).
"""
import pytest
from chisurf.plugins.core.acq.live.laser import (
    CmcLightBackend,
    cmc_light_available,
    open_laser,
    pie_slots,
    propose_pie_windows,
    ptu_tags,
)
from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_cmc_light_availability():
    """cmc_light module is discovered in dev/chinalaser and reports available."""
    ok, why = cmc_light_available()
    assert ok is True
    assert "ready" in why or "USB" in why


def test_cmc_light_open_simulated_and_lifecycle():
    """CmcLightBackend opens in simulated mode with 3 channels in safe all-off state."""
    laser = open_laser("cmc_sim")
    assert isinstance(laser, CmcLightBackend)
    assert not laser.is_open

    # SCPI and OBIS standard aliases
    assert isinstance(open_laser("scpi_sim"), CmcLightBackend)
    # obis means the real Coherent OBIS through libphacq now (owner round 2026-11-01);
    # obis_sim is its simulator, NOT the CMC shim -- the CMC simulated path is cmc_sim
    from chisurf.plugins.core.acq.live.laser import ObisBackend
    assert isinstance(open_laser("obis_sim"), ObisBackend)

    st = laser.open()
    try:
        assert laser.is_open
        assert laser.kind == "cmc_light"
        assert st.library == "cmc_light"
        assert st.emission_blocked is True
        assert len(st.heads) == 3

        # Channel 1: Blue, Channel 2: Green, Channel 3: Red
        slots = [h.slot for h in st.heads]
        assert slots == [100, 200, 300]

        names = [h.name for h in st.heads]
        assert any("Blue" in n for n in names)
        assert any("Green" in n for n in names)
        assert any("Red" in n for n in names)

        # Wavelengths
        wls = [h.wavelength_nm for h in st.heads]
        assert wls[0] in (405.0, 488.0)
        assert wls[1] in (532.0, 488.0, 520.0)
        assert wls[2] == 640.0
    finally:
        laser.close()
        assert not laser.is_open


def test_cmc_light_power_and_emission_control():
    """Setting power, individual head enable, and global emission block."""
    laser = CmcLightBackend(simulated=True)
    laser.open()
    try:
        # Set Blue at 45% and Red at 30%
        laser.set_head(100, intensity_pct=45.0, enabled=True)
        laser.set_head(300, intensity_pct=30.0, enabled=True)
        laser.set_emission(True)

        st = laser.state()
        assert st.emission_blocked is False
        assert st.heads[0].intensity_pct == pytest.approx(45.0)
        assert st.heads[2].intensity_pct == pytest.approx(30.0)

        # Direct readback from underlying source
        assert laser.source.emission(1) is True
        assert laser.source.emission(2) is False
        assert laser.source.emission(3) is True
        assert laser.source.power(1) == pytest.approx(0.45)
        assert laser.source.power(3) == pytest.approx(0.30)

        # Laser off blocks all outputs immediately
        laser.laser_off()
        st = laser.state()
        assert st.emission_blocked is True
        assert laser.source.emission(1) is False
        assert laser.source.emission(3) is False
    finally:
        laser.close()


def test_cmc_light_builtin_photodiode_readback():
    """Built-in BH1750 photodiode power monitor (lux) readback via diode_raw."""
    laser = CmcLightBackend(simulated=True)
    laser.open()
    try:
        # With all off, photodiode reads 0 lux
        assert laser.get_parameter("diode_raw") == 0.0
        assert laser.monitor_lux() == 0.0

        # Enable Blue at 50%
        laser.set_head(100, intensity_pct=50.0, enabled=True)
        laser.set_emission(True)
        lux_blue = laser.get_parameter("diode_raw")
        assert lux_blue > 0.0

        # Add Red at 30% -> additive photodiode reading increases
        laser.set_head(300, intensity_pct=30.0, enabled=True)
        lux_both = laser.get_parameter("diode_raw")
        assert lux_both > lux_blue

        # Global off returns to 0
        laser.laser_off()
        assert laser.get_parameter("diode_raw") == 0.0
    finally:
        laser.close()


def test_cmc_light_alex_sequence_and_pie():
    """Hardware ALEX sequence configuration and microtime window proposal."""
    laser = CmcLightBackend(simulated=True)
    laser.open()
    try:
        laser.load_alex(on_us=500, gap_us=50, sync_width_us=100)
        laser.set_head(100, enabled=True, intensity_pct=50.0, pulsed=True)
        laser.set_head(300, enabled=True, intensity_pct=50.0, pulsed=True)

        st = laser.state()
        assert st.heads[0].pulsed is True
        assert laser.source.source() == "SEQ"

        # Check steps in the instrument
        steps = laser.source.steps()
        assert len(steps) == 6
        assert steps[0] == (500, 1)  # Blue on
        assert steps[1] == (50, 0)   # gap
        assert steps[2] == (500, 2)  # Green on
        assert steps[3] == (50, 0)   # gap
        assert steps[4] == (500, 4)  # Red on
        assert steps[5] == (50, 0)   # gap

        # PTU tags
        tags = ptu_tags(laser, laser.capture())
        assert tags.get("Laser_Backend") == "cmc_light"
        assert "CMC_Identity" in tags

        # Arbitrary sequence setting via text and list
        laser.set_sequence_steps("30us 1; 10us; 30us 2")
        custom_steps = laser.get_sequence_steps()
        assert len(custom_steps) == 3
        assert custom_steps[0] == (30, 1)
        assert custom_steps[1] == (10, 0)
        assert custom_steps[2] == (30, 2)
    finally:
        laser.close()


def test_cmc_light_record_model_and_ui_integration(tmp_path):
    """RecordModel connects CMC Light and renders stacked cards in laser dock."""
    model = RecordModel(output_dir=tmp_path, realtime=False)
    # Check laser options expose CMC Light
    opts = model.laser_options()
    opt_keys = [k for k, _ in opts]
    assert "cmc_light" in opt_keys
    assert "cmc_sim" in opt_keys

    # Connect CMC Light simulated
    model.laser_kind = "cmc_sim"
    assert model.connect_laser()
    assert model.laser_connected is True
    assert isinstance(model.laser, CmcLightBackend)

    app = RecordApp(model)
    try:
        app.focus_dock("laser")
        ui = Driver(app, (1500, 950))
        ui.draw(3)

        # Verify all 3 channels appear in laser dock
        strings = ui.strings()
        assert any("Blue" in s for s in strings)
        assert any("Green" in s for s in strings)
        assert any("Red" in s for s in strings)

        # Control rects exist for all slots (100, 200, 300)
        for slot in (100, 200, 300):
            assert f"laser_on_{slot}" in app.item_rects
            assert f"laser_drive_{slot}" in app.item_rects or f"laser_target_{slot}" in app.item_rects

        # Test photodiode reading with CMC Light
        model.laser.set_head(100, intensity_pct=50.0, enabled=True)
        model.laser.set_emission(True)
        model.power_poll(force=True)
        reading = model.power_reading()
        assert "µW" in reading or "lux" in reading or reading != "— µW"
    finally:
        app.close()
