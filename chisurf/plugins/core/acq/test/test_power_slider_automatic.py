"""Real GUI gestures apply µW without a second Set button, with confirmation."""
from pathlib import Path
from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_drag_commits_one_automatic_target_without_set_button(tmp_path):
    m=RecordModel(output_dir=tmp_path);assert m.connect_instrument_simulator()
    app=RecordApp(m)
    try:
        app.focus_dock('laser');ui=Driver(app,(1500,950));ui.draw(3)
        assert 'Set µW' not in ui.strings()
        x,y,w,h=ui.rect('power_target_uw')
        ui.drag((x+10,y+h/2),(x+w*.45,y+h/2))
        assert m.power_servo is not None and m.power_servo.active,m.power_message
        assert not m.laser.state().emission_blocked
        assert m.laser.state().heads[1].intensity_pct==0
    finally:app.close()


def test_power_warning_is_modal_and_cancel_changes_nothing(tmp_path):
    m=RecordModel(output_dir=tmp_path);assert m.connect_instrument_simulator()
    app=RecordApp(m)
    try:
        m.recorded_paths.append(Path('saved-reference.ptu'))
        events=list(m.laser.events)
        assert not m.request_power_target(3)
        ui=Driver(app,(1500,950));ui.draw(3)
        assert 'Change laser power?' in ui.strings()
        assert 'source_kind' not in app.item_rects
        ui.click_text('No')
        assert m.pending_power_change is None
        assert m.laser.events==events
    finally:app.close()
