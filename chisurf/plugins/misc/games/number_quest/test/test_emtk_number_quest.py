"""The native Number Quest: rounds against the core rules, the documented keys, sound, drawing.

The oracle for a round is the core (:class:`..core.game.NumberQuestGame`) played directly, with the
app's lifetime wording for the hints; the keys are the ones ``gui/help.md`` documents.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from emtk.keys import KEY_DOWN, KEY_ENTER, KEY_ESCAPE, KEY_LEFT, KEY_RIGHT, KEY_UP
from emtk.testing import RecordingPainter

from chisurf.plugins.emtk_layout import SOUND_OFF_ICON, action_caption
from chisurf.plugins.misc.games.number_quest.core.game import GuessStatus, NumberQuestGame
from chisurf.plugins.misc.games.number_quest.gui.app import NumberQuestApp, make_app

HERE = Path(__file__).parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
ROUNDS = [[10], [90], [37], [10, 20, 30, 40, 50, 60, 70], [50, 25, 37]]

#: The controls ``gui/help.md`` lists: key -> the app action that does it.
DOCUMENTED_KEYS = {
    "ArrowLeft": "left",  # fine step down
    "ArrowDown": "left",
    "ArrowRight": "right",  # fine step up
    "ArrowUp": "right",
    "q": "coarse_left",  # steps of ten
    "e": "coarse_right",
    "Enter": "confirm",  # submit
    " ": "confirm",
    "r": "restart",
    "Escape": "restart",
    "m": "sound",
}


def _core_rounds():
    """Play ROUNDS on the core rules directly, hints worded as lifetimes."""
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


KEYCODE = {
    "ArrowLeft": (KEY_LEFT, ""),
    "ArrowRight": (KEY_RIGHT, ""),
    "ArrowDown": (KEY_DOWN, ""),
    "ArrowUp": (KEY_UP, ""),
    "Enter": (KEY_ENTER, ""),
    "Escape": (KEY_ESCAPE, ""),
}


# 1. the app's rounds end as the core rules end them
def test_rounds_follow_the_core_rules():
    for seq, core_trail in zip(ROUNDS, _core_rounds()):
        app = NumberQuestApp()
        app.game.reset(target=37)
        trail = []
        for value in seq:
            app.estimate = value
            app.submit()
            trail.append(
                [app.message, app.game.attempts_remaining, app.game.score, app.game.status.value]
            )
        assert trail == core_trail, seq


# 2. the documented keys
def test_the_documented_keys_are_bound():
    for key, action in DOCUMENTED_KEYS.items():
        code, text = KEYCODE.get(
            key, (ord(key) if len(key) == 1 else 0, key if len(key) == 1 else "")
        )
        assert NumberQuestApp.binding(code, text) == action, key


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
