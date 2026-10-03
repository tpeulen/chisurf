"""Native toolbox routing, persistence and input ownership."""

import os
import subprocess
import sys

import pytest


def test_every_original_route_under_hard_qt_blocker(tmp_path):
    code = r"""
import sys
from chisurf.emtk.validation import BlockQt
sys.meta_path.insert(0, BlockQt())
from emtk.testing import RecordingPainter
from chisurf.plugins.tttr.tttr_toolbox.gui.app import make_app
from chisurf.emtk.i18n import SUPPORTED_LOCALES, set_locale
app = make_app()
assert len(app.tools) == 6
for panel in app.tools:
    child = app.select(panel['role'])
    assert child is not None, app.errors
    assert app.routes[panel['role']]
    for width, height in [(1200,750),(800,600),(600,500)]:
        painter = RecordingPainter()
        for _ in range(2): app.draw(painter,0,0,width,height)
        assert painter.strings
    app.show_child_help()
    app.draw(RecordingPainter(),0,0,1000,700)
    app.child_help.open = False
for locale in SUPPORTED_LOCALES:
    set_locale(locale)
    app.draw(RecordingPainter(),0,0,1000,700)
set_locale('en')
state=app.export_settings()
other=make_app()
other.restore_settings(state)
assert other.selected == app.selected
assert set(state['children']).issubset(other.children)
assert app.selected in other.children
app.close();other.close()
assert not any(m.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','pyqtgraph'} for m in sys.modules)
"""
    env = dict(os.environ, CHISURF_SETTINGS_DIR=str(tmp_path), MPLCONFIGDIR=str(tmp_path / "mpl"))
    process = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=90
    )
    assert process.returncode == 0, process.stdout + process.stderr


def fake_child():
    from emtk.app import ImApp

    class Child(ImApp):
        def __init__(self):
            super().__init__(lambda: None)
            self.calls = []
            self.value = 1

        def key(self, *args):
            self.calls.append(("key", args))
            return True

        def pointer_press(self, *args):
            self.calls.append(("press", args))

        def pointer_release(self, *args):
            self.calls.append(("release", args))

        def wheel(self, *args):
            self.calls.append(("wheel", args))

        def export_settings(self):
            return {"value": self.value}

        def restore_settings(self, data):
            self.value = data["value"]

        def close(self):
            self.calls.append(("close", ()))

    return Child()


def test_route_errors_stay_visible_and_retry():
    from emtk.testing import RecordingPainter

    from chisurf.plugins.tttr.tttr_toolbox.gui.app import make_app

    attempts = []

    def resolver(panel):
        attempts.append(panel["role"])
        if len(attempts) == 1:
            return None, ""
        if len(attempts) == 2:
            raise RuntimeError("broken child dependency")
        return fake_child, "test:child"

    app = make_app(resolver=resolver)
    role = app.selected
    assert app.select(role) is None
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 800, 600)
    assert any("no native EMTK" in text for text in painter.strings)
    assert len(app.tools) == 6
    app.select(role, retry=True)
    assert app.errors[role] == "broken child dependency"
    assert app.select(role, retry=True)
    assert role not in app.errors
    assert len(attempts) == 3
    with pytest.raises(ValueError):
        app.select("not-a-route")
    app.close()


def test_input_focus_capture_and_overlay():
    from emtk.events import LEFT_BUTTON

    from chisurf.plugins.tttr.tttr_toolbox.gui.app import make_app

    app = make_app(resolver=lambda panel: (fake_child, "test:child"))
    child = app.select(app.selected)
    app.pointer_press(250, 120, LEFT_BUTTON)
    assert child.calls[-1] == ("press", (20, 120 - 62, LEFT_BUTTON, 0, 1))
    app.key(65, "a")
    assert child.calls[-1][0] == "key"
    # A release outside the child still finishes its captured drag.
    app.pointer_release(10, 10, LEFT_BUTTON)
    assert child.calls[-1][0] == "release"
    app.wheel(250, 120, 2)
    assert child.calls[-1] == ("wheel", (20, 120 - 62, 2, 0))
    count = len(child.calls)
    app.pointer_press(20, 120, LEFT_BUTTON)
    app.key(65, "a")
    assert len(child.calls) == count
    app.help.show()
    app.pointer_press(250, 120, LEFT_BUTTON)
    app.key(65, "a")
    app.wheel(250, 120, 2)
    assert len(child.calls) == count
    app.close()


def test_search_and_child_settings_preserve_navigation():
    from chisurf.plugins.tttr.tttr_toolbox.gui.app import make_app

    app = make_app(resolver=lambda panel: (fake_child, "test:child"))
    first = app.select("alex_creator")
    first.value = 42
    app.select("audifier")
    assert app.select("alex_creator") is first
    app.select("count_rate")
    app.filter = "detector"
    assert any(p["role"] == "count_rate" for p in app.matching_panels())
    app.filter = "nonsense-no-match"
    assert not app.matching_panels()
    other = make_app(resolver=lambda panel: (fake_child, "test:child"))
    other.restore_settings(app.export_settings())
    assert other.selected == "count_rate"
    assert other.children["alex_creator"].value == 42
    other.restore_settings({"selected": "removed", "children": {"removed": {}}})
    assert other.selected == "count_rate"
    app.close()
    other.close()


def test_manifest_routes_are_resolved_at_use_time(tmp_path, monkeypatch):
    import json

    from chisurf.plugins.tttr.tttr_toolbox.gui import app

    path = tmp_path / "manifest.json"
    monkeypatch.setattr(app, "manifest_path", lambda panel: path)
    path.write_text(json.dumps({"entrypoints": {}}))
    assert app.resolve_factory({}) == (None, "")
    path.write_text(json.dumps({"entrypoints": {"emtk": "builtins:list"}}))
    factory, spec = app.resolve_factory({})
    assert factory() == [] and spec == "builtins:list"


def test_tooltips_drop_and_native_locales(monkeypatch):
    from emtk import im
    from emtk.i18n import tr
    from emtk.testing import RecordingPainter

    from chisurf.emtk.i18n import SUPPORTED_LOCALES, set_locale
    from chisurf.plugins.tttr.tttr_toolbox.gui.app import make_app

    app = make_app(resolver=lambda panel: (fake_child, "test:child"))
    child = app.select(app.selected)
    dropped = []
    child.on_paths_dropped = lambda paths: dropped.extend(paths)
    assert app.on_files_dropped(["source.ptu"])
    assert dropped == ["source.ptu"]
    app.help.show()
    assert not app.on_files_dropped(["ignored.ptu"])
    app.help.open = False
    tips = []
    original = im.set_item_tooltip

    def record(text):
        tips.append(text)
        original(text)

    monkeypatch.setattr(im, "set_item_tooltip", record)
    app.draw(RecordingPainter(), 0, 0, 1200, 750)
    assert all(p["description"] in tips for p in app.tools)
    assert "test:child" in tips
    assert any("Find tools" in tip for tip in tips)
    try:
        for locale in SUPPORTED_LOCALES:
            set_locale(locale)
            if locale != "en":
                assert tr("Tool help") != "Tool help"
                assert (
                    tr("Find tools by name, description or route.")
                    != "Find tools by name, description or route."
                )
            app.draw(RecordingPainter(), 0, 0, 800, 600)
    finally:
        set_locale("en")
        app.close()
