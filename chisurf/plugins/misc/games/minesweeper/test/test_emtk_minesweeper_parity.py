"""The native Minesweeper at parity with the Qt chigame view.

The Qt view (``gui/tool.py``: ``MinesweeperChiGame``) is driven in a subprocess with a
stub host on the same fixed board and the same presses; its messages, cursor and
board state are compared with the emtk app's, and its bindings with the emtk keys.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from emtk.keys import KEY_DOWN, KEY_ENTER, KEY_LEFT, KEY_RIGHT, KEY_UP
from emtk.testing import RecordingPainter

from chisurf.plugins.misc.games.minesweeper.gui.app import make_app
from chisurf.plugins.misc.games.minesweeper.test.capture_native import MINES

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
#: (action, row, col) presses: scan, flag, scan a mine, then input after the loss.
SCRIPT = [("confirm", 8, 5), ("menu", 0, 1), ("confirm", 2, 4), ("confirm", 7, 0), ("menu", 6, 6)]

_QT = r"""
import json, sys
from types import SimpleNamespace
from chisurf.gui.chigame.input import Action
from chisurf.plugins.misc.games.minesweeper.gui.tool import BINDINGS, MinesweeperChiGame
mines = {tuple(m) for m in json.loads(sys.argv[1])}
script = json.loads(sys.argv[2])
class Keys:
    def __init__(self): self.bindings = {}; self.pressed = set()
    def just_pressed(self, a): return a in self.pressed
    def is_held(self, a): return False
game = MinesweeperChiGame()
keys = Keys()
host = SimpleNamespace(keys=keys, camera=SimpleNamespace(center=[0.0, 0.0], height=0.0),
                       audio=SimpleNamespace(sfx=lambda *a, **k: None))
game.setup(host)
game.game._fixed_mine_positions = mines
game.game.reset()
trail = []
for action, row, col in script:
    game.cursor_row, game.cursor_col = row, col
    keys.pressed = {Action.CONFIRM if action == "confirm" else Action.MENU}
    game.update(1 / 60, keys)
    keys.pressed = set()
    g = game.game
    trail.append([game.message, g.status.value, sum(c.revealed for r in g.board for c in r),
                  sum(c.flagged for r in g.board for c in r)])
print("FACTS" + json.dumps({"trail": trail, "bindings": {k: v.name for k, v in BINDINGS.items()}}))
"""


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT, json.dumps(sorted(MINES)), json.dumps(SCRIPT)],
                          capture_output=True, text=True, timeout=300, env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and ("No module named" in proc.stderr or "could not connect to display" in proc.stderr):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt view's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS"):])


def _board_counts(game):
    return (sum(c.revealed for r in game.board for c in r), sum(c.flagged for r in game.board for c in r))


# 1. the same presses on the same board give the same game
def test_a_scripted_game_matches_the_qt_view(qt):
    app = make_app()
    app.game._fixed_mine_positions = MINES
    app.game.reset()
    trail = []
    for action, row, col in SCRIPT:
        app.cursor_row, app.cursor_col = row, col
        (app.reveal if action == "confirm" else app.flag)()
        trail.append([app.message, app.game.status.value, *_board_counts(app.game)])
    assert trail == qt["trail"]


# 2. the same keys
def test_bindings_match_the_qt_view(qt):
    keycode = {"ArrowUp": KEY_UP, "ArrowDown": KEY_DOWN, "ArrowLeft": KEY_LEFT, "ArrowRight": KEY_RIGHT,
               "Enter": KEY_ENTER}
    effect = {"UP": ("move", (-1, 0)), "DOWN": ("move", (1, 0)), "LEFT": ("move", (0, -1)),
              "RIGHT": ("move", (0, 1)), "CONFIRM": ("reveal",), "MENU": ("flag",), "CANCEL": ("restart",),
              "SHOULDER_L": ("change_difficulty", -1), "SHOULDER_R": ("change_difficulty", 1)}
    for key, action in qt["bindings"].items():
        app = make_app()
        seen = []
        app.move = lambda dr, dc: seen.append(("move", (dr, dc)))
        app.reveal = lambda: seen.append(("reveal",))
        app.flag = lambda: seen.append(("flag",))
        app.restart = lambda: seen.append(("restart",))
        app.change_difficulty = lambda step: seen.append(("change_difficulty", step))
        code = keycode.get(key, ord(key) if len(key) == 1 else 0)
        assert app.key(code, key if len(key) == 1 else ""), key
        assert seen == [effect[action]], key


def test_sound_is_greyed_without_an_audio_output_and_works_with_one():
    app = make_app()
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 560, 620)
    calls = []
    app = make_app(audio_callback=lambda name, value: calls.append((name, value)))
    app.sound_enabled = True
    app.game._fixed_mine_positions = MINES
    app.game.reset()
    app.cursor_row, app.cursor_col = 8, 5
    app.reveal()
    assert ("reveal", 620.0) in calls


@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (560, 620)])
def test_draws(size):
    app = make_app()
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    assert "Sound" in painter.strings


def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("minesweeper")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("minesweeper"))["controls_without_tooltip"] == []


def test_a_held_direction_repeats_like_the_qt_view():
    """One step on the press, then one per 0.07 s after a 0.30 s delay; host repeats ignored."""
    app = make_app()
    app.cursor_row, app.cursor_col = 0, 0
    app.key(KEY_RIGHT)
    assert app.cursor_col == 1
    app.key(KEY_RIGHT)                       # an auto-repeated press from the host
    assert app.cursor_col == 1
    def frames(seconds):                     # 10 ms frames (advance clamps one frame to 0.1 s)
        for _ in range(round(seconds / 0.01)):
            app.advance(0.01)

    frames(0.29)
    assert app.cursor_col == 1               # still in the initial delay
    frames(0.16)
    assert app.cursor_col == 3
    app.key_release(KEY_RIGHT)
    frames(0.5)
    assert app.cursor_col == 3 and not app.held
