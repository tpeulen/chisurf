"""The compact manual power form and laser-page µW control."""
import pytest


def test_simple_panel_needs_only_laser_diode_and_power(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.gui.power_controls import SimplePowerPanelModel
    record = RecordModel(output_dir=tmp_path)
    panel = SimplePowerPanelModel(record)
    panel.laser_name = '488 nm'
    panel.isolated = True
    panel.raw, panel.uw = 100, 1
    assert panel.add_point()
    panel.raw, panel.uw = 300, 3
    panel.isolated = True
    assert panel.add_point()
    assert panel.save()
    assert record.power_book.power('488 nm', 200) == pytest.approx(2)
    assert len(panel.rows()) == 2
    record.close()


def test_target_control_uses_the_selected_head_and_diode(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live.laser import SimLaser
    m = RecordModel(output_dir=tmp_path)
    m.laser = SimLaser(heads=[('488 nm',488),('640 nm',640)])
    m.laser.open();m.laser.set_head(200,intensity_pct=10)
    m.laser.set_emission(True)
    m.power_selected_slot = 200
    class Diode:
        def set_parameter(self, *a): pass
        def get_parameter(self,name,*a):
            return 1 if name == 'reported_excitation' else m.laser.state().heads[0].intensity_pct*10
        def close(self): pass
    m.shutters = Diode()
    m.power_book.add('488 nm',0,0);m.power_book.add('488 nm',1000,10)
    m.power_target_uw = 2
    assert m.set_power_target(), m.power_message
    m.power_servo.settle_s = 0
    for _ in range(40):
        m.power_poll(force=True)
        if not m.power_servo.active:break
    assert m.power_servo.status == 'reached',m.power_message
    assert m.laser.state().heads[0].intensity_pct == pytest.approx(20,abs=.5)
    assert m.laser.state().heads[1].intensity_pct == 0
    m.close()


def test_mixed_lasers_cannot_be_used_for_feedback(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    from chisurf.plugins.core.acq.live.laser import SimLaser
    m = RecordModel(output_dir=tmp_path);m.laser=SimLaser();m.laser.open()
    for head in m.laser.state().heads:m.laser.set_head(head.slot,intensity_pct=10)
    m.laser.set_emission(True)
    m.power_selected_slot=200
    m.power_book.add(m.laser.state().heads[0].name,0,0)
    m.power_book.add(m.laser.state().heads[0].name,1000,10)
    m.power_target_uw=2
    assert not m.set_power_target()
    assert 'one' in m.power_message.lower() or 'isolat' in m.power_message.lower()
    m.close()
