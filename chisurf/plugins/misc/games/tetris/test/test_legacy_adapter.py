"""The retained Qt host translates its enum inputs into the shared rules."""

from types import SimpleNamespace

from chisurf.gui.chigame.input import Action, InputMap

from ..model import SHAPES
from ..tetris import TetrisGame


def test_qt_actions_use_the_same_move_pause_restart_rules():
    game = TetrisGame()
    keys = InputMap()
    host = SimpleNamespace(
        keys=keys,
        camera=SimpleNamespace(center=[0, 0], height=0),
        audio=SimpleNamespace(sfx=lambda *args: None),
    )
    game.setup(host)
    game.shape, game.coords = 3, list(SHAPES[3])
    before = game.x
    keys.tap(Action.LEFT)
    game.update(0, keys)
    assert game.x == before - 1
    keys.end_frame()
    keys.tap(Action.MENU)
    game.update(0, keys)
    assert game.paused
    keys.end_frame()
    keys.tap(Action.CANCEL)
    game.update(0, keys)
    assert not game.paused and game.score == 0
