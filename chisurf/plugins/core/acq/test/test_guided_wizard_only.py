"""Guided measurement has one surface: the modal wizard, never a dock."""
from chisurf.plugins.core.acq.gui.record_app import DOCKS, RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_guided_measurement_is_not_a_dock_but_wizard_still_opens(tmp_path):
    app = RecordApp(RecordModel(output_dir=tmp_path))
    try:
        assert not any(key == 'guided' for key, _, _ in DOCKS)
        assert 'guided' not in app.docks.windows
        ui = Driver(app, (1500, 950)); ui.draw(2)
        app.model.ui_mode = 'guided'; assert app.model.ui_mode_changed()
        ui.draw(3)
        assert app.wizard.window.open
        assert 'wizard_next' in app.item_rects
        assert 'source_kind' not in app.item_rects
    finally:
        app.close()
