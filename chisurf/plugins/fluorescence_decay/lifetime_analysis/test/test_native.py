"""The native lifetime hub must host every real tool without loading Qt."""

import subprocess
import sys
from pathlib import Path


def test_all_five_real_children_render_without_qt():
    script = """
import importlib.abc,sys
class BlockQt(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise RuntimeError('Native lifetime hub attempted Qt: '+fullname)
sys.meta_path.insert(0,BlockQt())
from emtk.testing import RecordingPainter
from emtk.i18n import set_locale,get_locale
from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.app import make_app,PANELS
set_locale('de')
app=make_app()
try:
    for identifier,*_ in PANELS:
        child=app.select(identifier)
        assert child is not None,app.error
        app.draw(RecordingPainter(),0,0,1400,900)
        assert app.select(identifier) is child
        assert get_locale()=='de'
    settings=app.export_settings()
    app.restore_settings({'selected':'lltf'})
    assert app.selected=='lltf'
    app.restore_settings(settings)
    assert app.selected==PANELS[-1][0]
    assert len(app.children)==len(PANELS)
    app.search='lazy'
    app.draw(RecordingPainter(),0,0,1400,900)
    assert 'Lazy Lifetime' in app.item_rects
    assert 'MaxEnt MEM' not in app.item_rects
    assert 'chisurf.gui' not in sys.modules
finally:
    app.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[5],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
