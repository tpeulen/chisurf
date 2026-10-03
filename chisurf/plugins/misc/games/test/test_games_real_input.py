"""Every game takes REAL input through the Qt host ChiSurf opens it in, with a real event loop.

QKeyEvent / QMouseEvent are delivered to the ``ControlHost`` widget exactly as Qt would, the host's own
paint timer drives the frames (real wall clock), and each test asserts that the paddle / piece / cursor /
dial actually moved: press and release, held keys, ``focus_lost``, pointer press / drag / release.
Breakout is covered here because its registry entry was ``emtk: None`` (the audit measured its draw as
"not finishing": see okf/plugins/emtk-ports/games/REPORT.md for the diagnosis).
"""

from __future__ import annotations

import pathlib
import time

import pytest

qtpy = pytest.importorskip("qtpy")
from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402

GAMES = pathlib.Path(__file__).resolve().parents[1]
K = QtCore.Qt


@pytest.fixture(autouse=True)
def _hermetic_settings(tmp_path, monkeypatch):
    """The games never touch the real ~/.chisurf: HOME and the chisurf/MMFDB folders are temporary."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "cs"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mm"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mm.db"))


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def _host(qapp, game, size=(900, 700)):
    from chisurf.core.plugin import load_manifest
    from chisurf.core.plugin.registry import build_plugin_widget

    host = build_plugin_widget(load_manifest(GAMES / game / "manifest.json"))
    host.resize(*size)
    host.show()
    pump(qapp, 0.15)
    return host


def pump(qapp, seconds):
    """Run the real event loop (paint timer included) for *seconds* of wall clock."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        qapp.processEvents()
        time.sleep(0.01)


def _key(qapp, host, kind, key, text="", repeat=False):
    qapp.sendEvent(host, QtGui.QKeyEvent(kind, key, K.NoModifier, text, repeat))


def press(qapp, host, key, text=""):
    _key(qapp, host, QtCore.QEvent.KeyPress, key, text)


def release(qapp, host, key, text=""):
    _key(qapp, host, QtCore.QEvent.KeyRelease, key, text)


def tap(qapp, host, key, text="", hold=0.05):
    press(qapp, host, key, text)
    pump(qapp, hold)
    release(qapp, host, key, text)
    pump(qapp, 0.03)


def mouse(qapp, host, kind, x, y, button=K.LeftButton, buttons=None):
    buttons = button if buttons is None else buttons
    qapp.sendEvent(host, QtGui.QMouseEvent(kind, QtCore.QPointF(x, y), button, buttons, K.NoModifier))


def click(qapp, host, x, y, button=K.LeftButton):
    mouse(qapp, host, QtCore.QEvent.MouseMove, x, y, K.NoButton, K.NoButton)
    pump(qapp, 0.05)
    mouse(qapp, host, QtCore.QEvent.MouseButtonPress, x, y, button)
    pump(qapp, 0.05)
    mouse(qapp, host, QtCore.QEvent.MouseButtonRelease, x, y, button, K.NoButton)
    pump(qapp, 0.05)


def drag(qapp, host, start, end, steps=6):
    mouse(qapp, host, QtCore.QEvent.MouseMove, *start, K.NoButton, K.NoButton)
    pump(qapp, 0.05)
    mouse(qapp, host, QtCore.QEvent.MouseButtonPress, *start)
    pump(qapp, 0.05)
    for i in range(1, steps + 1):
        x = start[0] + (end[0] - start[0]) * i / steps
        y = start[1] + (end[1] - start[1]) * i / steps
        mouse(qapp, host, QtCore.QEvent.MouseMove, x, y, K.LeftButton)
        pump(qapp, 0.03)
    mouse(qapp, host, QtCore.QEvent.MouseButtonRelease, *end, K.LeftButton, K.NoButton)
    pump(qapp, 0.05)


# --------------------------------------------------------------------------- Breakout


def test_breakout_is_enabled_in_the_registry_and_manifest():
    from chisurf.plugins.misc.games.gui.registry import GAME_PANELS

    entry = next(item for item in GAME_PANELS if item["name"] == "Breakout")
    assert entry["emtk"] == "chisurf.plugins.misc.games.breakout.app:make_app"


def test_breakout_frame_terminates_and_stays_cheap_in_the_live_loop(qapp):
    """The audit saw 'draw does not finish within 120 s'; the live loop must keep painting."""
    host = _host(qapp, "breakout")
    start = time.monotonic()
    frames = []
    original = host.control.draw
    host.control.draw = lambda *a, **k: (frames.append(1), original(*a, **k))[1]
    press(qapp, host, K.Key_Right)
    pump(qapp, 0.6)
    release(qapp, host, K.Key_Right)
    assert frames, "no frame was drawn while a key was held"
    assert time.monotonic() - start < 5


def test_breakout_paddle_follows_held_keys_and_stops_on_release(qapp):
    host = _host(qapp, "breakout")
    app = host.control
    x0 = app.game.paddle_x
    press(qapp, host, K.Key_Right)
    pump(qapp, 0.4)
    assert "right" in app.keys.held.values()
    moved = app.game.paddle_x
    assert moved > x0 + 20
    release(qapp, host, K.Key_Right)
    assert not app.keys.held
    pump(qapp, 0.2)
    after = app.game.paddle_x
    pump(qapp, 0.2)
    assert app.game.paddle_x == after, "the paddle kept moving after the key went up"
    press(qapp, host, K.Key_Left)
    pump(qapp, 0.3)
    release(qapp, host, K.Key_Left)
    assert app.game.paddle_x < after - 10


def test_breakout_letter_keys_a_d_steer_and_a_key_up_keeps_the_other_held(qapp):
    host = _host(qapp, "breakout")
    app = host.control
    x0 = app.game.paddle_x
    press(qapp, host, K.Key_D, "d")
    pump(qapp, 0.3)
    assert app.game.paddle_x > x0
    press(qapp, host, K.Key_Right)          # both held
    release(qapp, host, K.Key_Right)        # Right up, D still down
    assert "right" in app.keys.held.values()
    release(qapp, host, K.Key_D, "d")
    assert not app.keys.held


def test_breakout_space_launches_the_ball_and_the_ball_moves(qapp):
    host = _host(qapp, "breakout")
    game = host.control.game
    assert game.stuck
    tap(qapp, host, K.Key_Space, " ")
    assert not game.stuck and game.ball_vy < 0
    y0 = game.ball_y
    pump(qapp, 0.3)
    assert game.ball_y != y0


def test_breakout_pause_reset_and_mute_keys(qapp):
    host = _host(qapp, "breakout")
    app = host.control
    tap(qapp, host, K.Key_Space, " ")
    tap(qapp, host, K.Key_P, "p")
    assert app.game.paused
    y = app.game.ball_y
    pump(qapp, 0.3)
    assert app.game.ball_y == y, "the ball moved while paused"
    tap(qapp, host, K.Key_P, "p")
    assert not app.game.paused
    muted = app.game.muted
    tap(qapp, host, K.Key_M, "m")
    assert app.game.muted != muted
    tap(qapp, host, K.Key_R, "r")
    assert app.game.stuck and app.game.score == 0


def test_breakout_focus_loss_releases_every_held_key(qapp):
    host = _host(qapp, "breakout")
    app = host.control
    press(qapp, host, K.Key_Right)
    press(qapp, host, K.Key_A, "a")
    assert app.keys.held
    qapp.sendEvent(host, QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    assert not app.keys.held
    x = app.game.paddle_x
    pump(qapp, 0.3)
    assert app.game.paddle_x == x


def test_breakout_pointer_drag_moves_the_paddle_and_the_stuck_ball(qapp):
    host = _host(qapp, "breakout")
    app = host.control
    ox, oy, scale = app.board
    y = oy + 500 * scale
    drag(qapp, host, (ox + 400 * scale, y), (ox + 650 * scale, y))
    assert app.game.paddle_x == pytest.approx(650, abs=25)
    assert app.game.ball_x == pytest.approx(app.game.paddle_x)


def test_breakout_in_the_hub_takes_keys_and_pointer(qapp):
    host = _host(qapp, "")
    hub = host.control
    child = hub.select("Breakout")
    assert child is not None and hub.error == ""
    pump(qapp, 0.2)
    x0 = child.game.paddle_x
    press(qapp, host, K.Key_Right)
    pump(qapp, 0.4)
    release(qapp, host, K.Key_Right)
    assert child.game.paddle_x > x0 + 20 and not child.keys.held
    tap(qapp, host, K.Key_Space, " ")
    assert not child.game.stuck


# --------------------------------------------------------------------------- Pong


def test_pong_paddle_moves_with_up_down_and_stops_on_release(qapp):
    host = _host(qapp, "pong")
    app = host.control
    y0 = app.game.paddle_y
    press(qapp, host, K.Key_Up)
    pump(qapp, 0.4)
    y1 = app.game.paddle_y
    release(qapp, host, K.Key_Up)
    assert y1 < y0 - 10
    pump(qapp, 0.15)
    y2 = app.game.paddle_y
    pump(qapp, 0.2)
    assert app.game.paddle_y == y2
    press(qapp, host, K.Key_Down)
    pump(qapp, 0.3)
    release(qapp, host, K.Key_Down)
    assert app.game.paddle_y > y2 + 10


def test_pong_second_player_keys_w_s_and_pause_and_focus_loss(qapp):
    host = _host(qapp, "pong")
    app = host.control
    press(qapp, host, K.Key_W, "w")
    assert "up" in app.p2.held
    qapp.sendEvent(host, QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    assert not app.p2.held and not app.keys.held
    tap(qapp, host, K.Key_P, "p")
    assert app.game.paused
    tap(qapp, host, K.Key_P, "p")
    assert not app.game.paused


def test_pong_pointer_drag_moves_the_player_paddle(qapp):
    host = _host(qapp, "pong")
    app = host.control
    ox, oy, scale = app.board
    x = ox + 40 * scale
    y0 = app.game.paddle_y
    drag(qapp, host, (x, oy + y0 * scale), (x, oy + 100 * scale))
    assert app.game.paddle_y == pytest.approx(100, abs=20)


# --------------------------------------------------------------------------- Tetris


def test_tetris_left_right_move_one_cell_per_press_and_up_rotates(qapp):
    import random

    random.seed(7)               # the first piece is random: pin it, or the O piece (no visible rotation) flakes this
    host = _host(qapp, "tetris")
    app = host.control
    game = app.game
    x0, coords = game.x, list(game.coords)
    tap(qapp, host, K.Key_Left, hold=0.02)
    assert game.x == x0 - 1
    tap(qapp, host, K.Key_Right, hold=0.02)
    tap(qapp, host, K.Key_Right, hold=0.02)
    assert game.x == x0 + 1
    assert not app.keys.held
    tap(qapp, host, K.Key_Up, hold=0.02)
    assert game.coords != coords or game.shape == 1   # the square piece rotates onto itself


def test_tetris_held_left_repeats_and_focus_loss_stops_it(qapp):
    host = _host(qapp, "tetris")
    app = host.control
    x0 = app.game.x
    press(qapp, host, K.Key_Left)
    pump(qapp, 0.7)
    assert app.game.x <= x0 - 2
    qapp.sendEvent(host, QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    assert not app.keys.held
    x = app.game.x
    pump(qapp, 0.3)
    assert app.game.x == x


def test_tetris_space_drops_the_piece_pause_and_reset(qapp):
    host = _host(qapp, "tetris")
    app = host.control
    game = app.game
    tap(qapp, host, K.Key_Space, " ", hold=0.02)
    assert any(cell is not None for row in game.well for cell in row), "the dropped piece never landed"
    tap(qapp, host, K.Key_P, "p")
    assert game.paused
    tap(qapp, host, K.Key_P, "p")
    assert not game.paused
    tap(qapp, host, K.Key_R, "r")
    assert all(cell is None for row in game.well for cell in row)


# --------------------------------------------------------------------------- Minesweeper


def _spy_buttons(monkeypatch):
    """Record every invisible_button's screen rectangle while the host paints."""
    from emtk import im

    rects, state = {}, {"pos": (0, 0)}
    set_pos, button = im.set_cursor_screen_pos, im.invisible_button

    def pos(p, *args, **kwargs):
        state["pos"] = tuple(p)
        return set_pos(p, *args, **kwargs)

    def inv(label, size, *args, **kwargs):
        rects[label] = (*state["pos"], *size)
        return button(label, size, *args, **kwargs)

    monkeypatch.setattr(im, "set_cursor_screen_pos", pos)
    monkeypatch.setattr(im, "invisible_button", inv)
    return rects


def _centre(rect):
    return rect[0] + rect[2] / 2, rect[1] + rect[3] / 2


def test_minesweeper_arrows_enter_flag_and_difficulty_keys(qapp):
    host = _host(qapp, "minesweeper")
    app = host.control
    app.cursor_row, app.cursor_col = 0, 0
    tap(qapp, host, K.Key_Right, hold=0.02)
    tap(qapp, host, K.Key_Down, hold=0.02)
    assert (app.cursor_row, app.cursor_col) == (1, 1)
    tap(qapp, host, K.Key_F, "f", hold=0.02)
    assert app.game.board[1][1].flagged
    tap(qapp, host, K.Key_Return, hold=0.02)
    assert any(c.revealed for row in app.game.board for c in row) or app.game.board[1][1].flagged
    held = len(app.held)
    press(qapp, host, K.Key_Right)
    pump(qapp, 0.5)
    c = app.cursor_col
    assert c >= 3, "a held arrow did not repeat"
    qapp.sendEvent(host, QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    assert not app.held and held == 0
    pump(qapp, 0.2)
    assert app.cursor_col == c
    size = (app.game.rows, app.game.columns)
    tap(qapp, host, K.Key_E, "e", hold=0.02)
    assert (app.game.rows, app.game.columns) != size


def test_minesweeper_left_click_scans_and_right_click_flags(qapp, monkeypatch):
    rects = _spy_buttons(monkeypatch)
    host = _host(qapp, "minesweeper")
    app = host.control
    pump(qapp, 0.15)
    x, y = _centre(rects["##cell-3-3"])
    click(qapp, host, x, y, K.RightButton)
    assert app.game.board[3][3].flagged
    x, y = _centre(rects["##cell-5-6"])
    click(qapp, host, x, y)
    assert (app.cursor_row, app.cursor_col) == (5, 6)
    assert any(c.revealed for row in app.game.board for c in row)


# --------------------------------------------------------------------------- Number Quest


def test_number_quest_keys_dial_submit_and_new_round(qapp):
    host = _host(qapp, "number_quest")
    app = host.control
    start = app.estimate
    tap(qapp, host, K.Key_Right, hold=0.02)
    tap(qapp, host, K.Key_Right, hold=0.02)
    assert app.estimate == start + 2
    tap(qapp, host, K.Key_E, "e", hold=0.02)
    assert app.estimate == start + 12
    tap(qapp, host, K.Key_Q, "q", hold=0.02)
    assert app.estimate == start + 2
    press(qapp, host, K.Key_Left)
    pump(qapp, 0.6)
    assert app.estimate < start, "a held Left did not repeat"
    qapp.sendEvent(host, QtGui.QFocusEvent(QtCore.QEvent.FocusOut))
    e = app.estimate
    pump(qapp, 0.3)
    assert app.estimate == e
    tap(qapp, host, K.Key_Return, hold=0.02)
    assert app.history == [e]
    tap(qapp, host, K.Key_R, "r", hold=0.02)
    assert app.history == [] and app.estimate == 50


def test_number_quest_click_the_plot_dials_and_the_caption_submits(qapp, monkeypatch):
    rects = _spy_buttons(monkeypatch)
    host = _host(qapp, "number_quest")
    app = host.control
    pump(qapp, 0.15)
    dx, dy, dw, dh = rects["##dial"]
    click(qapp, host, dx + dw * 0.9, dy + dh / 2)
    assert app.estimate > 80
    click(qapp, host, dx + dw * 0.1, dy + dh / 2)
    assert app.estimate < 20
    left = next(v for k, v in rects.items() if k == "##306" or k == "##324")
    row = rects["##324"]
    click(qapp, host, row[0] + row[2] * 0.2, row[1] + row[3] / 2)
    assert len(app.history) == 1                       # left half submits
    click(qapp, host, row[0] + row[2] * 0.8, row[1] + row[3] / 2)
    assert app.history == []                           # right half starts a new round
    assert left


# --------------------------------------------------------------------------- hub


def test_every_game_in_the_hub_receives_a_real_key(qapp):
    host = _host(qapp, "")
    hub = host.control
    seen = {}
    for name in ("Number Quest", "Minesweeper", "Tetris", "Pong", "Breakout"):
        child = hub.select(name)
        assert child is not None, name
        got = []
        original = child.key
        child.key = lambda key, text="", modifiers=0, g=got, o=original: (g.append(key), o(key, text, modifiers))[1]
        pump(qapp, 0.1)
        tap(qapp, host, K.Key_Left, hold=0.02)
        seen[name] = got
    assert all(got == [int(K.Key_Left)] for got in seen.values()), seen
