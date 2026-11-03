"""The emtk ChiMOL host: chrome, data, routing, help, guide.

The loaded-structure check reads its answer from the demo PDB file itself.

Imported by absolute path (chimol's conftest loads this suite outside the
chisurf package), hence no relative imports and no ``__init__.py``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.chimol.app import ChimolHostApp, make_app
from chisurf.plugins.emtk_layout import action_caption

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())


def _demo_pdb() -> Path:
    import chimol.hosts  # a regular package even where `chimol` resolves as a namespace

    path = Path(chimol.hosts.__file__).parents[1] / "data" / "demos" / "148l.pdb"
    if not path.is_file():
        pytest.skip(f"missing demo structure {path}")
    return path


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


_ONE_LETTER = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E", "GLY": "G",
    "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P", "SER": "S",
    "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}


def _chain_sequence(pdb: Path, chain: str) -> str:
    """One-letter sequence of ``chain``: one letter per CA atom of the file's ATOM records (first
    alternate location only)."""
    return "".join(
        _ONE_LETTER[line[17:20]]
        for line in pdb.read_text().splitlines()
        if line.startswith("ATOM")
        and line[12:16] == " CA "
        and line[16] in " A"
        and line[21] == chain
    )


# 1. loading a file gives the object, the panel rows and the sequence the file holds
def test_loaded_structure_shows_the_files_object_rows_and_sequence(app):
    pdb = _demo_pdb()
    app._chimol.cmd.do(f"load {pdb}")
    _draw(app)
    names = sorted(str(getattr(o, "name", "")) for o in app._chimol.viewer.objects.values())
    assert names == [pdb.stem]  # one object, named after the file
    gui = app._chimol.renderer._internal_gui
    # the panel: "all", the object, and the default selection (PyMOL's rows)
    assert [row.name for row in gui.rows] == ["all", pdb.stem, "sele"]
    # the strip: one sequence row per object; each chain is its marker, a space, its residues
    (seq,) = gui.sequences
    assert seq.name == pdb.stem
    codes = "".join(seq.codes)
    expected = _chain_sequence(pdb, "E")
    assert len(expected) > 100
    assert codes.startswith("E " + expected + "S ")


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
        assert any(action_caption("help") == s for s in painter.strings) and any(
            action_caption("guide") == s for s in painter.strings
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


# 8. persistence
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
