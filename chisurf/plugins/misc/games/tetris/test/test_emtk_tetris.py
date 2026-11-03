"""The native Tetris: the keys ``gui/help.md`` documents, scripted keys, the Sound switch, drawing."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from emtk.keys import KEY_DOWN, KEY_ENTER, KEY_ESCAPE, KEY_LEFT, KEY_RIGHT, KEY_UP
from emtk.testing import RecordingPainter

from chisurf.plugins.emtk_layout import SOUND_OFF_ICON, action_caption
from chisurf.plugins.misc.games.tetris.app import TetrisApp, make_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())

#: The controls ``gui/help.md`` lists: key -> the model action that does it.
DOCUMENTED_KEYS = {
    "ArrowLeft": "left",  # move
    "ArrowRight": "right",
    "ArrowDown": "down",  # faster descent
    "ArrowUp": "confirm",  # rotate
    "Enter": "confirm",
    " ": "shoulder_r",  # drop
    "p": "menu",  # pause / resume
    "r": "cancel",  # restart
    "Escape": "cancel",
    "m": "shoulder_l",  # mute flag
}
KEYCODE = {
    "ArrowLeft": (KEY_LEFT, ""),
    "ArrowRight": (KEY_RIGHT, ""),
    "ArrowDown": (KEY_DOWN, ""),
    "ArrowUp": (KEY_UP, ""),
    "Enter": (KEY_ENTER, ""),
    "Escape": (KEY_ESCAPE, ""),
}


def test_the_documented_keys_are_bound():
    for key, action in DOCUMENTED_KEYS.items():
        code, text = KEYCODE[key] if key in KEYCODE else (ord(key), key)
        assert TetrisApp.binding(code, text) == action, key


def test_keys_pause_resume_and_hard_drop():
    app = make_app()
    game = app.game
    app.key(ord("p"), "p")
    assert game.paused is True
    app.key_release(ord("p"), "p")
    app.key(ord("p"), "p")
    assert game.paused is False
    app.key_release(ord("p"), "p")
    app.key(ord(" "), " ")  # hard drop: the piece is written into the well
    app.advance(1 / 60)
    assert sum(cell is not None for row in game.well for cell in row) == 4


def test_sound_is_greyed_without_an_audio_output_and_works_with_one():
    app = make_app()
    app.set_sound()
    assert app.sound_enabled is False
    calls = []
    audio = SimpleNamespace(
        sfx=lambda *a: calls.append(("sfx", a)),
        set_enabled=lambda on: calls.append(("on", on)),
        close=lambda: calls.append(("close",)),
    )
    app = make_app(audio=audio)
    app.set_sound()
    assert app.sound_enabled is True and ("on", True) in calls
    app.game._sfx("drop", 330.0)
    assert any(c[0] == "sfx" for c in calls)
    app.close()
    assert ("close",) in calls


@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (480, 600)])
def test_draws(size):
    app = make_app()
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    # The shared Sound toggle, off by default (chisurf.plugins.emtk_layout.sound_toggle).
    assert action_caption("sound", SOUND_OFF_ICON) in painter.strings


def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("tetris")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("tetris"))["controls_without_tooltip"] == []
