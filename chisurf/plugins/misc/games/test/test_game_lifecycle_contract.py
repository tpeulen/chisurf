"""Preserved game behavior and separately selected required lifecycle repairs.

``-k 'not required_boundary'`` locks existing behavior. ``-k required_boundary``
selects intentional lifecycle corrections, which fail against the old apps.
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import random

import pytest
from emtk import i18n
from emtk.keys import KEY_RIGHT, KEY_UP
from emtk.testing import RecordingPainter

APPS = {
    "pong": ("pong.app", "PongApp"),
    "breakout": ("breakout.app", "BreakoutApp"),
    "tetris": ("tetris.app", "TetrisApp"),
    "number": ("number_quest.gui.app", "NumberQuestApp"),
    "mines": ("minesweeper.gui.app", "MinesweeperApp"),
}


class RecordingAudio:
    """Observe optional backend cleanup without opening an audio device."""

    def __init__(self):
        self.enabled = []
        self.closed = 0
        self.effects = []

    def set_enabled(self, enabled):
        """Record backend enablement independently of persisted preference."""
        self.enabled.append(enabled)

    def close(self):
        """Count resource-release calls."""
        self.closed += 1

    def sfx(self, name, frequency):
        """Record a supplied effect without producing sound."""
        self.effects.append((name, frequency))


def make_game(name, audio=None):
    """Construct the real game with a fixed clock and reproducible random seed."""
    module, cls = APPS[name]
    factory = getattr(importlib.import_module(f"chisurf.plugins.misc.games.{module}"), cls)
    state = random.getstate()
    try:
        random.seed(154)
        kwargs = {"clock": lambda: 0.0}
        if name in {"pong", "tetris", "number"}:
            kwargs["audio"] = audio
        return factory(**kwargs)
    finally:
        random.setstate(state)


def close_game(app):
    """Release optional app resources when the old app exposes that boundary."""
    close = getattr(app, "close", None)
    if callable(close):
        close()


def press_direction(app, name):
    """Exercise each app's actual directional input representation."""
    key = KEY_UP if name == "pong" else KEY_RIGHT
    assert app.key(key)
    return key


def behavior_snapshot(name):
    """Record deterministic numeric state and complete rendering command evidence."""
    locale = i18n.get_locale()
    i18n.set_locale("en")
    app = make_game(name)
    try:
        app.io.wall_clock = False
        key = press_direction(app, name)
        app.advance(0.05)
        app.key_release(key)
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *app.window_size)
        state = copy.deepcopy(app.export_settings())
        calls = json.loads(json.dumps(painter.calls))
        return {
            "state": state,
            "window": list(app.window_size),
            "commands": calls,
            "command_sha256": hashlib.sha256(
                json.dumps(calls, sort_keys=True).encode()
            ).hexdigest(),
        }
    finally:
        close_game(app)
        i18n.set_locale(locale)


@pytest.mark.parametrize("name", APPS)
def test_existing_numerical_render_and_exported_state_are_repeatable(name):
    """A fixed real input produces identical exported values and draw commands."""
    before = behavior_snapshot(name)
    after = behavior_snapshot(name)
    assert before == after
    assert before["commands"] and before["state"]


@pytest.mark.parametrize("name", APPS)
def test_existing_focus_clears_owned_input_and_frame_clock(name):
    """Focus loss clears the app's actual held directions and repeat state."""
    app = make_game(name)
    try:
        press_direction(app, name)
        if name == "pong":
            assert app.key(ord("W"), "w")
        app.last_frame = 12.0
        app.focus_lost()
        assert app.last_frame is None
        if name in {"number", "mines"}:
            assert not app.held
            if name == "number":
                assert not app.repeat
        else:
            assert not app.keys.held and not app.keys.pressed
            if name == "pong":
                assert not app.p2.held
            if name == "tetris":
                assert app.game._repeat_action is None and app.game._repeat_timer == 0
    finally:
        close_game(app)


@pytest.mark.parametrize("name", ["pong", "tetris", "number"])
def test_existing_focus_mutes_backend_without_changing_sound_preference(name):
    """Losing focus disables supplied playback but keeps the saved user choice."""
    audio = RecordingAudio()
    app = make_game(name, audio)
    try:
        app.sound_enabled = True
        app.focus_lost()
        assert audio.enabled == [False]
        assert app.sound_enabled is True
        assert app.export_settings()["sound_enabled"] is True
    finally:
        close_game(app)


@pytest.mark.parametrize("name", ["pong", "breakout"])
def test_existing_physics_steps_are_bounded_without_replacing_model(name, monkeypatch):
    """Real physics runs through at most 1/120 second steps and a 0.1 second cap."""
    app = make_game(name)
    durations = []
    update = app.game.update

    def observed(dt, inputs):
        """Record durations while executing the unchanged numerical model."""
        durations.append(dt)
        return update(dt, inputs)

    monkeypatch.setattr(app.game, "update", observed)
    try:
        app.advance(0.5)
        assert durations and max(durations) <= 1 / 120
        assert sum(durations) == pytest.approx(0.1)
    finally:
        close_game(app)


@pytest.mark.parametrize("name", ["pong", "tetris", "number"])
def test_required_boundary_close_releases_supplied_audio_once(name):
    """Intentional fix: repeated close calls release the backend exactly once."""
    audio = RecordingAudio()
    app = make_game(name, audio)
    app.sound_enabled = True
    app.close()
    app.close()
    assert audio.closed == 1
    assert app.sound_enabled is True
    assert not app.animating()


@pytest.mark.parametrize("name", APPS)
def test_required_boundary_pending_frame_is_serviceable_while_idle(name):
    """Intentional fix: requested repaint survives an idle or paused predicate."""
    app = make_game(name)
    try:
        if hasattr(app.game, "paused"):
            app.game.paused = True
        app.focus_lost()
        app.wants_frame = False
        state = copy.deepcopy(app.export_settings())
        app.request_frame()
        assert app.animating()
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *app.window_size)
        assert app.export_settings() == state
    finally:
        close_game(app)


@pytest.mark.parametrize("name", APPS)
def test_required_boundary_closed_app_rejects_input_and_stops_frames(name):
    """Intentional fix: every closed game rejects new held input and frame demand."""
    app = make_game(name)
    app.close()
    state = copy.deepcopy(app.export_settings())
    assert not app.key(KEY_UP if name == "pong" else KEY_RIGHT)
    app.request_frame()
    assert not app.animating()
    assert app.export_settings() == state


@pytest.mark.parametrize("name", APPS)
def test_existing_exported_round_restores_without_shape_or_value_changes(name):
    """Actual atomic state readers retain complete values after real directional input."""
    saved = behavior_snapshot(name)["state"]
    app = make_game(name)
    try:
        app.restore_settings(copy.deepcopy(saved))
        assert app.export_settings() == saved
    finally:
        close_game(app)


def test_required_boundary_focus_clears_second_player_pending_edges():
    """Intentional fix: focus loss cannot replay a queued second-player key edge."""
    app = make_game("pong")
    try:
        assert app.key(ord("W"), "w")
        assert app.p2.pressed
        app.focus_lost()
        assert not app.p2.pressed and not app.p2.held
    finally:
        close_game(app)


def test_required_boundary_closed_pong_pointer_cannot_move_paddle():
    """Intentional fix: direct pointer delivery cannot mutate a closed round."""
    app = make_game("pong")
    app.draw(RecordingPainter(), 0, 0, *app.window_size)
    app.close()
    before = copy.deepcopy(app.export_settings())
    x, y, scale = app.board
    app.pointer_move(x + 30 * scale, y + 80 * scale, buttons=1)
    assert app.export_settings() == before


@pytest.mark.parametrize("name", ["pong", "tetris", "number"])
@pytest.mark.parametrize("preference", [False, True])
def test_required_boundary_closed_audio_ignores_effects_and_toggles(name, preference):
    """Intentional fix: closed resources receive no effects or preference toggles."""
    audio = RecordingAudio()
    app = make_game(name, audio)
    app.sound_enabled = preference
    app.close()
    calls_after_close = (list(audio.enabled), list(audio.effects), audio.closed)
    app.sfx("late-effect", 440)
    app.set_sound()
    assert (audio.enabled, audio.effects, audio.closed) == calls_after_close
    assert app.sound_enabled is preference
    assert app.export_settings()["sound_enabled"] is preference
