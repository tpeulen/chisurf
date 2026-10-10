"""Behavior, lifecycle, localization and Qt-blocked native factory checks."""

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from emtk import i18n
from emtk.app import as_surface
from emtk.keys import KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP
from emtk.testing import RecordingPainter

from ..app import TetrisApp, make_app
from ..model import BOARD_H, SHAPES
from ..translations import LOCALES, STRINGS, install_translations


def test_factory_in_clean_process_blocks_qt():
    script = """import sys
from importlib.abc import MetaPathFinder
class BlockQt(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise AssertionError('Qt import: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from chisurf.plugins.misc.games.tetris.app import make_app
app = make_app()
assert app.game.score == 0
assert len(app.game.well) == 22
app.close()
assert not any(name.startswith(('qtpy', 'PyQt', 'PySide')) for name in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_native_manifest():
    manifest = json.loads((Path(__file__).parents[1] / "manifest.json").read_text())
    assert manifest["entrypoints"]["emtk"] == "chisurf.plugins.misc.games.tetris.app:make_app"


def test_physical_keys_repeat_and_release_independently():
    app = TetrisApp()
    app.game.shape, app.game.coords = 3, list(SHAPES[3])
    x = app.game.x
    assert app.key(KEY_LEFT)
    assert app.game.x == x - 1
    app.key(KEY_LEFT)  # OS auto-repeat must not add another immediate move.
    assert app.game.x == x - 1
    for _ in range(3):
        app.advance(0.1)
    assert app.game.x == x - 2
    assert not app.key(ord("A"), "a"), "WASD must not steer (owner rule: arrows only)"
    app.key_release(KEY_LEFT)
    app.focus_lost()
    before = app.game.x
    app.advance(0.1)
    assert app.game.x == before


def test_rotation_square_and_wall_collision():
    app = TetrisApp()
    app.game.shape, app.game.coords = 3, list(SHAPES[3])
    before = list(app.game.coords)
    app.key(KEY_UP)
    assert app.game.coords == before
    app.key_release(KEY_UP)
    app.game.shape, app.game.coords = 0, list(SHAPES[0])
    app.game.y = 5
    app.key(KEY_UP)  # arrows only rotate (owner rule; WASD removed)
    assert app.game.coords == [(-y, x) for x, y in SHAPES[0]]
    app.game.x = 1
    app.key(KEY_LEFT)
    assert app.game.x == 1  # horizontal I cannot cross the left boundary.


def test_down_is_soft_drop_and_space_is_hard_drop():
    app = TetrisApp()
    before = app.game.y
    app.key(KEY_DOWN)
    app.advance(0.08)
    assert app.game.y == before + 2
    assert not any(c is not None for row in app.game.well for c in row)
    app.key_release(KEY_DOWN)
    app.key(32, " ")
    cells = [
        (r, c) for r, row in enumerate(app.game.well) for c, v in enumerate(row) if v is not None
    ]
    assert len(cells) == 4 and max(r for r, c in cells) == BOARD_H - 1


def test_pause_restart_gameover_and_close():
    app = TetrisApp()
    app.game.score = 99
    app.key(ord("P"), "p")
    app.key(ord("P"), "p")
    assert app.game.paused
    before = app.game.y
    app.advance(0.1)
    assert app.game.y == before
    app.key(ord("R"), "r")
    assert app.game.score == 0 and not app.game.paused
    app.game.over = True
    app.key(KEY_UP)
    assert not app.game.over
    app.key(KEY_RIGHT)
    app.close()
    assert not app.keys.held and not app.animating()
    assert not app.key(KEY_LEFT)
    state = app.export_settings()
    app.advance(0.1)
    assert app.export_settings() == state


def test_saved_round_is_atomic_and_does_not_alias():
    app = TetrisApp()
    app.game.drop_down()
    app.game.score = 120
    app.game.paused = True
    state = app.export_settings()
    other = TetrisApp()
    other.restore_settings(state)
    assert other.export_settings() == state
    state["well"][-1][0] = 6
    assert other.export_settings() != state
    before = other.export_settings()
    for mutate in (
        lambda s: s["game"].update(level=99),
        lambda s: s["game"].update(x=-1),
        lambda s: s["well"][0].__setitem__(0, True),
        lambda s: s["coords"][0].__setitem__(0, 50),
        lambda s: s["game"].update(_fall_timer=float("nan")),
    ):
        malformed = copy.deepcopy(before)
        mutate(malformed)
        with pytest.raises(ValueError):
            other.restore_settings(malformed)
        assert other.export_settings() == before


def test_surface_routes_release():
    app = TetrisApp()
    surface = as_surface(app)
    assert surface.on_key_press(KEY_RIGHT, "", 0)
    assert surface.on_key_release(KEY_RIGHT, "", 0)
    before = app.game.x
    app.advance(0.1)
    assert app.game.x == before


def test_six_locales_and_viewport_bounds():
    install_translations()
    try:
        for locale in LOCALES:
            i18n.set_locale(locale)
            for source, translations in STRINGS.items():
                assert len(translations) == 5
                assert i18n.tr(source, context="Tetris") == (
                    source if locale == "en" else translations[LOCALES.index(locale) - 1]
                )
            app = make_app()
            app.clock = lambda: 0
            for size in ((520, 620), (360, 620)):
                painter = RecordingPainter()
                app.draw(painter, 0, 0, *size)
                x, y, scale = app.board
                assert x + 37 * scale >= 0 and y + 27 * scale >= 34
                assert x + 390 * scale <= size[0] and y + 553 * scale <= size[1]
                assert painter.calls
    finally:
        i18n.set_locale("en")
