"""Routine acquisition toolbar stays small; workflows have their own entries."""
from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_top_row_has_no_global_calibration_or_guided_measurement_buttons(tmp_path,monkeypatch):
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    app=RecordApp(RecordModel(output_dir=tmp_path))
    try:
        ui=Driver(app,(1500,950));ui.draw(3)
        texts=ui.strings()
        assert 'Power cal' not in texts
        assert 'Guided measurement' not in texts
        assert 'start_pause' in app.item_rects and 'stop' in app.item_rects
    finally:app.close()
