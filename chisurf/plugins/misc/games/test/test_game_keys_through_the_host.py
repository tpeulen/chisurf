"""Keys reach the emtk games through the host they are opened in, presses AND releases.

Regression guard for "keys do not land": a host once forwarded presses only, so a game
never saw a key go up -- the key stayed held, the action kept going, and the next press
of the same key was dropped as a repeat. Each game is built from its manifest's
``entrypoints.emtk`` (what the menu opens) and driven by :class:`emtk.testing.Driver`
through the native host's surface. How the Qt host turns ``QKeyEvent`` presses,
releases, auto-repeat releases and focus changes into these calls is emtk's own
``tests/test_qt_host.py``; the native window releases every held key when it loses
focus (``emtk.native``'s focus callback), and the Qt host calls ``focus_lost``.
"""

from __future__ import annotations

import importlib
import pathlib

from emtk.keys import KEY_LEFT, KEY_RIGHT, KEY_UP
from emtk.testing import Driver

from chisurf.core.plugin import load_manifest

GAMES = pathlib.Path(__file__).resolve().parents[1]


def _open(game):
    """The game's emtk app, built as the menu builds it, in a driver."""
    module, factory = load_manifest(GAMES / game / "manifest.json").entrypoints.emtk.split(":")
    app = getattr(importlib.import_module(module), factory)()
    drv = Driver(app, size=(800, 600))
    drv.frame()
    return drv


def _press(drv, key):
    drv.surface.on_key_press(key, "", 0)
    drv.frame()


def _release(drv, key):
    drv.surface.on_key_release(key, "", 0)
    drv.frame()


def test_number_quest_steps_once_per_press_and_releases():
    drv = _open("number_quest")
    app = drv.app
    start = app.estimate
    for _ in range(3):
        drv.press(KEY_RIGHT)
    assert app.estimate == start + 3  # every press lands
    assert not app.held


def test_minesweeper_cursor_moves_per_press_and_releases():
    drv = _open("minesweeper")
    app = drv.app
    app.cursor_row, app.cursor_col = 0, 0
    for _ in range(2):
        drv.press(KEY_RIGHT)
    assert app.cursor_col == 2 and not app.held


def test_pong_paddle_stops_when_the_key_goes_up():
    drv = _open("pong")
    app = drv.app
    _press(drv, KEY_UP)
    assert "up" in app.keys.held
    _press(drv, KEY_UP)  # auto-repeat (a native window repeats presses): still held
    assert "up" in app.keys.held
    _release(drv, KEY_UP)
    assert "up" not in app.keys.held


def test_tetris_left_releases():
    drv = _open("tetris")
    app = drv.app
    drv.press(KEY_LEFT)
    assert "left" not in app.keys.held


def test_focus_loss_releases_held_keys():
    drv = _open("pong")
    app = drv.app
    _press(drv, KEY_UP)
    app.focus_lost()  # the Qt host's call when the window loses focus
    assert not app.keys.held
    _press(drv, KEY_UP)
    _release(drv, KEY_UP)  # the native window's: a release for every held key
    assert not app.keys.held


def test_keys_reach_the_game_selected_in_the_launcher():
    drv = _open("")
    hub = drv.app
    for name in ("Number Quest", "Tetris"):
        assert hub.select(name) is not None, name  # every game opens (Tetris was 'pending')
    child = hub.select("Number Quest")
    drv.frame()
    start = child.estimate
    for _ in range(2):
        drv.press(KEY_RIGHT)
    assert child.estimate == start + 2 and not child.held
    _press(drv, KEY_RIGHT)
    hub.focus_lost()
    assert not child.held  # focus loss reaches the game


def test_the_game_shown_when_the_hub_opens_takes_keys_without_a_click():
    """The hub opens on its first game; that game must exist and receive keys before any click."""
    drv = _open("")
    hub = drv.app
    assert hub.child is not None, "the first game was only built after clicking its list entry"
    seen = []
    original = hub.child.key
    hub.child.key = lambda key, text="", modifiers=0: (
        seen.append(key),
        original(key, text, modifiers),
    )[1]
    _press(drv, KEY_LEFT)
    assert seen == [KEY_LEFT]
