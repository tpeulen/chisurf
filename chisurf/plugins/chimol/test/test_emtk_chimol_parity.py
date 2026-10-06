"""The emtk ChiMOL host at parity with the Qt window: chrome, data, routing, help, guide.

Both hosts draw the same chimol viewer, so parity is measured on what each one
*holds* after the same actions -- the menu and toolbar tables, the object list,
the atom count -- not on pixels. The Qt window is built in a subprocess: once
Qt is imported, ``chimol.core.viewer`` binds a QWidget base, and the emtk host
in this process must stay toolkit-free (``test_port_is_qt_free``).

Imported by absolute path (chimol's conftest loads this suite outside the
chisurf package), hence no relative imports and no ``__init__.py``.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.chimol.app import ChimolHostApp, make_app

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())


def _demo_pdb() -> Path:
    import chimol.hosts  # a regular package even where `chimol` resolves as a namespace

    path = Path(chimol.hosts.__file__).parents[1] / "data" / "demos" / "148l.pdb"
    if not path.is_file():
        pytest.skip(f"missing demo structure {path}")
    return path


def _flatten(entries, prefix=""):
    out = []
    for entry in entries:
        if not entry.label:
            continue
        out.append((prefix + entry.label, entry.command))
        out.extend(_flatten(entry.children, prefix + entry.label + "/"))
    return out


def _chrome(gui) -> dict:
    return {
        "menus": [[title, _flatten(entries)] for title, entries in gui.menubar],
        "toolbar": [list(row) for row in gui.toolbar],
    }


def _draw(app, size=(1200, 800), times=3):
    painter = RecordingPainter()
    for _ in range(times):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


@pytest.fixture
def app():
    app = make_app()
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    if app._chimol_error:
        pytest.skip(f"chimol unavailable: {app._chimol_error}")
    yield app
    app.close()


_QT_FACTS = r"""
import json, os, sys
from qtpy import QtWidgets
qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
from chimol.hosts.qt import MolViewPluginWindow
def flat(entries, prefix=""):
    out = []
    for e in entries:
        if not e.label:
            continue
        out.append((prefix + e.label, e.command))
        out.extend(flat(e.children, prefix + e.label + "/"))
    return out
w = MolViewPluginWindow()
w.resize(1200, 800)
gui = w.viewer.renderer._internal_gui
w.cmd.do("load " + sys.argv[1])
for _ in range(5):
    qapp.processEvents()
names = [str(getattr(o, "name", "")) for o in w.viewer.objects.values()]
print("FACTS" + json.dumps({
    "menus": [[t, flat(e)] for t, e in gui.menubar],
    "toolbar": [list(r) for r in gui.toolbar],
    "objects": sorted(names),
    "n_atoms": int(len(w.viewer.atom_xyz) if getattr(w.viewer, "atom_xyz", None) is not None else -1),
}))
"""


@pytest.fixture(scope="module")
def qt_facts():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT_FACTS, str(_demo_pdb())],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"Qt window could not be built here: {proc.stderr[-800:]}")
    return json.loads(line[len("FACTS") :])


# 1. the same data gives the same viewer state as in the Qt window
def test_loaded_structure_matches_the_qt_window(app, qt_facts):
    app._chimol.cmd.do(f"load {_demo_pdb()}")
    _draw(app)
    names = sorted(str(getattr(o, "name", "")) for o in app._chimol.viewer.objects.values())
    assert names == qt_facts["objects"]
    viewer = app._chimol.viewer
    n_atoms = int(len(viewer.atom_xyz)) if getattr(viewer, "atom_xyz", None) is not None else -1
    assert n_atoms == qt_facts["n_atoms"]


def test_menus_and_toolbar_match_the_qt_window(app, qt_facts):
    """Every menu entry and toolbar button of the Qt window, with the same command."""
    ours = json.loads(json.dumps(_chrome(app._chimol.renderer._internal_gui)))
    assert ours["menus"] == qt_facts["menus"]
    assert ours["toolbar"] == qt_facts["toolbar"]


# 2. the host's actions, and an error that must not escape
def test_help_and_guide_open_and_a_bad_load_reports(app):
    assert not app.help_window.open
    app.help_window.show()
    assert app.help_window.open
    app.help_window.hide()
    app.tour.start()
    assert app.tour.active and app.tour.step_idx == 0
    app.tour.stop()
    before = app._object_count()
    app._chimol.cmd.do("load /no/such/file.pdb")  # reported at the prompt, not raised
    _draw(app)
    assert app._object_count() == before


def test_a_click_on_help_does_not_reach_chimol(app, monkeypatch):
    calls = []
    monkeypatch.setattr(
        app._chimol.renderer, "on_pointer_press", lambda *a, **k: calls.append(("press", a))
    )
    _draw(app)
    hx, hy, hw, hh = app.item_rects["help"]
    app.pointer_move(hx + hw / 2, hy + hh / 2, 0)
    _draw(app, times=1)
    app.pointer_press(hx + hw / 2, hy + hh / 2, 0)
    assert calls == [], "the status strip belongs to the host"
    vx, vy, vw, vh = app.item_rects["viewport"]
    app.pointer_release(hx + hw / 2, hy + hh / 2, 0)
    app.pointer_move(vx + vw / 2, vy + vh / 2, 0)
    _draw(app, times=1)
    app.pointer_press(vx + vw / 2, vy + vh / 2, 0)
    assert len(calls) == 1, "a click on the molecule reaches chimol"


# 3. (no spec: the surface is chimol's chrome) -- the guide's targets are real regions
def test_every_guide_target_is_a_drawn_region(app):
    _draw(app)
    steps = json.loads((PLUGIN / "guide.json").read_text(encoding="utf-8"))["steps"]
    for step in steps:
        key = app.tour._target_key(step.get("target"))
        if key:
            assert key in app.item_rects, key
            x, y, w, h = app.item_rects[key]
            assert w > 0 and h > 0 and 0 <= y and y + h <= 800, (key, app.item_rects[key])


# 4. draws empty and populated at both sizes
@pytest.mark.parametrize("size", [(1200, 800), (800, 600)])
def test_app_draws_empty_and_populated(size):
    app = make_app()
    try:
        painter = _draw(app, size)
        if app._chimol_error:
            pytest.skip(app._chimol_error)
        empty = app._object_count()
        assert any(f"{empty} object(s)" in s for s in painter.strings)
        assert any("Help" == s for s in painter.strings) and any(
            "Guide" == s for s in painter.strings
        )
        app._chimol.cmd.do(f"load {_demo_pdb()}")
        painter = _draw(app, size)
        assert any(f"{empty + 1} object(s)" in s for s in painter.strings)
        assert app._frame is not None and app._frame.shape[1] >= 760
    finally:
        app.close()


# 5. the workflow the guide walks, through the host's own event path
def test_the_tour_waits_for_load_drag_and_command(app):
    app.tour.start(1)
    assert app.tour.awaiting  # Open a structure
    app._chimol.cmd.do(f"load {_demo_pdb()}")
    _draw(app)
    assert not app.tour.awaiting
    app.tour.next()  # Turn it
    assert app.tour.awaiting
    vx, vy, vw, vh = app.item_rects["viewport"]
    cx, cy = vx + vw / 2, vy + vh / 2
    app.pointer_move(cx, cy, 0)
    _draw(app, times=1)
    app.pointer_press(cx, cy, 0)
    app.pointer_move(cx + 40, cy + 10, 1)
    app.pointer_release(cx + 40, cy + 10, 0)
    assert not app.tour.awaiting
    app.tour.next()  # Say it instead
    assert app.tour.awaiting
    app._chimol.cmd.do("show sticks")
    assert not app.tour.awaiting
    app.tour.next()
    assert app.tour.step_idx == 4 and not app.tour.awaiting


# 6. no Qt, no chisurf.gui
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("chimol")
    assert result["ok"], result["output"]


# 7. every control has a tooltip
def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inv = emtk_inventory(build_emtk_app("chimol"))
    assert inv["controls_without_tooltip"] == []
    assert {"help", "guide"} <= set(inv["controls"])  # normalised labels


# 8. persistence: the Qt window remembered nothing of its own (settings_key null)
def test_settings_round_trip(app):
    saved = app.export_settings()
    assert saved == {}
    json.dumps(saved)
    app.restore_settings({"anything": 1})
    assert app.export_settings() == saved
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["statefulness"]["window"]["settings_key"] is None
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.chimol.app:make_app"


def test_help_links_resolve():
    text = (PLUGIN / "help.md").read_text(encoding="utf-8")
    import re

    for target in re.findall(r"\]\((docs/[^)]+)\)", text):
        assert (REPO / target).is_file(), target
    assert ChimolHostApp.STATUS_H > 0
