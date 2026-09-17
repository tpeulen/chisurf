"""A floating window is repainted when what it draws changes.

Why this exists
---------------
The chrome caches last frame's vertices per **block**: one for the furniture
under the windows, one per floating window, one for the furniture over them.
A block is rebuilt when its key moves, and the win from splitting windows out
is that dragging a panel does not re-emit the object list.

Splitting them out is also how the Mouse panel died. A window's key was its
frame -- position, size, collapsed, title -- plus a `body_revision` counter
that whoever changed the body was supposed to bump. The Mouse panel's body
draws the frame number, the playback stride, the averaging window and the mouse
mode, and *none of those are written by the panel*: the playback loop writes
them from outside, once a frame, and bumps nothing. So the panel showed
``State 1 / 464`` through an entire trajectory, its slider never moved and its
buttons looked dead -- while every press was working perfectly on the model
underneath.

The ingredients were never missing. `chrome_fingerprint()` has carried
``state``, ``stride``, ``average``, ``mouse_mode`` and ``selecting`` since long
before any of this; the split simply stopped windows from consulting it. So a
window that does not say what it draws is keyed on the whole fingerprint --
what it compared before the split, still cached through camera motion, which is
the only time the frame rate is being watched. A window that *does* say
(:attr:`GuiWindow.body_key`, :mod:`emtk.redraw`) is keyed on exactly that.

What is pinned here is that property, not the mechanism: change something a
body draws, and the body is redrawn.

The other half of the contract -- the framework invalidating a window when
routed input reaches its body -- is `test_window_body_invalidation.py`, which
drives real presses through a real renderer. This one is about the state a
window draws that no press ever touches.
"""

from __future__ import annotations

import pytest
from chimol.ui.gui._common import GuiWindow
from chimol.ui.gui.gui import InternalGui
from emtk import redraw
from emtk.testing import RecordingPainter


@pytest.fixture()
def gui():
    """A laid-out chrome with the Mouse panel floating, as a user undocks it."""
    panel = InternalGui()
    panel.layout(1200, 800)
    panel.mouse_window.docked = False
    panel.layout(1200, 800)
    return panel


def _keys(panel) -> dict:
    """Every block's key, by the window it belongs to (``None`` = furniture)."""
    out = {}
    for key, _paint in panel.paint_blocks(RecordingPainter):
        out[key[1] if key[0] == "window" else key[0]] = key
    return out


def _mouse_key(panel):
    key = _keys(panel).get("mouse")
    assert key is not None, "the Mouse panel is not a block at all"
    return key


@pytest.mark.parametrize(
    "field, value",
    [
        ("state", (100, 464)),  # the frame counter, written by the playback loop
        ("stride", 3),  # the stride slider
        ("average", 5),  # the averaging slider
        ("mouse_mode", "editing"),
        ("selecting", "residues"),
    ],
)
def test_the_mouse_panel_repaints_when_what_it_draws_moves(gui, field, value):
    """Each of these is drawn in the block and written from outside it."""
    gui.state = (1, 464)
    before = _mouse_key(gui)
    setattr(gui, field, value)
    assert _mouse_key(gui) != before, f"{field} moved and the panel did not"


def test_a_window_still_caches_when_nothing_it_draws_moved(gui):
    """The point of the split: an idle chrome re-emits nothing."""
    first = _keys(gui)
    assert _keys(gui) == first


def test_a_declared_key_is_what_the_window_is_cached_on(gui):
    """A body that says what it draws is keyed on exactly that."""
    drawn = {"rows": 1}
    win = gui.add_window(
        GuiWindow(
            key="declared",
            title="Declared",
            body=lambda p, rect: None,
            body_key=lambda: drawn["rows"],
        )
    )
    win.docked = False
    gui.layout(1200, 800)

    before = _keys(gui)["declared"]
    drawn["rows"] = 2
    assert _keys(gui)["declared"] != before


def test_a_body_whose_summary_raises_is_redrawn_not_fatal(gui):
    """Emtk's contract: an unsummarisable body costs a repaint, not the window."""

    def broken():
        raise RuntimeError("no")

    win = gui.add_window(
        GuiWindow(
            key="broken",
            title="Broken",
            body=lambda p, rect: None,
            body_key=broken,
        )
    )
    win.docked = False
    gui.layout(1200, 800)

    assert redraw.is_always(redraw.content_key(gui.window("broken")))
    assert _keys(gui)["broken"] != _keys(gui)["broken"]


def test_dragging_the_stride_slider_moves_it_and_shows_it(gui):
    """The user-visible half: "the slider does not work".

    It always worked. A press took the groove, the drag set the stride, the
    playback listener was told -- and the panel was drawn from a cache that
    predated all of it, so the thumb never left the left-hand end. Both halves
    are checked here, in one gesture, because passing only the first is exactly
    the state that was shipped.
    """
    groove = gui._stride_groove
    assert groove.w > 0.0, "the stride slider was not laid out"
    before_key, before = _mouse_key(gui), gui.stride

    assert gui.mouse_press(groove.x + groove.w * 0.5, groove.y + groove.h * 0.5)
    assert gui._dragging_playback == "stride"
    gui.drag(groove.x + groove.w * 0.85, groove.y + groove.h * 0.5)
    gui.release()

    assert gui.stride > before, "the drag did not reach the model"
    assert _mouse_key(gui) != before_key, "the drag never reached the screen"
