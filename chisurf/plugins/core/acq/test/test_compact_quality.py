"""One concise quality table; explanations/actions belong to row tooltips."""
import time

from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


ACTION = 'Replace the sample, check alignment, and repeat the reference measurement.'
DETAIL = 'This is the explanation of the measured quality metric.'


def _app(tmp_path):
    model = RecordModel(output_dir=tmp_path)
    model.ui_mode='advanced';model.ui_mode_changed()
    model.snapshot = {'bursts': 10, 'burst_rate_hz': 1., 'photons': 1000, 'elapsed_s': 10.,
                      'qc': {'ready': True, 'level': 'amber', 'checks': [
        {'name': 'Test metric', 'value': '12.0', 'range': '10–11',
         'light': 'amber', 'detail': DETAIL, 'action': ACTION}]}}
    return RecordApp(model)


def test_quality_is_one_compact_table_without_visible_advice(tmp_path):
    app = _app(tmp_path)
    try:
        ui = Driver(app, (1500, 950))
        app.focus_dock('quality'); ui.draw(3)
        strings = ui.strings()
        assert ACTION not in strings and DETAIL not in strings
        assert 'Guidance' not in strings
        assert {'Metric', 'Value', 'Limit', 'Status'} <= set(strings)
        assert strings.count('Test metric') == 1, 'do not duplicate the table as a bullet list'
        rows = app.model.quality_rows()
        assert ACTION in rows[0]['detail'] and DETAIL in rows[0]['detail']
        assert rows[0]['acceptable'] == '10–11'
        # Exercise actual row-hover routing, not merely the stored tooltip field.
        table = app.form.tables['quality_rows'].control
        x, y, _, _ = table._body_box
        ui.hover(x + 30, y + table._row_h / 2)
        time.sleep(.65)
        hovered = ' '.join(ui.strings())
        assert ACTION in hovered and DETAIL in hovered
    finally:
        app.close()


def test_quality_table_stretches_to_fill_its_dock_vertically(tmp_path):
    app=_app(tmp_path)
    try:
        ui=Driver(app,(1500,950));app.focus_dock('quality');ui.draw(3)
        x,y,w,h=app.form.rects['quality_rows']
        region = app.docks.region_of('quality')
        dx,dy,dw,dh=app.docks.region_boxes[region]
        assert h>150, 'do not collapse the table to its row count'
        assert 0 <= (dy+dh)-(y+h) <= 15, 'table must fill the available dock height'
        previous=h
        ui.draw(3,size=(1500,1150))
        assert app.form.rects['quality_rows'][3]>previous
    finally:app.close()


def test_no_quality_data_still_means_no_verdict(tmp_path):
    model = RecordModel(output_dir=tmp_path)
    try:
        row = model.quality_rows()[0]
        assert row['status'] == 'no verdict' and row['value'] == '—'
        assert row['detail']
    finally:
        model.close()
