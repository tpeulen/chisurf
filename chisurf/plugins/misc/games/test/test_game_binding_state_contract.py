"""Committed binding precedence and atomic state contracts before shared extraction."""

from __future__ import annotations

import copy
import hashlib
import json
import random

import pytest
from emtk import keys

from .test_game_lifecycle_contract import (
    APPS,
    RecordingAudio,
    behavior_snapshot,
    close_game,
    make_game,
    press_direction,
)

PHYSICAL = sorted(
    set(range(-2, 130))
    | {
        value
        for name, value in vars(keys).items()
        if name.startswith("KEY_") and type(value) is int
    }
    | {0x110000, 999999}
)
TEXTS = (
    "",
    "p",
    "P",
    "w",
    "s",
    "q",
    "E",
    "r",
    "m",
    "n",
    "f",
    " ",
    "left",
    "pq",
    "é",
    "ß",
    "🙂",
    "\n",
    "\t",
    "UP",
)


def expected_binding(name, key, text):
    """Express the existing user contract, including conflicting key/text priority."""
    letter = (text or (chr(key) if 32 <= key < 127 else "")).lower()
    if name == "pong":
        if key in (keys.KEY_UP, keys.KEY_LEFT, keys.KEY_DOWN, keys.KEY_RIGHT):
            return ("up" if key in (keys.KEY_UP, keys.KEY_LEFT) else "down", False)
        if letter in ("w", "s"):
            return ("up" if letter == "w" else "down", True)
        if key == keys.KEY_ESCAPE:
            return "cancel", False
        action = {
            "p": "menu",
            "r": "cancel",
            "m": "shoulder_l",
            "n": "shoulder_r",
            " ": "confirm",
        }.get(letter)
        if action is None and key in (keys.KEY_ENTER, keys.KEY_RETURN):
            action = "confirm"
        return action, False
    directions = {keys.KEY_LEFT: "left", keys.KEY_RIGHT: "right"}
    if name == "tetris":
        directions.update({keys.KEY_DOWN: "down", keys.KEY_UP: "confirm"})
    else:
        # Breakout and Number Quest: Down is an alias of Left, Up of Right.
        directions.update({keys.KEY_DOWN: "left", keys.KEY_UP: "right"})
    # Physical keys outrank any text, so these are resolved before the letter table.
    if key in (keys.KEY_ENTER, keys.KEY_RETURN):
        directions[key] = "confirm"
    if key == keys.KEY_ESCAPE:
        directions[key] = "restart" if name == "number" else "cancel"
    if key in directions:
        return directions[key]
    return {
        "breakout": {" ": "confirm", "p": "menu", "r": "cancel", "m": "shoulder_r"},
        "tetris": {"p": "menu", "r": "cancel", " ": "shoulder_r", "m": "shoulder_l"},
        "number": {
            "q": "coarse_left",
            "e": "coarse_right",
            "r": "restart",
            " ": "confirm",
            "m": "sound",
        },
    }[name].get(letter)


def binding_matrix():
    """Capture every public resolver result and physical/text conflict explicitly."""
    result = {}
    for name in ("pong", "breakout", "tetris", "number"):
        app = make_game(name)
        try:
            result[name] = [
                [key, text, app.binding(key, text)] for key in PHYSICAL for text in TEXTS
            ]
        finally:
            close_game(app)
    return result


@pytest.mark.parametrize("name", ["pong", "breakout", "tetris", "number"])
def test_binding_matrix_preserves_known_unknown_and_conflicting_inputs(name):
    """All physical keys and text spellings retain exact action and unbound shape."""
    app = make_game(name)
    try:
        for key in PHYSICAL:
            for text in TEXTS:
                assert app.binding(key, text) == expected_binding(name, key, text), (
                    name,
                    key,
                    text,
                )
    finally:
        close_game(app)


def mines_input_matrix():
    """Capture actual minefield input effects where no binding API existed."""
    result = []
    physical = [
        -1,
        0,
        32,
        ord("F"),
        ord("Q"),
        ord("E"),
        ord("R"),
        999999,
        keys.KEY_LEFT,
        keys.KEY_RIGHT,
        keys.KEY_UP,
        keys.KEY_DOWN,
        keys.KEY_ENTER,
        keys.KEY_RETURN,
        keys.KEY_ESCAPE,
    ]
    for key in physical:
        for text in TEXTS:
            app = make_game("mines")
            rng = random.getstate()
            try:
                # Difficulty changes and restarts generate new boards after construction.
                random.seed(154)
                handled = app.key(key, text)
                state = app.export_settings()
                result.append([key, text, handled, sorted(app.held), state])
            finally:
                random.setstate(rng)
                close_game(app)
    return result


def test_minefield_physical_priority_and_text_recognition_use_real_rules():
    """Arrow and confirm keys retain priority over conflicting text actions."""
    for key, text, handled, held, state in mines_input_matrix():
        letter = (text or (chr(key) if 32 <= key < 127 else "")).lower()
        direction = {
            keys.KEY_LEFT: (0, -1),
            keys.KEY_RIGHT: (0, 1),
            keys.KEY_UP: (-1, 0),
            keys.KEY_DOWN: (1, 0),
        }.get(key)
        expected = (
            direction is not None
            or key in (keys.KEY_ENTER, keys.KEY_RETURN, 32)
            or key == keys.KEY_ESCAPE
            or letter in {" ", "f", "r", "q", "e", "m"}
        )
        assert handled is expected, (key, text)
        if direction is not None:
            assert held == [direction]
            assert state["cursor"] == [4 + direction[0], 4 + direction[1]]
            assert (state["rows"], state["columns"]) == (9, 9)


def transient_state(app, audio):
    """Observe input, frame, audio and view state without copying the live model."""
    result = {}
    for name in (
        "keys",
        "p2",
        "held",
        "repeat",
        "last_frame",
        "closed",
        "wants_frame",
        "sound_enabled",
        "history",
        "hint",
        "message",
        "cursor_row",
        "cursor_col",
    ):
        if hasattr(app, name):
            value = getattr(app, name)
            result[name] = copy.deepcopy(vars(value) if hasattr(value, "__dict__") else value)
    result["audio"] = copy.deepcopy(vars(audio))
    return result


def corrupt_late(name, saved):
    """Invalidate a field reached after construction and most candidate validation."""
    if name in {"breakout", "tetris"}:
        saved["sound_enabled"] = "invalid boolean"
    elif name == "pong":
        saved["game"]["serve_timer"] = -1
    elif name == "number":
        saved["history"] = [saved["target"], saved["target"]]
    else:
        saved["difficulty_index"] = "not an integer"


@pytest.mark.parametrize("name", APPS)
def test_late_invalid_state_leaves_identity_inputs_audio_and_values_unchanged(name):
    """Failure after preparing a candidate cannot partially commit any app state."""
    audio = RecordingAudio()
    app = make_game(name, audio)
    try:
        press_direction(app, name)
        app.last_frame = 17.25
        app.sound_enabled = True
        saved = copy.deepcopy(app.export_settings())
        before = transient_state(app, audio)
        model = app.game
        invalid = copy.deepcopy(saved)
        corrupt_late(name, invalid)
        with pytest.raises(ValueError):
            app.restore_settings(invalid)
        assert app.game is model
        assert app.export_settings() == saved
        assert transient_state(app, audio) == before
    finally:
        close_game(app)


def mutate_tree(value):
    """Invalidate every returned mutable container to detect aliases."""
    if isinstance(value, dict):
        for child in list(value.values()):
            mutate_tree(child)
        value["foreign"] = True
    elif isinstance(value, list):
        for child in list(value):
            mutate_tree(child)
        value.append("foreign")


@pytest.mark.parametrize("name", APPS)
def test_exports_and_restored_input_are_detached_mutable_snapshots(name):
    """Export and restore exchange values, never references to caller-owned lists."""
    app = make_game(name)
    try:
        saved = app.export_settings()
        before = copy.deepcopy(saved)
        mutate_tree(saved)
        assert app.export_settings() == before
        incoming = copy.deepcopy(before)
        app.restore_settings(incoming)
        assert app.export_settings() == before
        mutate_tree(incoming)
        assert app.export_settings() == before
    finally:
        close_game(app)


@pytest.mark.parametrize("name", APPS)
def test_state_roundtrip_preserves_exact_shape_and_values(name):
    """Round trips keep the actual application's exported numerical contract."""
    saved = behavior_snapshot(name)["state"]
    app = make_game(name)
    try:
        app.restore_settings(copy.deepcopy(saved))
        assert app.export_settings() == saved
    finally:
        close_game(app)


@pytest.mark.parametrize("name", ["pong", "breakout", "mines"])
def test_existing_permissive_coercions_remain_supported(name):
    """Accepted integral floats and explicit minefield conversions remain accepted."""
    app = make_game(name)
    try:
        state = app.export_settings()
        if name == "pong":
            state["game"]["player_score"] = 2.0
            state["sound_enabled"] = "false"
        elif name == "breakout":
            state["game"]["score"] = 2.0
        else:
            state["rows"] = str(state["rows"])
            state["columns"] = float(state["columns"])
            state["mines"] = str(state["mines"])
            state["cursor"] = ["2", 3.0]
            state["difficulty_index"] = "4"
            state["message"] = 123
            state["sound_enabled"] = "false"
        app.restore_settings(state)
        result = app.export_settings()
        if name == "mines":
            assert result["cursor"] == [2, 3] and result["message"] == "123"
            assert result["difficulty_index"] == 1 and result["sound_enabled"] is True
        else:
            field = "player_score" if name == "pong" else "score"
            assert result["game"][field] == 2.0 and type(result["game"][field]) is float
            if name == "pong":
                assert result["sound_enabled"] is True
    finally:
        close_game(app)


@pytest.mark.parametrize("name", ["pong", "breakout", "tetris", "number"])
def test_boolean_is_not_a_numeric_state_value(name):
    """The stricter four numerical validators must not coerce booleans to integers."""
    app = make_game(name)
    try:
        state = app.export_settings()
        if name == "number":
            state["estimate"] = True
        else:
            state["game"]["player_score" if name == "pong" else "score"] = True
        model = app.game
        with pytest.raises(ValueError):
            app.restore_settings(state)
        assert app.game is model
    finally:
        close_game(app)


def contract_snapshot():
    """Publish complete binding/state/paint evidence for independent before/after checks."""
    matrix = binding_matrix()
    mines = mines_input_matrix()
    return {
        "bindings": matrix,
        "mines_inputs": mines,
        "games": {name: behavior_snapshot(name) for name in APPS},
        "binding_sha256": hashlib.sha256(json.dumps(matrix, sort_keys=True).encode()).hexdigest(),
    }


@pytest.mark.parametrize("name", ["pong", "mines"])
def test_required_raising_sound_coercion_leaves_live_state_unchanged(name):
    """Intentional fix: failing custom truth conversion cannot partially commit a round."""

    class InvalidTruth:
        """Represent a non-JSON caller whose boolean conversion fails."""

        def __bool__(self):
            """Raise during the existing permissive sound preference coercion."""
            raise RuntimeError("sound truth conversion failed")

    audio = RecordingAudio()
    app = make_game(name, audio)
    try:
        press_direction(app, name)
        app.last_frame = 17.25
        app.sound_enabled = True
        saved = copy.deepcopy(app.export_settings())
        before = transient_state(app, audio)
        model = app.game
        invalid = copy.deepcopy(saved)
        invalid["sound_enabled"] = InvalidTruth()
        with pytest.raises(RuntimeError, match="sound truth conversion failed"):
            app.restore_settings(invalid)
        assert app.game is model
        assert app.export_settings() == saved
        assert transient_state(app, audio) == before
    finally:
        close_game(app)
