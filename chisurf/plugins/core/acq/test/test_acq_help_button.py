"""Help must open visibly from an actual toolbar click, including a narrow host."""
import pytest
from emtk.keys import KEY_ESCAPE
from chisurf.plugins.core.acq.gui.record_app import RecordApp,RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


@pytest.mark.parametrize('size',[(1500,950),(700,650)])
def test_help_button_opens_visible_help(size,tmp_path,monkeypatch):
    from chisurf.plugins.core.acq.gui.video_panel import VideoPanel
    monkeypatch.setattr(VideoPanel,'connect',lambda self:False)
    app=RecordApp(RecordModel(output_dir=tmp_path))
    try:
        ui=Driver(app,size);ui.draw(3)
        ui.click_text('❓ Help');ui.draw(3)
        assert 'Record help' in ui.strings()
        assert any(len(lines)>5 for _,lines in app.help_window.sections)
        ui.key(KEY_ESCAPE);ui.draw(2)
        assert not app.help_window.open
    finally:app.close()
