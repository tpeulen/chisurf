"""The committed µW target is the only power-setting gesture."""
import copy
from pathlib import Path
import time
import pytest
from chisurf.plugins.core.acq.gui.record_app import RecordModel


def make_model(tmp_path):
    m=RecordModel(output_dir=tmp_path,realtime=False)
    assert m.connect_instrument_simulator()
    return m


def settle(m):
    assert m.power_servo is not None
    m.power_servo.settle_s=0
    end=time.monotonic()+6
    while m.power_servo.active and time.monotonic()<end:
        m.power_poll(force=True);time.sleep(.005)
    assert m.power_servo.status=='reached',m.power_message


def test_committed_target_with_other_heads_emitting_confirms_then_isolates(tmp_path):
    m=make_model(tmp_path)
    try:
        # the UI's idle polling captures the shared dark while nothing is driven
        m.power_poll(force=True);m.power_poll(force=True)
        m.laser.set_head(300,intensity_pct=50)
        events=list(m.laser.events)
        # Red emits unverified (no session entry): the request must NOT silently
        # isolate; it asks, naming Red and what confirming will do
        assert not m.request_power_target(2),m.power_message
        assert m.pending_power_change==2
        assert 'Red 640 nm' in m.power_change_warning
        assert 'zero' in m.power_change_warning.lower()
        assert m.laser.events==events,'no hardware state changes before confirmation'
        assert m.laser.state().heads[1].intensity_pct==50
        assert m.confirm_power_change(),m.power_message
        settle(m)
        assert m.laser.state().heads[1].intensity_pct==0
        assert m.shutters.get_parameter('reported_excitation')==1
        assert m.power_target_uw==2
        assert 'SIMULATED' in m.power_reading()
        assert m.power_book.power(m.power_laser_name(),m.shutters.get_parameter('diode_raw'))==pytest.approx(2,abs=.1)
    finally:m.close()


def test_reference_power_change_waits_for_confirmation_and_preserves_average_power_book(tmp_path):
    m=make_model(tmp_path)
    try:
        m.recorded_paths.append(Path('earlier-reference.ptu'))
        original=copy.deepcopy(m.power_book.records)
        events=list(m.laser.events)
        assert not m.request_power_target(3)
        assert m.pending_power_change==3
        assert 'pulse shape' in m.power_change_warning.lower()
        assert m.laser.events==events,'no hardware state changes before confirmation'
        assert m.confirm_power_change(),m.power_message
        settle(m)
        assert m.power_change_invalidations
        assert m.power_book.records==original
    finally:m.close()


def test_calibration_read_diode_selects_connected_name_and_uses_fresh_sample(tmp_path):
    from chisurf.plugins.core.acq.gui.power_controls import SimplePowerPanelModel
    m=make_model(tmp_path)
    try:
        m.laser.set_head(200,intensity_pct=20);m.laser.set_head(300,intensity_pct=50)
        m.set_shutter('Excitation',True);m.laser.set_emission(True)
        panel=SimplePowerPanelModel(m);panel.laser_name='Green 488 nm'
        assert panel.read_diode(),panel.message
        assert panel.raw==pytest.approx(m.shutters.get_parameter('diode_raw'))
        assert m.laser.state().heads[1].intensity_pct==0
    finally:m.close()
