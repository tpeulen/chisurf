"""Idle acquisition keeps actual empty axes instead of collapsing the plot docks."""
from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_idle_plot_frames_have_the_same_useful_area_without_fabricated_data(tmp_path,monkeypatch):
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    app=RecordApp(RecordModel(output_dir=tmp_path))
    try:
        ui=Driver(app,(1500,950))
        for dock, key in (('plot_hist', 'live_view'), ('plot_trace', 'live_trace'), ('plot_decays', 'live_decays')):
            app.focus_dock(dock)
            ui.draw(2)
            assert app.item_rects[key][3]>150, (key,app.item_rects[key])
            text=ui.strings()
            if key == 'live_trace':
                assert 'time (s)' in text and 'count rate (kHz)' in text
            elif key == 'live_decays':
                assert 'micro-time channel' in text and 'photons' in text
        assert app.model.snapshot is None and app.model.session is None
    finally:app.close()
