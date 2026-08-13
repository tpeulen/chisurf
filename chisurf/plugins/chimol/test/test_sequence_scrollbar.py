"""The sequence scrollbar's thumb stays under the pointer that is dragging it.

The report
----------
"The scrolling of the sequence using the scrollbar is stuttering."

It was not a frame-rate problem. Two places mapped between a scroll position
and a thumb position, and they used **different mappings**:

* the layout drew the thumb at ``scroll / longest`` of the track;
* the drag read the cursor as ``fraction * max_scroll``, over the full track
  width -- ignoring that the thumb's left edge can only travel
  ``track.w - thumb.w`` before its right edge hits the end.

So the thumb trailed the pointer by a factor of ``1 - visible / longest``, and
the gap grew across the track. Because the scroll is a whole number of
residues, it closed that gap in visible jerks -- the pointer moving smoothly
and the thumb moving in steps is what "stuttering" was.

What this pins
--------------
* the thumb follows the pointer, within a residue's width, the whole way
  across -- the drift is the bug and a mid-track sample is where it shows;
* the *grabbed point* of the thumb stays under the cursor, so a press on the
  thumb does not jump the sequence before the drag has moved;
* the ends are reachable and exact: dragging to the far right shows the last
  residue, which the old mapping could not do since the thumb ran out of
  travel first.
"""
from __future__ import annotations

import pytest

from toolkit_free import probe


@pytest.fixture(scope="module")
def measured():
    return probe('''
        app = open_app(size=(1000, 700))
        app.cmd.do("fetch 148L")
        app.cmd.do("info_panel off")
        gui = app.renderer._internal_gui
        gui.sequence_visible = True
        app.renderer.draw_frame()

        track, thumb = gui._seq_track, gui._seq_thumb
        emit("scrollable", "yes" if gui.max_scroll() > 0 else "no")
        emit("thumb_narrower_than_track", "yes" if thumb.w < track.w else "no")

        # Grab the thumb a third of the way in and walk it across the track.
        grab_x = thumb.x + thumb.w / 3.0
        y = track.y + track.h / 2.0
        gui.mouse_press(grab_x, y)
        emit("scroll_on_press", gui._seq_scroll)

        drift = []
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = track.x + (track.w - thumb.w) * fraction + thumb.w / 3.0
            gui.drag(x, y)
            # Where the thumb ended up versus where the grabbed point is.
            held = gui._seq_thumb.x + thumb.w / 3.0
            drift.append(abs(held - min(max(x, track.x), track.x + track.w)))
        emit("max_drift", max(drift))

        # The far end must reach the last residue exactly.
        gui.drag(track.x + track.w + 50.0, y)
        emit("scroll_at_end", gui._seq_scroll)
        emit("max_scroll", gui.max_scroll())
        gui.drag(track.x - 50.0, y)
        emit("scroll_at_start", gui._seq_scroll)
        gui.release()
    ''')


def test_the_strip_is_actually_scrollable(measured):
    """The premise: a lysozyme sequence is wider than the strip."""
    assert measured["scrollable"] == "yes"
    assert measured["thumb_narrower_than_track"] == "yes"


def test_pressing_the_thumb_does_not_jump_the_sequence(measured):
    """The grabbed point is held; the old code snapped the edge to the cursor."""
    assert int(measured["scroll_on_press"]) == 0, (
        "pressing the thumb without moving it scrolled the strip"
    )


def test_the_thumb_follows_the_pointer_across_the_track(measured):
    """Within a few pixels the whole way -- the growing gap is the stutter."""
    assert float(measured["max_drift"]) < 6.0, (
        f"the thumb trailed the pointer by {measured['max_drift']}px; the drag "
        "and the layout are using different mappings again"
    )


def test_both_ends_are_reachable(measured):
    """The far right shows the last residue, and the far left the first."""
    assert int(measured["scroll_at_end"]) == int(measured["max_scroll"])
    assert int(measured["scroll_at_start"]) == 0


def test_scrolling_actually_redraws_the_strip():
    """The other half of the stutter, and the larger one.

    The chrome is cached against a fingerprint of its own state, and the
    sequence's scroll position was **not in it**. So scrolling moved the rows,
    laid them out again, and put not one pixel on screen: the strip redrew only
    when something else in the fingerprint happened to change -- a hover
    crossing a row, the status line -- so it advanced in bursts under a pointer
    that was moving smoothly.

    Measured in pixels for that reason. Every piece of state was already
    correct while the screen showed the previous frame.
    """
    measured = probe('''
        app = open_app(size=(1000, 700))
        app.cmd.do("fetch 148L")
        app.cmd.do("info_panel off")
        gui = app.renderer._internal_gui
        gui.sequence_visible = True
        app.renderer.draw_frame()

        strip = slice(int(gui._seq_strip.y), int(gui._seq_strip.y + gui._seq_strip.h))
        before = np.asarray(app.renderer.grab_image())[strip, :, :3].copy()

        moved = gui.scroll_sequence(20)
        app.renderer.draw_frame()
        after = np.asarray(app.renderer.grab_image())[strip, :, :3]

        emit("scrolled", "yes" if moved else "no")
        emit("changed_pixels", int((before != after).sum()))
    ''')

    assert measured["scrolled"] == "yes", "the strip did not scroll at all"
    assert int(measured["changed_pixels"]) > 500, (
        "scrolling the sequence changed no pixels: the cached chrome does not "
        "know the strip moved"
    )
