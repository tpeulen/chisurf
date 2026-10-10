"""Native input, round restoration and import-boundary regression checks."""

import json
import os
import subprocess
import sys

import pytest
from emtk import i18n
from emtk.events import LEFT_BUTTON, RIGHT_BUTTON
from emtk.keys import KEY_LEFT, KEY_RETURN
from emtk.pil_painter import PilPainter

from ..core.game import GameStatus, MinesweeperGame
from ..gui.app import MinesweeperApp, make_app, tr
from ..gui.translations import LOCALES, STRINGS


def test_keyboard_cursor_flag_loss_restart_and_presets():
    app = MinesweeperApp(MinesweeperGame(5, 5, 1, {(2, 2)}))
    app.cursor_row = app.cursor_col = 0
    assert app.key(KEY_LEFT)
    assert (app.cursor_row, app.cursor_col) == (0, 0)
    assert app.key(ord("F"))
    assert app.game.board[0][0].flagged
    app.key(ord("F"))
    app.cursor_row = app.cursor_col = 2
    app.key(KEY_RETURN)
    assert app.game.status is GameStatus.LOST
    app.key(ord("F"))
    assert not app.game.board[2][2].flagged
    app.key(ord("R"))
    assert app.game.status is GameStatus.ACTIVE
    assert not any(c.revealed for row in app.game.board for c in row)
    app.key(ord("E"))
    assert (app.game.rows, app.game.columns, app.game.mines) == (16, 16, 40)
    app.key(ord("Q"))
    assert (app.game.rows, app.game.columns) == (9, 9)
    assert not app.key(ord("Z"))
    assert not app.key(ord("R"), "r", modifiers=0x04000000)


def test_real_mouse_delivery_reveals_and_right_click_flags():
    app = make_app()
    app.game._fixed_mine_positions = {
        (0, 0),
        (0, 3),
        (1, 7),
        (2, 4),
        (3, 2),
        (4, 8),
        (5, 5),
        (6, 1),
        (7, 7),
        (8, 3),
    }
    app.game.reset()

    def draw():
        app.draw(PilPainter(560, 620), 0, 0, 560, 620)

    draw()
    app.pointer_press(112, 148, RIGHT_BUTTON)
    draw()
    app.pointer_release(112, 148, RIGHT_BUTTON)
    draw()
    assert app.game.board[0][0].flagged
    app.pointer_press(448, 484, LEFT_BUTTON)
    draw()
    app.pointer_release(448, 484, LEFT_BUTTON)
    draw()
    assert app.game.board[8][8].revealed
    assert (app.cursor_row, app.cursor_col) == (8, 8)


@pytest.mark.parametrize("terminal", [False, True])
def test_full_round_state_survives_json_restore(terminal):
    app = MinesweeperApp(MinesweeperGame(5, 5, 2, {(0, 0), (4, 4)}))
    app.cursor_row, app.cursor_col = 0, 0
    app.flag()
    app.cursor_row, app.cursor_col = 2, 2
    app.reveal()
    if terminal:
        app.cursor_row = app.cursor_col = 4
        app.reveal()
    state = json.loads(json.dumps(app.export_settings()))
    restored = make_app()
    restored.restore_settings(state)
    assert restored.export_settings() == state
    original = restored.game
    with pytest.raises(ValueError):
        restored.restore_settings({**state, "cursor": [999, 0]})
    assert restored.game is original
    restored.restart()
    assert restored.game.status is GameStatus.ACTIVE


def test_safe_region_wins_and_restart_keeps_selected_size():
    app = MinesweeperApp(MinesweeperGame(5, 5, 1, {(0, 0)}))
    app.cursor_row, app.cursor_col = 4, 4
    app.reveal()
    assert app.game.status is GameStatus.WON
    app.restart()
    assert (app.game.rows, app.game.columns, app.game.mines) == (5, 5, 1)
    assert app.game.status is GameStatus.ACTIVE


def test_optional_host_audio_boundary_and_saved_preference():
    events = []
    app = MinesweeperApp(
        MinesweeperGame(5, 5, 1, {(0, 0)}),
        audio_callback=lambda event, value: events.append((event, value)),
    )
    app.cursor_row = app.cursor_col = 1
    app.flag()
    assert not events  # Sound is opt-in, as in the original Qt host.
    app.sound_enabled = True
    app.flag()
    app.reveal()
    assert events == [("flag", 480.0), ("reveal", 620.0)]
    restored = make_app()
    restored.restore_settings(app.export_settings())
    assert restored.sound_enabled
    assert restored.audio_callback is None


def test_invalid_preset_restore_is_atomic():
    app = make_app()
    original = app.game
    state = app.export_settings()
    with pytest.raises(ValueError):
        app.restore_settings({**state, "difficulty_index": "invalid"})
    assert app.game is original


def test_six_locale_catalogs_cover_every_display_string():
    app = make_app()
    old_locale = i18n.get_locale()
    try:
        for locale in LOCALES:
            i18n.set_locale(locale)
            assert app.window_title
            for source in STRINGS:
                assert tr(source)
                if locale != "en" and source not in {"Minesweeper", "Expert"}:
                    assert tr(source) != source
            app.draw(PilPainter(360, 620), 0, 0, 360, 620)
    finally:
        i18n.set_locale(old_locale)


def test_native_factory_and_render_block_all_qt_imports():
    script = """
import importlib.abc, sys
class NoQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise AssertionError('Qt import: ' + fullname)
sys.meta_path.insert(0, NoQt())
from chisurf.plugins.misc.games.minesweeper.gui.app import make_app
from emtk.pil_painter import PilPainter
app = make_app()
app.draw(PilPainter(360, 620), 0, 0, 360, 620)
assert not any(name.startswith(('qtpy', 'PyQt', 'PySide')) for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
    )
    assert result.returncode == 0, result.stderr
