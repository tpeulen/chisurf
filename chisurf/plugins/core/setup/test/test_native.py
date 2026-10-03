"""Native routes and validation protect persistent settings."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from chisurf.plugins.core.setup.gui.model import PANELS, SettingsDocument


def test_document_preserves_types_and_invalid_input(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text('caption: "a|b"\nitems: [a, b]\nflag: true\n')
    doc = SettingsDocument(path)
    doc.text += "count: 4\n"
    assert doc.dirty
    value = doc.save()
    assert value["caption"] == "a|b" and value["items"] == ["a", "b"]
    assert not doc.dirty
    original = path.read_bytes()
    doc.text = "items: [broken"
    with pytest.raises(Exception):
        doc.save()
    assert path.read_bytes() == original
    doc.reload()
    assert not doc.dirty
    target = tmp_path / "copy.yaml"
    doc.save(target)
    assert target.read_bytes() == original


def test_all_original_destinations_exist():
    assert len(PANELS) == 15
    assert len({p.key for p in PANELS}) == 15
    assert {p.label for p in PANELS} >= {
        "Packages",
        "Updates",
        "Models",
        "User Editor",
        "Getting Started",
    }


def test_routes_render_without_qt(tmp_path):
    code = r"""
import sys
class BlockQt:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise ImportError('Qt forbidden '+fullname)
sys.meta_path.insert(0,BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.core.setup.gui.app import make_app
app=make_app(settings_dir=sys.argv[1])
for panel in app.panels:
    app.select(panel.key)
    p=RecordingPainter();app.draw(p,0,0,1100,800)
    assert not app.error, (panel.key,app.error)
    # Nav rows draw "icon ▸ label"; the label must survive as a substring.
    assert any(panel.label in s for s in p.strings), (panel.key, panel.label)
assert app.routes['channels']=='native'
assert app.routes['plugins']=='native'
app.select('chisurf')
app.child.choose('open')
app.draw(RecordingPainter(),0,0,1100,800)
app.child.dialog=None
app.help.show();app.tour.start()
app.draw(RecordingPainter(),0,0,1100,800)
state=app.export_settings()
app.restore_settings(state)
assert app.selected=='chisurf'
assert 'qtpy' not in sys.modules
app.close()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr


def test_configuration_actions_and_child_state(tmp_path):
    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.setup.gui.app import make_app

    app = make_app(settings_dir=tmp_path)
    editor = app.select("chisurf")
    editor.document.text = "gui:\n  plot:\n    font_size: 14\n"
    assert editor.save()
    assert (tmp_path / "settings_chisurf.yaml").exists()
    app.select("plots")
    assert app.select("chisurf") is editor
    editor.document.text = "gui: ["
    assert not editor.save()
    assert editor.error
    editor.document.reload()
    editor.validate()
    app.draw(RecordingPainter(), 0, 0, 900, 650)
    restored = make_app(settings_dir=tmp_path)
    restored.restore_settings(app.export_settings())
    assert restored.selected == "chisurf"
    assert restored.child.document.path == editor.document.path
    app.close()
    restored.close()


def test_save_refreshes_active_settings(tmp_path, monkeypatch):
    from chisurf.core import settings
    from chisurf.plugins.core.setup.gui.app import make_app

    path = tmp_path / "settings_chisurf.yaml"
    monkeypatch.setattr(settings, "chisurf_settings_file", path)
    monkeypatch.setattr(settings, "cs_settings", {})
    monkeypatch.setattr(settings, "gui", {})
    app = make_app(settings_dir=tmp_path)
    editor = app.select("chisurf")
    editor.document.text = "gui:\n  plot:\n    font_size: 18\n"
    assert editor.save()
    assert settings.cs_settings["gui"]["plot"]["font_size"] == 18
    assert settings.gui["plot"]["font_size"] == 18
    editor._invalid_fields["gui.plot.colors"] = "Incomplete list"
    assert not editor.save()
    assert "invalid" in editor.error
    app.close()
