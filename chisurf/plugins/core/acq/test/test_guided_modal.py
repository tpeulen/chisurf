"""Shared modal wizard, blurred real background, protected input routing."""
from emtk import Wizard
from emtk.testing import RecordingPainter
from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def test_acquisition_uses_reusable_emtk_wizard(tmp_path):
    app=RecordApp(RecordModel(output_dir=tmp_path))
    try:
        assert isinstance(app.wizard.navigation, Wizard)
        app.model.ui_mode='guided';app.model.ui_mode_changed()
        ui=Driver(app,(1000,700));ui.draw(3)
        x,y,w,h=app.wizard.window.box
        px,py,pw,ph=app.item_rects['wizard_back']
        nx,ny,nw,nh=app.item_rects['wizard_next']
        assert y+h-65 <= ny and ny+nh <= y+h
        assert px+pw < nx and py==ny
        assert 'guided' not in app.docks.windows
    finally:app.close()


def test_blur_has_real_background_but_background_controls_are_not_interactive(tmp_path):
    class BackgroundSpy(RecordingPainter):
        def backdrop(self,*args,**kwargs):
            self.before_blur=list(self.strings)
    app=RecordApp(RecordModel(output_dir=tmp_path))
    try:
        app.model.ui_mode='guided';app.model.ui_mode_changed()
        p=BackgroundSpy();app.draw(p,0,0,1200,800)
        assert 'Acquisition' in p.before_blur, 'blur must cover the dock view, not an empty frame'
        assert 'source_kind' not in app.item_rects
        assert 'wizard_next' in app.item_rects
    finally:app.close()


def test_click_on_background_toolbar_does_not_open_another_window(tmp_path, monkeypatch):
    app=RecordApp(RecordModel(output_dir=tmp_path))
    calls=[]
    monkeypatch.setattr(app.help_window,'show',lambda:calls.append('opened'))
    try:
        app.model.ui_mode='guided';app.model.ui_mode_changed()
        ui=Driver(app,(1500,950));ui.draw(3)
        ui.click_text('❓ Help')
        assert not calls
        assert app.wizard.window.open
    finally:app.close()
