"""Native hub navigation, child lifecycle, and import boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from emtk import i18n, im
from emtk.testing import RecordingPainter

from ..gui.app import GamesHubApp, make_app
from ..gui.registry import GAME_PANELS
from ..gui.translations import LOCALES


def test_factory_manifest_and_all_routes():
    manifest = json.loads((Path(__file__).parents[1] / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.misc.games.gui.app:make_app"
    app = make_app()
    assert isinstance(app, GamesHubApp)
    assert [item["name"] for item in GAME_PANELS] == ["Number Quest", "Minesweeper", "Tetris", "Pong", "Breakout"]
    for name in ("Number Quest", "Minesweeper", "Tetris", "Pong"):
        child = app.select(name)
        assert child is not None and hasattr(child, "draw")
        assert app.select(name) is child
    assert app.error == ""
    assert "Pong" in app.children
    with pytest.raises(ValueError):
        app.select("Unknown")
    app.close()
    assert not app.children


def test_render_pending_and_populated_child_with_tooltips(monkeypatch):
    app = make_app()
    tips = []
    monkeypatch.setattr(im, "set_item_tooltip", tips.append)
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 1060, 730)
    assert any("Number Quest" in value for value in painter.strings)
    assert any("Breakout (not available)" in value for value in painter.strings)
    assert any("Guess the hidden number" in value for value in tips)
    app.select("Tetris")
    app.draw(painter, 0, 0, 1060, 730)
    assert any("Left/Right move" in value for value in painter.strings)      # the keys line
    app.select("Minesweeper")
    app.draw(painter, 0, 0, 720, 680)
    assert app.child.game is not None


def test_child_input_is_local_and_selection_preserves_state(monkeypatch):
    app = make_app()
    child = app.select("Number Quest")
    assert app.key(0, "d") is True
    assert child.estimate == 51
    app.select("Pong")
    assert app.select("Number Quest") is child
    assert child.estimate == 51

    app.child_box = (180.0, 86.0, 500.0, 500.0)
    presses = []
    monkeypatch.setattr(child, "pointer_press", lambda *args: presses.append(args))
    app.pointer_press(210, 106, 1)
    app.pointer_press(40, 40, 1)
    assert presses == [(30.0, 20.0, 1, 0, 1)]


def test_all_six_locales_have_navigation_copy():
    try:
        for locale in LOCALES:
            i18n.set_locale(locale)
            assert i18n.tr("Games", context="Games")
            assert i18n.tr("Native version pending", context="Games")
            for item in GAME_PANELS:
                assert i18n.tr(item["description"], context="Games")
    finally:
        i18n.set_locale("en")


def test_factory_blocks_qt_imports_in_clean_process():
    code = """
import builtins, sys
real = builtins.__import__
def blocked(name, *args, **kwargs):
    if name.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
        raise AssertionError('Qt import: ' + name)
    return real(name, *args, **kwargs)
builtins.__import__ = blocked
from chisurf.plugins.misc.games.gui.app import make_app
from emtk.testing import RecordingPainter
app = make_app()
app.select('Number Quest')
app.select('Minesweeper')
app.select('Pong')
app.select('Tetris')
app.draw(RecordingPainter(), 0, 0, 1060, 730)
assert not any(m.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'} for m in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
