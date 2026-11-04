"""The rate monitor is a compact, aligned table rather than stacked loose labels."""
import pytest


def test_count_rate_rows_keep_sync_detectors_units_and_mean(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    m=RecordModel(output_dir=tmp_path)
    m.device_rates_hz=[20e6,1234,0,5678]
    m.snapshot={'count_rate_hz':6912}
    rows=m.count_rate_rows()
    assert [r['channel'] for r in rows]==['Sync','Detector 0','Detector 1','Detector 2','Mean recorded']
    assert rows[0]['value']==pytest.approx(20) and rows[0]['unit']=='MHz'
    assert rows[1]['value']==pytest.approx(1.234) and rows[1]['unit']=='kHz'
    assert rows[2]['value']==0 and rows[2]['unit']=='Hz'
    m.close()


def test_rate_dock_uses_a_table_and_smaller_default_region(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel,RecordApp,_layout
    from chisurf.plugins.microscopy.imaging_emtk.testing import Driver
    m=RecordModel(output_dir=tmp_path);m.device_rates_hz=[20e6,1000,0,2000]
    app=RecordApp(m)
    try:
        app.focus_dock('rates')
        ui=Driver(app,(1500,950));ui.draw(3)
        assert 'count_rate_rows' in app.form.tables
        assert 'live_rates' in app.item_rects
        assert {'Sync','Detector 0','Detector 1','Detector 2','MHz','kHz','Hz'} <= set(ui.strings())
        x,y,w,h=app.item_rects['live_rates']
        assert h<=180,'the rate table should not consume half the right-hand panel'
    finally:app.close()
