"""The OBIS backend: a Coherent OBIS LS/LX through libphacq's ``obis`` driver.

The phacq driver's own simulator answers, so the whole chain (open_laser -> ObisBackend ->
phacq device -> protocol) runs hardware-free. The CDRH guard, the W-power mapping, the
box channel->laser routing, and the ALEX/PIE oscillator contract are pinned here.
"""

from __future__ import annotations

import pytest

from chisurf.plugins.core.acq.live import laser as laser_mod
from chisurf.plugins.core.acq.live.laser import LaserError, ObisBackend, pie_slots


@pytest.fixture()
def obis():
    """An open OBIS simulator laser; close() blocks emission, never raises."""
    ok, why = ObisBackend.available()
    if not ok:
        pytest.skip(why)
    laser = laser_mod.open_laser("obis", allow_simulated=True)
    laser.open()
    try:
        yield laser
    finally:
        laser.close()


def test_obis_driver_is_discoverable(obis):
    ok, why = laser_mod.obis_available()
    assert ok, why


def test_open_laser_obis_opens_the_simulator(obis):
    st = obis.state()
    assert st.model.startswith("OBIS")
    assert st.library == "libphacq"
    assert len(st.heads) == 1
    # open() blocks emission
    assert st.emission_blocked


def test_open_laser_obis_without_port_or_consent_raises():
    """No port named and no simulator consent: a clear error, never a port scan."""
    ok, why = ObisBackend.available()
    if not ok:
        pytest.skip(why)
    with pytest.raises(LaserError, match="no OBIS serial port"):
        laser_mod.open_laser("obis").open()


def test_head_power_maps_intensity_onto_the_watt_limits(obis):
    """intensity_pct scales linearly between the unit's reported LOW/HIGH power limits."""
    head = obis.state().heads[0]
    obis.set_head(head.slot, intensity_pct=50.0)
    mid = obis.state().heads[0].intensity_pct
    assert 45.0 <= mid <= 55.0
    obis.set_head(head.slot, intensity_pct=0.0)
    assert obis.state().heads[0].intensity_pct == pytest.approx(0.0, abs=1e-6)


def test_pulsed_head_switches_the_digital_gate(obis):
    """pulsed=True is the external DIGITAL modulation (the ni card's ALEX/PIE gate)."""
    head = obis.state().heads[0]
    obis.set_head(head.slot, pulsed=True)
    assert obis.state().heads[0].pulsed
    obis.set_head(head.slot, pulsed=False)
    assert not obis.state().heads[0].pulsed


def test_cdrh_guard_blocks_emission_until_cleared(obis):
    """The 5 s CDRH delay refuses emission until cdrh_delay is off (safety contract)."""
    obis.device.apply({"cdrh_delay[0]": 1})  # the fresh unit's safety default, back on
    with pytest.raises(LaserError, match="CDRH"):
        obis.set_emission(True)
    obis.device.apply({"cdrh_delay[0]": 0})
    obis.set_emission(True)
    assert not obis.state().emission_blocked
    obis.close()
    assert obis._state.emission_blocked  # close() blocks emission, never raises


def test_combiner_box_carries_one_head_per_laser():
    """open('sim:N') gives N heads; slot == laser index, per-laser emission is independent."""
    ok, why = ObisBackend.available()
    if not ok:
        pytest.skip(why)
    laser = ObisBackend(serial="sim:3", allow_simulated=True)
    laser.open()
    try:
        st = laser.state()
        assert [h.slot for h in st.heads] == [0, 1, 2]
        laser.set_head(2, enabled=True, intensity_pct=25.0)
        heads = laser.state().heads
        assert heads[2].intensity_pct == pytest.approx(25.0, abs=1.0)
        assert laser.device.get_parameter("emission", 2) == 1.0
        assert laser.device.get_parameter("emission", 0) == 0.0
    finally:
        laser.close()


def test_oscillator_program_stays_in_the_state_for_pie_slots(obis):
    """The ALEX/PIE program is kept (the ni card plays it): pie_slots works off the state."""
    st = obis.state()
    for h in st.heads:
        h.output = h.slot
        h.wavelength_nm = 488.0 if h.slot == 0 else 640.0
    obis.set_oscillator(
        base_hz=40e6,
        burst_lengths=[1] * laser_mod.SEQUENCER_OUTPUTS,
        output_enabled=[i < 2 for i in range(laser_mod.SEQUENCER_OUTPUTS)],
        sync_enabled=[False] * laser_mod.SEQUENCER_OUTPUTS,
        delays_ns=[0.0] * laser_mod.SEQUENCER_OUTPUTS,
    )
    program = obis.capture()
    slots = pie_slots(program)
    assert slots, "the program's enabled outputs must produce PIE slots"
    assert [s["output"] for s in slots] == [0, 1]


def test_chooser_selects_obis_and_opens_through_the_model(tmp_path):
    """The Settings dock's laser path: laser_kind 'obis' + an empty address opens the
    simulator (allow_simulated), the way the chooser's obis row connects."""
    ok, why = ObisBackend.available()
    if not ok:
        pytest.skip(why)
    from chisurf.plugins.core.acq.gui.record_app import RecordModel

    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    model.disconnect_laser()
    model.laser_kind, model.laser_address = "obis", ""
    assert model.connect_laser(), model.laser_detail
    assert model.laser_connected
    assert model.laser.state().model.startswith("OBIS")
    model.disconnect_laser()
    assert not model.laser_connected
