"""The native Pong: the keys ``gui/help.md`` documents for both players, scripted keys, the Sound switch."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from emtk.keys import KEY_DOWN, KEY_ENTER, KEY_ESCAPE, KEY_LEFT, KEY_RIGHT, KEY_UP
from emtk.testing import RecordingPainter

from chisurf.plugins.emtk_layout import SOUND_OFF_ICON, action_caption
from chisurf.plugins.misc.games.pong.app import PongApp, make_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())

#: The controls ``gui/help.md`` lists for the first paddle: key -> the model action that does it.
PLAYER_1 = {
    "ArrowUp": "up",
    "ArrowLeft": "up",
    "ArrowDown": "down",
    "ArrowRight": "down",
    "Enter": "confirm",  # another round after a winner
    " ": "confirm",
    "p": "menu",  # pause / resume
    "r": "cancel",  # restart
    "Escape": "cancel",
    "m": "shoulder_l",  # computer / two-player
    "n": "shoulder_r",  # mute flag
}
#: ... and for the second paddle in two-player mode.
PLAYER_2 = {"w": "up", "s": "down"}
KEYCODE = {
    "ArrowUp": (KEY_UP, ""),
    "ArrowDown": (KEY_DOWN, ""),
    "ArrowLeft": (KEY_LEFT, ""),
    "ArrowRight": (KEY_RIGHT, ""),
    "Enter": (KEY_ENTER, ""),
    "Escape": (KEY_ESCAPE, ""),
}


def _code(key):
    return KEYCODE.get(key, (ord(key) if len(key) == 1 else 0, key if len(key) == 1 else ""))


# 2. the documented keys, both players
def test_the_documented_keys_are_bound():
    for key, action in PLAYER_1.items():
        assert PongApp.binding(*_code(key)) == (action, False), key
    for key, action in PLAYER_2.items():
        assert PongApp.binding(*_code(key)) == (action, True), key


def test_keys_pause_switch_the_opponent_and_restart():
    app = make_app()
    game = app.game
    game.serve_timer = 0.0
    app.key(ord("p"), "p")
    assert game.paused is True
    app.key_release(ord("p"), "p")
    app.key(ord("p"), "p")
    assert game.paused is False
    vs = game.vs_computer
    app.key(ord("m"), "m")
    assert game.vs_computer is (not vs)
    game.player_score = 5
    app.key(ord("r"), "r")
    assert game.player_score == 0


def test_sound_is_greyed_without_an_audio_output_and_works_with_one():
    app = make_app()
    app.set_sound()
    assert app.sound_enabled is False
    calls = []
    audio = SimpleNamespace(
        sfx=lambda *a: calls.append(("sfx", a)),
        set_enabled=lambda on: calls.append(("on", on)),
        close=lambda: None,
    )
    app = make_app(audio=audio)
    app.set_sound()
    assert app.sound_enabled is True and ("on", True) in calls
    app.game._sfx("paddle", 660.0)
    assert ("sfx", ("paddle", 660.0)) in calls


@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (820, 640)])
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

    result = qt_free("pong")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("pong"))["controls_without_tooltip"] == []
