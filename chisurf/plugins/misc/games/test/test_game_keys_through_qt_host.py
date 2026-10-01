"""Keys reach the emtk games through the Qt host ChiSurf opens them in, presses AND releases.

Regression guard for "keys do not land": emtk's ControlHost forwarded presses only,
so a game never saw a key go up -- the key stayed held, the action kept going, and
the next press of the same key was dropped as a repeat. Each game is opened the way
the menu opens it (``build_plugin_widget`` -> ControlHost) and driven with real
QKeyEvents.
"""

from __future__ import annotations

import pathlib

import pytest

qtpy = pytest.importorskip("qtpy")
from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402

GAMES = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _host(qapp, game):
    from chisurf.core.plugin import load_manifest
    from chisurf.core.plugin.registry import build_plugin_widget

    host = build_plugin_widget(load_manifest(GAMES / game / "manifest.json"))
    host.resize(800, 600)
    return host


def _send(qapp, host, kind, key, repeat=False):
    qapp.sendEvent(host, QtGui.QKeyEvent(kind, key, QtCore.Qt.NoModifier, "", repeat))


def _press(qapp, host, key):
    _send(qapp, host, QtCore.QEvent.KeyPress, key)


def _release(qapp, host, key):
    _send(qapp, host, QtCore.QEvent.KeyRelease, key)


def test_number_quest_steps_once_per_press_and_releases(qapp):
    host = _host(qapp, "number_quest")
    app = host.control
    start = app.estimate
    for _ in range(3):
        _press(qapp, host, QtCore.Qt.Key_Right)
        _release(qapp, host, QtCore.Qt.Key_Right)
    assert app.estimate == start + 3          # every press lands
    assert not app.held


def test_minesweeper_cursor_moves_per_press_and_releases(qapp):
    host = _host(qapp, "minesweeper")
    app = host.control
    app.cursor_row, app.cursor_col = 0, 0
    for _ in range(2):
        _press(qapp, host, QtCore.Qt.Key_Right)
        _release(qapp, host, QtCore.Qt.Key_Right)
    assert app.cursor_col == 2 and not app.held


def test_pong_paddle_stops_when_the_key_goes_up(qapp):
    host = _host(qapp, "pong")
    app = host.control
    _press(qapp, host, QtCore.Qt.Key_Up)
    assert "up" in app.keys.held
    _send(qapp, host, QtCore.QEvent.KeyRelease, QtCore.Qt.Key_Up, repeat=True)   # auto-repeat: still held
    assert "up" in app.keys.held
    _release(qapp, host, QtCore.Qt.Key_Up)
    assert "up" not in app.keys.held


def test_tetris_left_releases(qapp):
    host = _host(qapp, "tetris")
    app = host.control
    _press(qapp, host, QtCore.Qt.Key_Left)
    _release(qapp, host, QtCore.Qt.Key_Left)
    assert "left" not in app.keys.held


def test_focus_loss_releases_held_keys(qapp):
    host = _host(qapp, "pong")
    app = host.control
    _press(qapp, host, QtCore.Qt.Key_Up)
    qapp.sendEvent(host, QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    assert not app.keys.held
