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
def test_keypad_arrows_reach_games_through_qt_host(module):
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui, QtWidgets

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app = importlib.import_module(module).make_app()
    seen = []
    original = app.key

    def record(code, text="", modifiers=0):
        accepted = original(code, text, modifiers)
        seen.append((code, modifiers, accepted))
        return accepted

    app.key = record
    host = ControlHost(app)
    try:
        key = KEY_UP if module.endswith("pong.app") else KEY_RIGHT
        qt_key = QtCore.Qt.Key_Up if key == KEY_UP else QtCore.Qt.Key_Right
        mods = QtCore.Qt.KeypadModifier | QtCore.Qt.ShiftModifier
        qapp.sendEvent(host, QtGui.QKeyEvent(QtCore.QEvent.KeyPress, qt_key, mods))
        qapp.sendEvent(host, QtGui.QKeyEvent(QtCore.QEvent.KeyRelease, qt_key, mods))
        assert seen == [(key, SHIFT_MODIFIER, True)]
    finally:
        host.close()
