"""The native Tetris at parity with the Qt chigame view.

Both drive :class:`..model.TetrisModel` (the Qt ``TetrisGame`` subclasses it; the
committed Qt rules equal it apart from action names and the draw helpers that
moved to the view, ``okf/plugins/emtk-ports/tetris/rules_diff_vs_head.txt``).
Compared here: the Qt bindings (subprocess) against the emtk keys, scripted keys,
the Sound switch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from emtk.keys import KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP
from emtk.testing import RecordingPainter

from chisurf.plugins.misc.games.tetris.app import TetrisApp, make_app
from chisurf.plugins.misc.games.tetris.model import TetrisModel

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())

_QT = r"""
import json
from chisurf.plugins.misc.games.tetris.tetris import BINDINGS, TetrisGame
from chisurf.plugins.misc.games.tetris.model import TetrisModel
print("FACTS" + json.dumps({"bindings": {k: v.name for k, v in BINDINGS.items()},
                            "shares_model": issubclass(TetrisGame, TetrisModel)}))
"""

ACTION = {
    "LEFT": "left",
    "RIGHT": "right",
    "DOWN": "down",
    "CONFIRM": "confirm",
    "MENU": "menu",
    "CANCEL": "cancel",
    "SHOULDER_R": "shoulder_r",
}
KEYCODE = {
    "ArrowLeft": (KEY_LEFT, ""),
    "ArrowRight": (KEY_RIGHT, ""),
    "ArrowDown": (KEY_DOWN, ""),
    "ArrowUp": (KEY_UP, ""),
}


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
        cwd=str(REPO),
    )
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None and (
        "No module named" in proc.stderr or "could not connect to display" in proc.stderr
    ):
        pytest.skip(f"no Qt here: {proc.stderr[-400:]}")
    # Any other failure is the Qt game's own: skipping it hid a broken Qt host.
    assert line is not None, f"the Qt run failed: {proc.stderr[-1200:]}"
    return json.loads(line[len("FACTS") :])


def test_the_qt_game_runs_the_same_model(qt):
    assert qt["shares_model"] is True
    assert isinstance(TetrisApp().game, TetrisModel)


def test_bindings_match_the_qt_game(qt):
    for key, action in qt["bindings"].items():
        code, text = KEYCODE[key] if key in KEYCODE else (ord(key), key)
        assert TetrisApp.binding(code, text) == ACTION[action], key


def test_keys_drive_the_game_like_the_qt_controller():
    app = make_app()
    game = app.game
    app.key(ord("p"), "p")
    assert game.paused is True
    app.key_release(ord("p"), "p")
    app.key(ord("p"), "p")
    assert game.paused is False
    app.key_release(ord("p"), "p")
    app.key(ord(" "), " ")  # hard drop: the piece is written into the well
    app.advance(1 / 60)
    assert sum(cell is not None for row in game.well for cell in row) == 4


def test_sound_is_greyed_without_an_audio_output_and_works_with_one():
    app = make_app()
    app.set_sound()
    assert app.sound_enabled is False
    calls = []
    audio = SimpleNamespace(
        sfx=lambda *a: calls.append(("sfx", a)),
        set_enabled=lambda on: calls.append(("on", on)),
        close=lambda: calls.append(("close",)),
    )
    app = make_app(audio=audio)
    app.set_sound()
    assert app.sound_enabled is True and ("on", True) in calls
    app.game._sfx("drop", 330.0)
    assert any(c[0] == "sfx" for c in calls)
    app.close()
    assert ("close",) in calls


@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (480, 600)])
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

    result = qt_free("tetris")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("tetris"))["controls_without_tooltip"] == []
