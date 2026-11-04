"""Simple mode has only warnings; detailed quality and range controls are expert-only."""
from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_simple_mode_hides_green_details_and_ranges_but_keeps_warnings(tmp_path,monkeypatch):
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    m=RecordModel(output_dir=tmp_path)
    m.snapshot={'bursts':10,'burst_rate_hz':1.,'photons':1000,'elapsed_s':1.,'qc':{
        'ready':True,'level':'red','checks':[
            {'name':name,'light':color,'value':'1','range':'0–2','detail':'hover detail','action':'hover action'}
            for name,color in [('Passing metric','green'),('Watch metric','amber'),('Failed metric','red')]]}}
    app=RecordApp(m)
    try:
        ui=Driver(app,(1500,950));app.focus_dock('quality');ui.draw(3)
        assert 'Passing metric' not in ' '.join(ui.strings())
        assert 'Watch metric' in ' '.join(ui.strings()) and 'Failed metric' in ' '.join(ui.strings())
        assert 'quality_rows' not in app.form.rects
        ranges={'Histogram range.fold','Trace range.fold','Decay range.fold'}
        assert not ranges.intersection(app.item_rects)
        m.ui_mode='advanced';assert m.ui_mode_changed();ui.draw(3)
        assert {'Metric','Value','Limit','Status','Passing metric'}<=set(ui.strings())
        assert 'quality_rows' in app.form.rects
        drawn_rects = set(app.item_rects)
        for r_dock in ('plot_hist', 'plot_trace', 'plot_decays'):
            app.focus_dock(r_dock)
            ui.draw(1)
            drawn_rects.update(app.item_rects)
        assert ranges<=drawn_rects
    finally:app.close()
