"""The chrome holds the pointer in **one** slot: press takes it, release drops it.

Ten flags (``_dragging_thumb``, ``_seq_drag``, ``_window_drag`` ...) with an
OR in ``is_dragging``, a ladder in ``drag`` and a clearing list in
``release`` is three places that had to agree; a gesture missing from any of
them read as an unresponsive control (BUG-001/002). They are properties over
one ``Capture`` now -- this pins that: no two gestures at once, every one
ends with the release, and the flags still answer.
"""

from __future__ import annotations

import pytest
from chimol.ui.gui import InternalGui
from chimol.ui.gui.capture import Capture

#: (flag/attribute, value it is set to) -- every gesture the chrome captures.
GESTURES = [
    ("_dragging_splitter", True),
    ("_dragging_thumb", True),
    ("_dragging_timeline", True),
    ("_dragging_ui_scale", True),
    ("_seq_drag", (0, 3)),
    ("_nerd_drag", (2.0, 4.0)),
    ("_window_drag", ("k", 1.0, 2.0)),
    ("_window_resize", ("k", 1.0, 2.0, 3.0, 4.0)),
    ("_window_body_drag", "k"),
    ("_dragging_playback", "speed"),
]


@pytest.fixture
def gui():
    return InternalGui(run_command=lambda _line: None)


def test_a_fresh_chrome_holds_nothing(gui):
    assert not gui.is_dragging()
    assert gui._capture is None
    for name, _value in GESTURES:
        assert not getattr(gui, name)


@pytest.mark.parametrize("name,value", GESTURES)
def test_each_gesture_takes_the_slot_and_answers_its_flag(gui, name, value):
    setattr(gui, name, value)
    assert gui.is_dragging(), name
    assert getattr(gui, name) == value
    assert isinstance(gui._capture, Capture)
    # and it is the *only* one held
    others = [other for other, _v in GESTURES if other != name]
    assert not any(getattr(gui, other) for other in others), name
    gui.release()
    assert not gui.is_dragging() and gui._capture is None
    assert not getattr(gui, name)


def test_a_second_gesture_replaces_the_first(gui):
    gui._dragging_thumb = True
    gui._window_drag = ("k", 0.0, 0.0)
    assert gui._window_drag == ("k", 0.0, 0.0)
    assert not gui._dragging_thumb, "two gestures cannot hold the pointer at once"
    gui.release()
    assert not gui.is_dragging()


def test_clearing_a_gesture_that_is_not_held_leaves_the_slot_alone(gui):
    gui._dragging_thumb = True
    gui._seq_drag = None  # a stale clear must not steal the slot
    assert gui._dragging_thumb and gui.is_dragging()
    gui._dragging_thumb = False
    assert not gui.is_dragging()
