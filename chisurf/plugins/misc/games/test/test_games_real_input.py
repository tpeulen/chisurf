"""Every game takes REAL input through the native host, with a real clock.

Key and pointer events are delivered to the game's emtk surface exactly as the native window
delivers them (:class:`emtk.testing.Driver`'s ``ControlSurface``), frames are drawn against the
real wall clock, and each test asserts that the paddle / piece / cursor / dial actually moved:
press and release, held keys, ``focus_lost``, pointer press / drag / release. How the Qt host turns
``QKeyEvent`` / ``QMouseEvent`` / focus changes into these same calls is emtk's own
``tests/test_qt_host.py``. Breakout is covered here because its registry entry was ``emtk: None``
(an audit measured its draw as "not finishing").
"""

from __future__ import annotations

import importlib
import pathlib
import time
from types import SimpleNamespace

import pytest
from emtk.events import LEFT_BUTTON, NO_BUTTON, RIGHT_BUTTON
from emtk.keys import KEY_DOWN, KEY_LEFT, KEY_RETURN, KEY_RIGHT, KEY_SPACE, KEY_UP
from emtk.testing import Driver

GAMES = pathlib.Path(__file__).resolve().parents[1]
#: The keys the tests press, by the names the host reports them under (letters are upper-case codes).
K = SimpleNamespace(
    Key_Left=KEY_LEFT,
    Key_Right=KEY_RIGHT,
    Key_Up=KEY_UP,
    Key_Down=KEY_DOWN,
    Key_Return=KEY_RETURN,
    Key_Space=KEY_SPACE,
    **{f"Key_{c}": ord(c) for c in "DEFMPQRW"},
    LeftButton=LEFT_BUTTON,
    RightButton=RIGHT_BUTTON,
    NoButton=NO_BUTTON,
)


@pytest.fixture(autouse=True)
def _hermetic_settings(tmp_path, monkeypatch):
    """The games never touch the real ~/.chisurf: HOME and the chisurf/MMFDB folders are temporary."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "cs"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mm"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mm.db"))


class _Host:
    """A game opened as the menu opens it (``entrypoints.emtk``), on the native host's surface."""

    def __init__(self, game, size):
        manifest = load_manifest(GAMES / game / "manifest.json")
        module, factory = manifest.entrypoints.emtk.split(":")
        self.control = getattr(importlib.import_module(module), factory)()
        self.drv = Driver(self.control, size=size)
        self.surface = self.drv.surface


def load_manifest(path):
    from chisurf.core.plugin import load_manifest as load

    return load(path)


def _host(game, size=(900, 700)):
    host = _Host(game, size)
    pump(host, 0.15)
    return host


def pump(host, seconds):
    """Draw frames against the real wall clock for *seconds*, as the window's loop does."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        host.drv.frame()
        time.sleep(0.01)


def press(host, key, text=""):
    host.surface.on_key_press(key, text, 0)


def release(host, key, text=""):
    host.surface.on_key_release(key, text, 0)


def focus_out(host):
    """The window lost focus: the host tells the control (``focus_lost``)."""
    host.control.focus_lost()


def tap(host, key, text="", hold=0.05):
    press(host, key, text)
    pump(host, hold)
    release(host, key, text)
    pump(host, 0.03)


def click(host, x, y, button=K.LeftButton):
    host.surface.on_pointer_move(x, y, K.NoButton, 0)
    pump(host, 0.05)
    host.surface.on_pointer_press(x, y, button, 0)
    pump(host, 0.05)
    host.surface.on_pointer_release(x, y, button, 0)
    pump(host, 0.05)


def drag(host, start, end, steps=6):
    host.surface.on_pointer_move(*start, K.NoButton, 0)
    pump(host, 0.05)
    host.surface.on_pointer_press(*start, K.LeftButton, 0)
    pump(host, 0.05)
    for i in range(1, steps + 1):
        x = start[0] + (end[0] - start[0]) * i / steps
        y = start[1] + (end[1] - start[1]) * i / steps
        host.surface.on_pointer_move(x, y, K.LeftButton, 0)
        pump(host, 0.03)
    host.surface.on_pointer_release(*end, K.LeftButton, 0)
    pump(host, 0.05)


# --------------------------------------------------------------------------- Breakout


def test_breakout_is_enabled_in_its_manifest():
    import json
    from pathlib import Path

    manifest = json.loads((Path(__file__).parents[1] / "breakout" / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.misc.games.breakout.app:make_app"
    assert not manifest.get("menu_hidden")


def test_breakout_frame_terminates_and_stays_cheap_in_the_live_loop():
    """The audit saw 'draw does not finish within 120 s'; the live loop must keep painting."""
    host = _host("breakout")
    start = time.monotonic()
    frames = []
    original = host.control.draw
    host.control.draw = lambda *a, **k: (frames.append(1), original(*a, **k))[1]
    press(host, K.Key_Right)
    pump(host, 0.6)
    release(host, K.Key_Right)
    assert frames, "no frame was drawn while a key was held"
    assert time.monotonic() - start < 5


def test_breakout_paddle_follows_held_keys_and_stops_on_release():
    host = _host("breakout")
    app = host.control
    x0 = app.game.paddle_x
    press(host, K.Key_Right)
    pump(host, 0.4)
    assert "right" in app.keys.held.values()
    moved = app.game.paddle_x
    assert moved > x0 + 20
    release(host, K.Key_Right)
    assert not app.keys.held
    pump(host, 0.2)
    after = app.game.paddle_x
    pump(host, 0.2)
    assert app.game.paddle_x == after, "the paddle kept moving after the key went up"
    press(host, K.Key_Left)
    pump(host, 0.3)
    release(host, K.Key_Left)
    assert app.game.paddle_x < after - 10


def test_breakout_letter_keys_are_not_directions_and_releases_are_independent():
    """WASD no longer steers (owner rule: direction keys only); a key-up on one
    of two held directions must not drop the other."""
    host = _host("breakout")
    app = host.control
    x0 = app.game.paddle_x
    press(host, K.Key_D, "d")
    pump(host, 0.3)
    assert app.game.paddle_x == x0, "D must not steer the paddle (arrows only)"
    assert not app.keys.held
    press(host, K.Key_Left)  # both held
    press(host, K.Key_Right)
    release(host, K.Key_Right)  # Right up, Left still down
    assert "left" in app.keys.held.values()
    release(host, K.Key_Left)
    assert not app.keys.held


def test_breakout_space_launches_the_ball_and_the_ball_moves():
    host = _host("breakout")
    game = host.control.game
    assert game.stuck
    tap(host, K.Key_Space, " ")
    assert not game.stuck and game.ball_vy < 0
    y0 = game.ball_y
    pump(host, 0.3)
    assert game.ball_y != y0


def test_breakout_pause_reset_and_mute_keys():
    host = _host("breakout")
    app = host.control
    tap(host, K.Key_Space, " ")
    tap(host, K.Key_P, "p")
    assert app.game.paused
    y = app.game.ball_y
    pump(host, 0.3)
    assert app.game.ball_y == y, "the ball moved while paused"
    tap(host, K.Key_P, "p")
    assert not app.game.paused
    muted = app.game.muted
    tap(host, K.Key_M, "m")
    assert app.game.muted != muted
    tap(host, K.Key_R, "r")
    assert app.game.stuck and app.game.score == 0


def test_breakout_focus_loss_releases_every_held_key():
    host = _host("breakout")
    app = host.control
    press(host, K.Key_Right)
    press(host, K.Key_Left)
    assert app.keys.held
    focus_out(host)
    assert not app.keys.held
    x = app.game.paddle_x
    pump(host, 0.3)
    assert app.game.paddle_x == x


def test_breakout_pointer_drag_moves_the_paddle_and_the_stuck_ball():
    host = _host("breakout")
    app = host.control
    ox, oy, scale = app.board
    y = oy + 500 * scale
    drag(host, (ox + 400 * scale, y), (ox + 650 * scale, y))
    assert app.game.paddle_x == pytest.approx(650, abs=25)
    assert app.game.ball_x == pytest.approx(app.game.paddle_x)


# --------------------------------------------------------------------------- Pong


def test_pong_paddle_moves_with_up_down_and_stops_on_release():
    host = _host("pong")
    app = host.control
    y0 = app.game.paddle_y
    press(host, K.Key_Up)
    pump(host, 0.4)
    y1 = app.game.paddle_y
    release(host, K.Key_Up)
    assert y1 < y0 - 10
    pump(host, 0.15)
    y2 = app.game.paddle_y
    pump(host, 0.2)
    assert app.game.paddle_y == y2
    press(host, K.Key_Down)
    pump(host, 0.3)
    release(host, K.Key_Down)
    assert app.game.paddle_y > y2 + 10


def test_pong_second_player_keys_w_s_and_pause_and_focus_loss():
    host = _host("pong")
    app = host.control
    press(host, K.Key_W, "w")
    assert "up" in app.p2.held
    focus_out(host)
    assert not app.p2.held and not app.keys.held
    tap(host, K.Key_P, "p")
    assert app.game.paused
    tap(host, K.Key_P, "p")
    assert not app.game.paused


def test_pong_pointer_drag_moves_the_player_paddle():
    host = _host("pong")
    app = host.control
    ox, oy, scale = app.board
    x = ox + 40 * scale
    y0 = app.game.paddle_y
    drag(host, (x, oy + y0 * scale), (x, oy + 100 * scale))
    assert app.game.paddle_y == pytest.approx(100, abs=20)


# --------------------------------------------------------------------------- Tetris


def test_tetris_left_right_move_one_cell_per_press_and_up_rotates():
    import random

    random.seed(
        7
    )  # the first piece is random: pin it, or the O piece (no visible rotation) flakes this
    host = _host("tetris")
    app = host.control
    game = app.game
    x0, coords = game.x, list(game.coords)
    tap(host, K.Key_Left, hold=0.02)
    assert game.x == x0 - 1
    tap(host, K.Key_Right, hold=0.02)
    tap(host, K.Key_Right, hold=0.02)
    assert game.x == x0 + 1
    assert not app.keys.held
    tap(host, K.Key_Up, hold=0.02)
    assert game.coords != coords or game.shape == 1  # the square piece rotates onto itself


def test_tetris_held_left_repeats_and_focus_loss_stops_it():
    host = _host("tetris")
    app = host.control
    x0 = app.game.x
    press(host, K.Key_Left)
    pump(host, 0.7)
    assert app.game.x <= x0 - 2
    focus_out(host)
    assert not app.keys.held
    x = app.game.x
    pump(host, 0.3)
    assert app.game.x == x


def test_tetris_space_drops_the_piece_pause_and_reset():
    host = _host("tetris")
    app = host.control
    game = app.game
    tap(host, K.Key_Space, " ", hold=0.02)
    assert any(cell is not None for row in game.well for cell in row), (
        "the dropped piece never landed"
    )
    tap(host, K.Key_P, "p")
    assert game.paused
    tap(host, K.Key_P, "p")
    assert not game.paused
    tap(host, K.Key_R, "r")
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


def test_minesweeper_arrows_enter_flag_and_difficulty_keys():
    host = _host("minesweeper")
    app = host.control
    app.cursor_row, app.cursor_col = 0, 0
    tap(host, K.Key_Right, hold=0.02)
    tap(host, K.Key_Down, hold=0.02)
    assert (app.cursor_row, app.cursor_col) == (1, 1)
    tap(host, K.Key_F, "f", hold=0.02)
    assert app.game.board[1][1].flagged
    tap(host, K.Key_Return, hold=0.02)
    assert any(c.revealed for row in app.game.board for c in row) or app.game.board[1][1].flagged
    held = len(app.held)
    press(host, K.Key_Right)
    pump(host, 0.5)
    c = app.cursor_col
    assert c >= 3, "a held arrow did not repeat"
    focus_out(host)
    assert not app.held and held == 0
    pump(host, 0.2)
    assert app.cursor_col == c
    size = (app.game.rows, app.game.columns)
    tap(host, K.Key_E, "e", hold=0.02)
    assert (app.game.rows, app.game.columns) != size


def test_minesweeper_left_click_scans_and_right_click_flags(monkeypatch):
    rects = _spy_buttons(monkeypatch)
    host = _host("minesweeper")
    app = host.control
    pump(host, 0.15)
    x, y = _centre(rects["##cell-3-3"])
    click(host, x, y, K.RightButton)
    assert app.game.board[3][3].flagged
    x, y = _centre(rects["##cell-5-6"])
    click(host, x, y)
    assert (app.cursor_row, app.cursor_col) == (5, 6)
    assert any(c.revealed for row in app.game.board for c in row)


# --------------------------------------------------------------------------- Number Quest


def test_number_quest_keys_dial_submit_and_new_round():
    host = _host("number_quest")
    app = host.control
    start = app.estimate
    tap(host, K.Key_Right, hold=0.02)
    tap(host, K.Key_Right, hold=0.02)
    assert app.estimate == start + 2
    tap(host, K.Key_E, "e", hold=0.02)
    assert app.estimate == start + 12
    tap(host, K.Key_Q, "q", hold=0.02)
    assert app.estimate == start + 2
    press(host, K.Key_Left)
    pump(host, 0.6)
    assert app.estimate < start, "a held Left did not repeat"
    focus_out(host)
    e = app.estimate
    pump(host, 0.3)
    assert app.estimate == e
    tap(host, K.Key_Return, hold=0.02)
    assert app.history == [e]
    tap(host, K.Key_R, "r", hold=0.02)
    assert app.history == [] and app.estimate == 50


def test_number_quest_click_the_plot_dials_and_the_caption_submits(monkeypatch):
    rects = _spy_buttons(monkeypatch)
    host = _host("number_quest")
    app = host.control
    pump(host, 0.15)
    dx, dy, dw, dh = rects["##dial"]
    click(host, dx + dw * 0.9, dy + dh / 2)
    assert app.estimate > 80
    click(host, dx + dw * 0.1, dy + dh / 2)
    assert app.estimate < 20
    left = next(v for k, v in rects.items() if k == "##306" or k == "##324")
    row = rects["##324"]
    click(host, row[0] + row[2] * 0.2, row[1] + row[3] / 2)
    assert len(app.history) == 1  # left half submits
    click(host, row[0] + row[2] * 0.8, row[1] + row[3] / 2)
    assert app.history == []  # right half starts a new round
    assert left


# --------------------------------------------------------------------------- every game


@pytest.mark.parametrize("game", ["number_quest", "minesweeper", "tetris", "pong", "breakout"])
def test_every_game_opened_from_its_manifest_receives_a_real_key(game):
    host = _host(game)
    app = host.control
    got = []
    original = app.key
    app.key = lambda key, text="", modifiers=0: (got.append(key), original(key, text, modifiers))[1]
    pump(host, 0.1)
    tap(host, K.Key_Left, hold=0.02)
    assert got == [K.Key_Left]
