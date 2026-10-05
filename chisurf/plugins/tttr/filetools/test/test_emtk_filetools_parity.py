"""The native File tools hub at parity with the Qt FileToolsTool.

The Qt hub runs in a subprocess (this process stays Qt-free): its panel list is compared
with the emtk hub's, and every panel must open its child's own emtk app. The hub's own
behaviour -- navigation by pointer, frames only while the child needs them, a guide
that waits for a tool to be opened, drops and keys routed to the open child -- is
driven here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from emtk.testing import PixelPainter, RecordingPainter

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
PANELS = json.loads((HERE.parent / "gui" / "panels.json").read_text())["panels"]

from chisurf.plugins.tttr.filetools.gui.app import FileToolsApp, caption  # noqa: E402


def _draw(app, size=(1200, 800), n=2, painter=RecordingPainter):
    out = None
    for _ in range(n):
        out = painter(*size) if painter is PixelPainter else painter()
        app.draw(out, 0, 0, *size)
    return out


_QT = r"""
import json
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chisurf.plugins.tttr.filetools.gui.tool import FileToolsTool
w = FileToolsTool()
rows = [w.nav_list.item(i).text() for i in range(w.nav_list.count())]
print("FACTS" + json.dumps({"rows": rows}))
"""


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT], capture_output=True, text=True, timeout=300, env=env,
                          cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS"):])


# 1. the Qt hub's tools, in its order; every one opens its own emtk app
def test_the_tools_are_the_qt_hubs_and_each_opens_natively(qt):
    app = FileToolsApp()
    try:
        names = [p["name"] for p in app.panels]
        assert len(qt["rows"]) == len(names) == 7
        for qt_row, name in zip(qt["rows"], names):
            assert name in qt_row                                     # the Qt row is icon + name
        for panel in app.panels:
            child = app.select(panel["role"])
            assert child is not None and panel["role"] not in app.errors, app.errors.get(panel["role"])
            _draw(app, n=1)
    finally:
        app.close()


def test_a_child_that_cannot_open_breaks_only_its_panel():
    app = FileToolsApp(resolver=lambda panel: None if panel["role"] == "pto_inspector" else
                       __import__("chisurf.plugins.tttr.filetools.gui.app", fromlist=["x"]).native_factory(panel))
    try:
        assert app.select("pto_inspector") is None
        strings = " ".join(_draw(app).strings)
        assert "Native panel pending" in strings and "Retry" in strings
        assert app.select("tttr_header_edit") is not None                 # the rest of the hub works
    finally:
        app.close()


# navigation by pointer; the captions carry no stray glyphs
def test_a_press_on_a_list_entry_opens_that_tool():
    app = FileToolsApp()
    size = (1200, 800)
    try:
        _draw(app, size, painter=PixelPainter)
        x, y, w, h = app.item_rects["nav_tttr_header_edit"]
        app.pointer_move(x + w / 2, y + h / 2)
        app.press(x + w / 2, y + h / 2)
        _draw(app, size, n=1, painter=PixelPainter)
        app.release()
        _draw(app, size, n=1, painter=PixelPainter)
        assert app.selected == "tttr_header_edit"
        assert all("️" not in caption(p) for p in PANELS)
        strings = _draw(app).strings
        assert caption(PANELS[3]) in strings and all("️" not in s for s in strings)
    finally:
        app.close()


def test_the_filter_hides_what_does_not_match():
    app = FileToolsApp()
    try:
        app.select("tttr_header_edit")
        app.filter = "header"
        strings = _draw(app).strings
        assert strings.count(caption(PANELS[3])) == 2               # the list entry and the description strip
        assert caption(PANELS[0]) not in strings
    finally:
        app.close()


# frames: only while the open child (or the hub) needs them
def test_frames_follow_the_open_child(monkeypatch):
    app = FileToolsApp()
    try:
        child = app.select("pto_inspector")          # renders on demand (most children render continuously)
        _draw(app)
        assert not child.animating() and not app.animating()
        monkeypatch.setattr(child, "animating", lambda: True)
        assert app.animating()
        monkeypatch.setattr(child, "next_frame_in", lambda: 0.25)
        assert app.next_frame_in() == 0.25
    finally:
        app.close()


# drops and keys reach the open child
def test_drops_and_keys_reach_the_open_child(monkeypatch, tmp_path):
    app = FileToolsApp()
    try:
        child = app.select("tttr_header_edit")
        received, keys = [], []
        hook = "files_dropped" if callable(getattr(child, "files_dropped", None)) else "on_paths_dropped"
        monkeypatch.setattr(child, hook, lambda paths: received.append(paths))
        assert app.files_dropped([str(tmp_path / "a.ptu")])
        assert received == [[str(tmp_path / "a.ptu")]]
        monkeypatch.setattr(child, "key", lambda *args: keys.append(args) or True)
        _draw(app)
        x, y, w, h = app.child_box
        app.pointer_press(x + 20, y + 20, 0)
        app.key(65, "a", 0)
        assert keys and keys[-1][:2] == (65, "a")
    finally:
        app.close()


# guide: every target drawn; the converter step waits until a converter is opened
def test_the_guide_points_at_real_controls_and_waits():
    app = FileToolsApp()
    try:
        app.select("tttr_header_edit")
        _draw(app)
        steps = app.tour.steps
        keys = {app.tour._target_key(s.get("target")) for s in steps} - {""}
        assert keys == {"nav_split_convert", "description", "nav_tttr_header_edit", "search", "panel"}
        assert keys <= set(app.item_rects)
        index = next(i for i, s in enumerate(steps) if s.get("await"))
        app.tour.start(index)
        assert app.tour.awaiting
        assert steps[index]["title"] in " ".join(_draw(app, n=1).strings)
        app.select("pto_inspector")
        assert app.tour.awaiting                                        # not the converter
        app.select("split_convert")
        assert not app.tour.awaiting
    finally:
        app.tour.active = False
        app.close()


# 4. draws at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_draws(size):
    app = FileToolsApp()
    try:
        strings = _draw(app, size).strings
        assert {"Guide", "Help"} <= set(strings) and caption(PANELS[0]) in strings
        x, y, w, h = app.child_box
        assert x + w <= size[0] + 0.5 and y + h <= size[1] + 0.5
    finally:
        app.close()


def test_help_opens_with_its_page():
    app = FileToolsApp()
    try:
        app.help.show()
        assert app.help.open and "acts on a" in " ".join(_draw(app).strings)
    finally:
        app.close()


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("filetools")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    app = build_emtk_app("filetools")
    try:
        assert emtk_inventory(app)["controls_without_tooltip"] == []
    finally:
        app.close()
