"""Task accents separate acquisition, illumination, analysis and monitoring."""
from emtk.style import contrast_ratio
from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
from chisurf.plugins.core.acq.gui.video_panel import VideoPanel


def test_acquisition_task_regions_have_distinct_readable_accents(tmp_path,monkeypatch):
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    app=RecordApp(RecordModel(output_dir=tmp_path))
    try:
        accents=[app.docks.window(key).accent for key in ('acquisition','laser','analysis','rates')]
        assert all(accent is not None for accent in accents)
        resolved=[accent.resolve((25,25,30,255)) if hasattr(accent,'resolve') else accent for accent in accents]
        assert len({accent.fill for accent in resolved})==4
        assert all(contrast_ratio(accent.fill,accent.text)>=4.5 for accent in resolved)
        assert app.docks.window('shutters').accent==app.docks.window('laser').accent
        assert app.docks.window('plot_trace').accent==app.docks.window('analysis').accent
    finally:app.close()
