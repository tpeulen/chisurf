"""Every connected head stays visible; no color/laser combobox hides it."""
from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def make(tmp_path):
    m=RecordModel(output_dir=tmp_path);assert m.connect_instrument_simulator()
    app=RecordApp(m);app.focus_dock('laser');return app,Driver(app,(1500,950))


def test_all_connected_lasers_are_stacked_with_power_switch_pulsed_and_calibration(tmp_path):
    app,ui=make(tmp_path)
    try:
        ui.draw(3)
        strings=ui.strings()
        assert 'Green 488 nm' in strings and 'Red 640 nm' in strings
        assert 'Color / laser' not in strings
        assert 'power_selected_slot' not in app.item_rects
        for slot in (200,300):
            for prefix in ('laser_target','laser_on','laser_pulsed','laser_calibrate'):
                assert f'{prefix}_{slot}' in app.item_rects
        assert app.item_rects['laser_target_300'][1]>app.item_rects['laser_target_200'][1]
    finally:app.close()


def test_each_calibration_button_opens_that_heads_calibration(tmp_path):
    app,ui=make(tmp_path)
    try:
        ui.draw(3);ui.click('laser_calibrate_300')
        assert app.power_panel.model.laser_name=='Red 640 nm'
        assert app.model.power_selected_slot==300
        assert app.model.laser.state().emission_blocked
    finally:app.close()


def test_uncalibrated_heads_have_percentage_controls_and_explicit_on(tmp_path):
    app,ui=make(tmp_path)
    try:
        app.model.power_book.records.clear()
        ui.draw(3)
        assert 'laser_drive_200' in app.item_rects and 'laser_drive_300' in app.item_rects
        x,y,w,h=ui.rect('laser_drive_200')
        ui.drag((x+5,y+h/2),(x+w*.35,y+h/2))
        assert app.model.laser.state().heads[0].intensity_pct>0
        assert app.model.laser.state().emission_blocked
        ui.click('laser_on_200')
        assert not app.model.laser.state().emission_blocked
    finally:app.close()


def test_per_head_pulsed_switch_changes_only_that_head(tmp_path):
    app,ui=make(tmp_path)
    try:
        ui.draw(3);ui.click('laser_pulsed_200')
        heads=app.model.laser.state().heads
        assert heads[0].pulsed is False and heads[1].pulsed is True
        assert app.model.laser.state().emission_blocked
    finally:app.close()
