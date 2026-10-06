"""The native Number Quest at parity with the Qt chigame view.

The Qt game (``gui/tool.py``: ``NumberQuestChiGame``) is driven in a subprocess with
a stub host -- the same rounds, the same keys -- and its messages, estimates and
bindings are compared with the emtk app's.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from emtk.keys import KEY_ENTER, KEY_LEFT, KEY_RIGHT
from emtk.testing import RecordingPainter

from chisurf.plugins.misc.games.number_quest.app import NumberQuestApp, make_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
ROUNDS = [[10], [90], [37], [10, 20, 30, 40, 50, 60, 70], [50, 25, 37]]

_QT = r"""
import json, sys
from types import SimpleNamespace
from chisurf.plugins.misc.games.number_quest.gui.tool import BINDINGS, NumberQuestChiGame
rounds = json.loads(sys.argv[1])
results = []
for seq in rounds:
    game = NumberQuestChiGame()
    host = SimpleNamespace(keys=SimpleNamespace(bindings={}), camera=SimpleNamespace(center=[0.0, 0.0], height=0.0),
                           audio=SimpleNamespace(sfx=lambda *a, **k: None))
    game.setup(host)
    game.game.reset(target=37)
    trail = []
    for value in seq:
        game.estimate = value
        game.submit()
        trail.append([game.message, game.game.attempts_remaining, game.game.score, game.game.status.value])
    results.append(trail)
print("FACTS" + json.dumps({"rounds": results, "bindings": {k: v.name for k, v in BINDINGS.items()}}))
"""

#: Qt chigame actions -> the emtk app's action names.
ACTION = {
    "LEFT": "left",
    "RIGHT": "right",
    "CONFIRM": "confirm",
    "CANCEL": "restart",
    "SHOULDER_L": "coarse_left",
    "SHOULDER_R": "coarse_right",
}
KEYCODE = {"ArrowLeft": (KEY_LEFT, ""), "ArrowRight": (KEY_RIGHT, ""), "Enter": (KEY_ENTER, "")}


@pytest.fixture(scope="module")
def qt():
    pytest.importorskip("qtpy")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(REPO), env.get("PYTHONPATH", "")]))
    proc = subprocess.run(
        [sys.executable, "-c", _QT, json.dumps(ROUNDS)],
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


# 1. the same rounds end the same way
def test_rounds_match_the_qt_game(qt):
    for seq, qt_trail in zip(ROUNDS, qt["rounds"]):
        app = NumberQuestApp()
        app.game.reset(target=37)
        trail = []
        for value in seq:
            app.estimate = value
            app.submit()
            trail.append(
                [app.message, app.game.attempts_remaining, app.game.score, app.game.status.value]
            )
        assert trail == qt_trail, seq


# 2. the same keys do the same things
def test_bindings_match_the_qt_game(qt):
    for key, action in qt["bindings"].items():
        code, text = KEYCODE.get(
            key, (ord(key) if len(key) == 1 else 0, key if len(key) == 1 else "")
        )
        assert NumberQuestApp.binding(code, text) == ACTION[action], key


def test_sound_is_greyed_without_an_audio_output_and_works_with_one():
    app = make_app()
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 560, 420)
    app.set_sound()
    assert app.sound_enabled is False  # nothing to switch
    calls = []
    audio = SimpleNamespace(
        sfx=lambda *a: calls.append(("sfx", a)),
        set_enabled=lambda on: calls.append(("on", on)),
        close=lambda: calls.append(("close",)),
    )
    app = make_app(audio=audio)
    app.set_sound()
    assert app.sound_enabled is True and ("on", True) in calls
    app.game.reset(target=37)
    app.estimate = 37
    app.submit()
    assert ("sfx", ("guess", 880)) in calls


# 4. draws at both sizes and the window's own
@pytest.mark.parametrize("size", [(1200, 800), (800, 600), (560, 420)])
def test_draws(size):
    app = make_app()
    painter = RecordingPainter()
    for _ in range(2):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    assert "Sound" in painter.strings


# 6/7. no Qt, tooltips
def test_port_is_qt_free():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("number_quest")
    assert result["ok"], result["output"]


def test_every_control_has_a_tooltip():
    sys.path.insert(0, str(REPO))
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    assert emtk_inventory(build_emtk_app("number_quest"))["controls_without_tooltip"] == []
