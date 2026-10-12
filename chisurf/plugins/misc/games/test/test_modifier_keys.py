"""Plain and Shift/keypad game keys work; application shortcuts stay reserved."""

import importlib

import pytest
from emtk.events import ALT_MODIFIER, CONTROL_MODIFIER, META_MODIFIER, SHIFT_MODIFIER
from emtk.keys import KEY_RIGHT, KEY_UP

FACTORIES = [
    "chisurf.plugins.misc.games.pong.app",
    "chisurf.plugins.misc.games.tetris.app",
    "chisurf.plugins.misc.games.breakout.app",
    "chisurf.plugins.misc.games.minesweeper.gui.app",
    "chisurf.plugins.misc.games.number_quest.gui.app",
]


@pytest.mark.parametrize("module", FACTORIES)
def test_shift_and_keypad_are_not_application_shortcuts(module):
    app = importlib.import_module(module).make_app()
    try:
        key = KEY_UP if module.endswith("pong.app") else KEY_RIGHT
        assert app.key(key, "", SHIFT_MODIFIER)
        app.key_release(key)
        assert app.key(key, "", 0x20000000)
        app.key_release(key)
        for modifier in (CONTROL_MODIFIER, ALT_MODIFIER, META_MODIFIER):
            assert not app.key(key, "", modifier)
    finally:
        close = getattr(app, "close", None)
        if close is not None:
            close()


@pytest.mark.parametrize("module", FACTORIES)
def test_keypad_arrows_reach_games_through_the_host(module):
    """A Shift+keypad arrow arrives as the plain arrow with Shift, and the game takes it.

    Every host strips the keypad bit before the control sees the key: emtk's
    ``tests/test_qt_host.py`` proves it for the Qt host; here the native host
    (:class:`emtk.testing.Driver`, the glfw window's surface) delivers the press and release.
    """
    from emtk.testing import Driver

    app = importlib.import_module(module).make_app()
    seen = []
    original = app.key

    def record(code, text="", modifiers=0):
        accepted = original(code, text, modifiers)
        seen.append((code, modifiers, accepted))
        return accepted

    app.key = record
    try:
        drv = Driver(app, size=(800, 600))
        drv.frame()
        key = KEY_UP if module.endswith("pong.app") else KEY_RIGHT
        drv.press(key, SHIFT_MODIFIER)
        assert seen == [(key, SHIFT_MODIFIER, True)]
    finally:
        close = getattr(app, "close", None)
        if close is not None:
            close()
