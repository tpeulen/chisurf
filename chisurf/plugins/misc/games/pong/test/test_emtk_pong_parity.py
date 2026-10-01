"""The native Pong at parity with the Qt chigame view.

Both drive :class:`..model.PongModel` (the Qt ``PongGame`` subclasses it; the
committed Qt rules equal it method for method apart from action names and a host
guard, ``okf/plugins/emtk-ports/pong/rules_diff_vs_head.txt``). Compared here: the
Qt bindings (subprocess) against the emtk keys, a scripted rally, the Sound switch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from emtk.keys import KEY_DOWN, KEY_ENTER, KEY_UP
from emtk.testing import RecordingPainter

from chisurf.plugins.misc.games.pong.app import PongApp, make_app
from chisurf.plugins.misc.games.pong.model import PongModel

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())

_QT = r"""
import json
from chisurf.plugins.misc.games.pong.pong import P1_BINDINGS, P2_BINDINGS, PongGame
from chisurf.plugins.misc.games.pong.model import PongModel
print("FACTS" + json.dumps({"p1": {k: v.name for k, v in P1_BINDINGS.items()},
                            "p2": {k: v.name for k, v in P2_BINDINGS.items()},
                            "shares_model": issubclass(PongGame, PongModel)}))
"""

ACTION = {"UP": "up", "DOWN": "down", "CONFIRM": "confirm", "MENU": "menu", "CANCEL": "cancel",
          "SHOULDER_L": "shoulder_l", "SHOULDER_R": "shoulder_r"}
KEYCODE = {"ArrowUp": (KEY_UP, ""), "ArrowDown": (KEY_DOWN, ""), "Enter": (KEY_ENTER, "")}


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run([sys.executable, "-c", _QT], capture_output=True, text=True, timeout=300,
                          env=env, cwd=str(REPO))
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("FACTS")), None)
    if line is None:
        pytest.skip(f"the Qt game could not be built here: {proc.stderr[-800:]}")
    return json.loads(line[len("FACTS"):])


def _code(key):
    return KEYCODE.get(key, (ord(key) if len(key) == 1 else 0, key if len(key) == 1 else ""))


# 1. the same rules (the Qt game is a PongModel)
def test_the_qt_game_runs_the_same_model(qt):
    assert qt["shares_model"] is True
    assert isinstance(PongApp().game, PongModel)


# 2. the same keys, both players
def test_bindings_match_the_qt_game(qt):
    for key, action in qt["p1"].items():
        assert PongApp.binding(*_code(key)) == (ACTION[action], False), key
    for key, action in qt["p2"].items():
        assert PongApp.binding(*_code(key)) == (ACTION[action], True), key


def test_keys_drive_the_game_like_the_qt_controller():
    app = make_app()
    game = app.game
    game.serve_timer = 0.0
    app.key(ord("p"), "p")
    assert game.paused is True
    app.key_release(ord("p"), "p")
    app.key(ord("p"), "p")
    assert game.paused is False
    vs = game.vs_computer
    app.key(ord("m"), "m")
    assert game.vs_computer is (not vs)
    game.player_score = 5
    app.key(ord("r"), "r")
    assert game.player_score == 0


def test_sound_is_greyed_without_an_audio_output_and_works_with_one():
    app = make_app()
    app.set_sound()
    assert app.sound_enabled is False
    calls = []
    audio = SimpleNamespace(sfx=lambda *a: calls.append(("sfx", a)), set_enabled=lambda on: calls.append(("on", on)),
                            close=lambda: None)
    app = make_app(audio=audio)
    app.set_sound()
    assert app.sound_enabled is True and ("on", True) in calls
    app.game._sfx("paddle", 660.0)
    assert ("sfx", ("paddle", 660.0)) in calls


@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (820, 640)])
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

    result = qt_free("pong")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("pong"))["controls_without_tooltip"] == []
