"""Behavior and import-boundary checks for native Pong without a GPU."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from emtk.keys import KEY_DOWN, KEY_RETURN, KEY_UP
from emtk.testing import RecordingPainter

from ..app import PongApp, make_app
from ..model import ACCEPTOR_NM, DONOR_NM, FIELD_H, FIELD_W, PADDLE_H, WIN_SCORE
from ..translations import LOCALES, STRINGS, install_translations


def test_native_factory_does_not_import_qt_in_a_clean_process():
    script = """import sys
from importlib.abc import MetaPathFinder
class BlockQt(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise AssertionError('Qt import: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from chisurf.plugins.misc.games.pong.app import make_app
app = make_app()
assert app.game.player_score == 0
app.close()
assert not any(name.startswith(('qtpy', 'PyQt', 'PySide')) for name in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_held_keys_release_and_focus_loss_stop_motion():
    app = PongApp()
    app.key(KEY_DOWN)
    app.advance(0.1)
    assert app.game.paddle_y > 300
    app.key_release(KEY_DOWN)
    before = app.game.paddle_y
    app.advance(0.1)
    assert app.game.paddle_y == before
    app.key(KEY_UP)
    app.focus_lost()
    app.advance(0.1)
    assert app.game.paddle_y == before


def test_two_player_keys_are_independent_and_clamped():
    app = PongApp()
    app.key(ord("M"), "m")
    assert not app.game.vs_computer
    app.key(ord("W"), "w")
    app.key(KEY_DOWN)
    app.advance(0.1)
    assert app.game.cpu_y < 300 < app.game.paddle_y
    for _ in range(30):
        app.advance(0.1)
    assert app.game.cpu_y == PADDLE_H / 2
    assert app.game.paddle_y == FIELD_H - PADDLE_H / 2
    app.key_release(ord("W"), "w")
    assert not app.p2.held


def test_pause_repeat_guard_and_reset_preserve_legacy_behavior():
    app = PongApp()
    app.game.player_score = 4
    app.key(ord("P"), "p")
    app.key(ord("P"), "p")
    assert app.game.paused
    before = app.game.ball_x
    app.advance(0.1)
    assert app.game.ball_x == before
    app.key(ord("R"), "r")
    assert not app.game.paused
    assert app.game.player_score == 0 and app.game.serve_timer == 1


def test_bounce_and_win_stop_the_ball_and_confirm_restarts():
    app = PongApp()
    g = app.game
    g.serve_timer = 0
    g.ball_x, g.ball_y, g.ball_vx, g.ball_vy = 40, 300, -300, 0
    app.advance(0.1)
    assert g.ball_vx > 300 and g.rally == 1 and g.ball_nm == DONOR_NM
    g.player_score = WIN_SCORE - 1
    g.ball_x, g.ball_vx = FIELD_W + 40, 400
    app.advance(0.1)
    assert g.winner == "Donor"
    before = g.ball_x
    app.advance(0.1)
    assert g.ball_x == before and not app.animating()
    app.key(KEY_RETURN)
    assert g.winner is None and g.player_score == 0


def test_serve_and_wall_bounce():
    app = PongApp()
    for _ in range(11):
        app.advance(0.1)
    assert app.game.ball_vx != 0
    app.game.ball_y, app.game.ball_vy = 1, -300
    app.game._move_ball(0.001)
    assert app.game.ball_vy > 0


def test_mouse_drags_the_correct_paddle_without_leaving_the_board():
    app = PongApp()
    app.board = (10, 40, 1)
    app.pointer_move(30, 45, 1)
    assert app.game.paddle_y == PADDLE_H / 2
    app.game.vs_computer = False
    app.pointer_move(790, 630, 1)
    assert app.game.cpu_y == FIELD_H - PADDLE_H / 2
    before = app.game.cpu_y
    app.pointer_move(790, 700, 1)
    assert app.game.cpu_y == before


def test_saved_round_restores_atomically():
    app = PongApp()
    app.game.player_score, app.game.cpu_score = 3, 2
    app.game.ball_nm = ACCEPTOR_NM
    app.game.paused = True
    state = app.export_settings()
    other = PongApp()
    other.restore_settings(state)
    assert other.export_settings() == state
    malformed = copy.deepcopy(state)
    malformed["game"]["cpu_y"] = -20
    with pytest.raises(ValueError):
        other.restore_settings(malformed)
    assert other.export_settings() == state


def test_close_stops_animation_and_releases_audio():
    class Audio:
        enabled = True
        closed = False

        def set_enabled(self, enabled):
            self.enabled = enabled

        def close(self):
            self.closed = True

    audio = Audio()
    app = PongApp(audio)
    app.key(KEY_DOWN)
    app.close()
    assert audio.closed and not audio.enabled
    assert not app.keys.held and not app.animating()


def test_six_locale_catalogs_and_responsive_render():
    from emtk import i18n

    install_translations()
    for locale in LOCALES:
        i18n.set_locale(locale)
        for source, values in STRINGS.items():
            assert len(values) == 5
            assert i18n.tr(source, context="Pong") == (
                source if locale == "en" else values[LOCALES.index(locale) - 1]
            )
        app = make_app()
        app.clock = lambda: 0
        for size in ((820, 640), (480, 640)):
            app.draw(RecordingPainter(), 0, 0, *size)
            x, y, scale = app.board
            assert x >= 0 and y >= 40
            assert x + FIELD_W * scale <= size[0]
            assert y + FIELD_H * scale <= size[1]
    i18n.set_locale("en")


def test_manifest_native_factory():
    manifest = json.loads((Path(__file__).parents[1] / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.misc.games.pong.app:make_app"


def test_native_surface_routes_key_press_and_release():
    from emtk.app import as_surface

    app = PongApp()
    surface = as_surface(app)
    assert surface.on_key_press(KEY_DOWN, "", 0)
    app.advance(0.1)
    before = app.game.paddle_y
    assert surface.on_key_release(KEY_DOWN, "", 0)
    app.advance(0.1)
    assert app.game.paddle_y == before


def test_footer_pause_is_reachable_by_mouse():
    app = PongApp()
    app.clock = lambda: 0
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 820, 640)
    # The measured legacy footer puts Menu hold around x=330.
    app.pointer_press(330, 621, 1)
    app.draw(painter, 0, 0, 820, 640)
    app.pointer_release(330, 621, 1)
    app.draw(painter, 0, 0, 820, 640)
    assert app.game.paused
