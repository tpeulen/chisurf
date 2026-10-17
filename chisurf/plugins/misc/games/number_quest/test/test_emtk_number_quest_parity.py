"""The native Number Quest against the retired Qt chigame view.

The Qt view's ``submit`` is transcribed below from its last committed source over the shared core
rules (:class:`..core.game.NumberQuestGame`); the same rounds are played on the emtk app and
compared, and the view's key bindings are frozen from the same source.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from emtk.keys import KEY_ENTER, KEY_LEFT, KEY_RIGHT
from emtk.testing import RecordingPainter

from chisurf.plugins.emtk_layout import SOUND_OFF_ICON, action_caption
from chisurf.plugins.misc.games.number_quest.core.game import GuessStatus, NumberQuestGame
from chisurf.plugins.misc.games.number_quest.gui.app import NumberQuestApp, make_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
ROUNDS = [[10], [90], [37], [10, 20, 30, 40, 50, 60, 70], [50, 25, 37]]

#: The Qt view's bindings (last committed ``gui/tool.py``), key -> chigame action name.
QT_BINDINGS = {
    "ArrowLeft": "LEFT",
    "ArrowRight": "RIGHT",
    "Enter": "CONFIRM",
    " ": "CONFIRM",
    "r": "CANCEL",
    "q": "SHOULDER_L",
    "e": "SHOULDER_R",
}


def _qt_view_rounds():
    """Play ROUNDS the way the retired view's ``submit`` did, over the core rules."""
    rounds = []
    for seq in ROUNDS:
        game = NumberQuestGame()
        game.reset(target=37)
        trail = []
        message = ""
        for value in seq:
            if game.status is not GuessStatus.ACTIVE:
                game.reset()
                message = "Dial an estimate, then confirm."
            else:
                result = game.guess(value)
                message = (
                    result.message.replace("Higher!", "Longer lifetime.")
                    .replace("Lower!", "Shorter lifetime.")
                    .replace("Try again.", "")
                    .strip()
                )
            trail.append([message, game.attempts_remaining, game.score, game.status.value])
        rounds.append(trail)
    return rounds


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


# 1. the same rounds end the same way
def test_rounds_match_the_qt_game():
    for seq, qt_trail in zip(ROUNDS, _qt_view_rounds()):
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
def test_bindings_match_the_qt_game():
    for key, action in QT_BINDINGS.items():
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
    # The shared Sound toggle, off by default (chisurf.plugins.emtk_layout.sound_toggle).
    assert action_caption("sound", SOUND_OFF_ICON) in painter.strings


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
