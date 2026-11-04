"""Actual Record ellipsis routing and inert chooser background, not helper-only tests."""
from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
from chisurf.plugins.core.acq.live import devices,settings_file
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_record_ellipsis_opens_and_loads_a_file_without_reloading_a_stale_workspace_pick(tmp_path,monkeypatch):
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    monkeypatch.setattr(devices,'attached_devices',lambda drivers=None:[])
    path=tmp_path/'chosen.json'
    settings_file.save(settings_file.new_settings(name='chosen',run={'duration_s':17.0}),path)
    m=RecordModel(output_dir=tmp_path);m.settings_address='profile:old'
    app=RecordApp(m)
    try:
        ui=Driver(app,(1500,950));ui.draw(3)
        ui.click('request_settings_file');ui.draw(2)
        assert app.settings_open_dialog.open
        assert 'Load acquisition settings' in ui.strings()
        ui.click_text(path.name);ui.click_text('Open');ui.draw(2)
        assert not app.settings_open_dialog.open
        m.wait_connected(10)  # Open adopts in a worker thread, never in the frame
        assert m.duration_s==17.0 and m.settings_file_path==str(path)
        assert m.settings_address=='', 'file loading must not leave a different reload target'
        assert m.device is None and m.simulation_connected
    finally:app.close()


def test_file_chooser_background_cannot_open_help(tmp_path,monkeypatch):
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    app=RecordApp(RecordModel(output_dir=tmp_path))
    try:
        ui=Driver(app,(1500,950));ui.draw(3)
        ui.click('request_settings_file');ui.draw(2)
        assert app.settings_open_dialog.open
        ui.click_text('❓ Help');ui.draw(2)
        assert not app.help_window.open
        assert app.settings_open_dialog.open
        ui.click_text('Cancel');ui.draw(2)
        assert not app.settings_open_dialog.open
        assert not app.model.settings_name
    finally:app.close()
