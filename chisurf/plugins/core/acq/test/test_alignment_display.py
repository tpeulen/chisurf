"""A detector-row double click opens genuinely large, updating alignment digits."""
from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_mean_alignment_rate_uses_the_full_run_not_the_visible_trace_window(tmp_path):
    m=RecordModel(output_dir=tmp_path)
    try:
        m.snapshot={'count_rate_hz':100000.,'trace':{'bin_width_s':1.,'counts':{'DD':[1,1,1]}}}
        mean=next(row for row in m.count_rate_rows() if row['channel']=='Mean recorded')
        assert mean['value']==100. and mean['unit']=='kHz'
    finally:m.close()


def test_mean_alignment_rate_can_use_native_photon_and_duration_counters(tmp_path):
    m=RecordModel(output_dir=tmp_path)
    try:
        m.device_rates_hz=[20e6,10000.]
        m.snapshot={'photons':2000,'elapsed_s':.25}
        mean=next(row for row in m.count_rate_rows() if row['channel']=='Mean recorded')
        assert mean['value']==(2000/.25)/1000 and mean['unit']=='kHz'
    finally:m.close()


def test_double_click_rate_opens_giant_floating_monitor_and_updates(tmp_path,monkeypatch):
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    m=RecordModel(output_dir=tmp_path);m.device_rates_hz=[20e6,1.25e6,0]
    app=RecordApp(m)
    try:
        app.focus_dock('rates')
        ui=Driver(app,(1500,950));ui.draw(3)
        table=app.form.tables['count_rate_rows'].control
        x,y,w,h=table._body_box
        px,py=x+25,y+table._row_h*1.5
        app.pointer_move(px,py);app.press(px,py,clicks=2);ui.draw(1)
        app.release();ui.draw(3)
        assert 'alignment_rate' in app.docks.floating()
        win=app.docks.window('alignment_rate')
        assert win.visible and win.box[2]>=1000 and win.box[3]>=600
        assert 'Detector 0' in ui.strings() and '1.25 MHz' in ui.strings()
        assert app.item_rects['alignment_rate_value'][3]>=120
        m.device_rates_hz[1]=2.5e6;ui.draw(2)
        assert '2.50 MHz' in ui.strings()
        ui.click_text('×',last=True);ui.draw(2)
        assert not win.visible
    finally:app.close()
