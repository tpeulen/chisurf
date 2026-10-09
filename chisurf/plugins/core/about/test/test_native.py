import subprocess
import sys

from emtk import im
from emtk.testing import RecordingPainter

from chisurf.core.info import __version__


def test_about_preserves_identity_content_and_close_action(monkeypatch):
    from chisurf.plugins.core.about.gui.app import make_app

    app = make_app()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 500, 500)
    text = "\n".join(painter.strings)
    assert __version__ in text
    assert "Thomas-Otavio Peulen" in text
    assert "thomas.peulen@tu-dortmund.de" in text
    assert "github.com/fluorescence-tools/chisurf" in text
    assert app.logo is not None
    original = im.button
    monkeypatch.setattr(im, "button", lambda label, *args, **kwargs:
                        label == "Close" or original(label, *args, **kwargs))
    app.draw(RecordingPainter(), 0, 0, 500, 500)
    assert app.close_requested


def test_about_factory_constructs_and_draws_without_qt():
    code = '''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PySide6', 'pyqtgraph'}:
            raise ImportError('Qt forbidden')
sys.meta_path.insert(0, Block())
from chisurf.plugins.core.about.gui.app import make_app
from emtk.testing import RecordingPainter
app = make_app()
app.draw(RecordingPainter(), 0, 0, 500, 500)
assert not any(name.startswith('qtpy') for name in sys.modules)
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
