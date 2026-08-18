"""The object list is a list: it fits the window, and it scrolls.

It was laid out as "one row per object, as tall as that comes to". A scene of
two molecules is fine; a labelling network is thirty-five objects and a hundred
and forty rows, and the list ran off the bottom of the viewport -- over the
mouse block, over the command line, with the rows past the edge unreachable
because there was nothing to scroll.

Capped to the room below where it starts, scrolled by the wheel and by a bar,
and -- the part that is easy to get wrong -- still indexed by row number: the
hit test, the hover and the per-row buttons all address rows by index, so a
list that *skips* the rows it cannot draw renumbers them, and a click on one
object toggles another.
"""
from __future__ import annotations

import pytest

from chimol.ui.gui import GuiRow, InternalGui


def _gui(rows: int = 140, height: int = 700) -> InternalGui:
    gui = InternalGui()
    gui.set_rows([GuiRow(name=f"object_{index}") for index in range(rows)])
    gui.layout(1000, height)
    return gui


def test_a_long_list_stops_before_the_bottom_of_the_viewport():
    gui = _gui()
    panel = gui.panel_rect
    assert panel.h > 0
    assert panel.y + panel.h < 700, "the list runs off the bottom of the window"


def test_a_short_list_is_exactly_its_rows():
    gui = _gui(rows=3)
    assert gui._panel_overflow == 0.0
    assert gui.objects_bar() is None, "a list that fits needs no bar"


def test_a_long_list_has_a_bar():
    gui = _gui()
    assert gui._panel_overflow > 0.0
    bar = gui.objects_bar()
    assert bar is not None and bar.h > 0
    assert bar.h < gui.panel_rect.h, "the thumb should be shorter than its track"


def test_the_wheel_scrolls_it():
    gui = _gui()
    assert gui.scroll_objects(-100.0)
    assert gui._objects_scroll == pytest.approx(100.0)
    assert gui.scroll_objects(100.0)
    assert gui._objects_scroll == pytest.approx(0.0)


def test_it_cannot_be_scrolled_past_either_end():
    gui = _gui()
    gui.scroll_objects(-10_000.0)
    assert gui._objects_scroll == pytest.approx(gui._panel_overflow)
    gui.scroll_objects(10_000.0)
    assert gui._objects_scroll == pytest.approx(0.0)


def test_rows_keep_their_numbers_when_they_scroll_out():
    """The hit test addresses rows by index; skipping them renumbers them."""
    gui = _gui()
    assert len(gui._row_rects) == 140
    gui.scroll_objects(-400.0)
    gui.layout(1000, 700)
    assert len(gui._row_rects) == 140
    assert len(gui._button_rects) == 140 and len(gui._eye_rects) == 140
    off_screen = [r for r in gui._row_rects if r.w == 0]
    assert off_screen, "nothing scrolled out of a list twice the height of its room"


def test_a_click_lands_on_the_row_that_is_drawn_there():
    gui = _gui()
    gui.scroll_objects(-400.0)
    gui.layout(1000, 700)
    for index, rect in enumerate(gui._row_rects):
        if rect.w <= 0:
            continue
        hit = gui.hit_test(rect.x + rect.w / 2, rect.y + rect.h / 2)
        assert hit.row == index, (
            f"a click in row {index}'s rectangle answered row {hit.row}"
        )
        break


def test_dragging_the_bar_moves_the_list():
    gui = _gui()
    bar = gui.objects_bar()
    panel = gui.panel_rect
    assert gui.press_objects_bar(bar.x + 2.0, bar.y + 2.0)
    gui.drag_objects_bar(panel.y + panel.h)          # thumb to the bottom
    assert gui._objects_scroll == pytest.approx(gui._panel_overflow)
    gui.release_objects_bar()
    assert gui._objects_bar_drag is None


def test_pressing_the_track_jumps_there():
    gui = _gui()
    panel = gui.panel_rect
    bar = gui.objects_bar()
    assert gui.press_objects_bar(bar.x + 2.0, panel.y + panel.h - 4.0)
    assert gui._objects_scroll > 0.0


def test_the_bar_takes_the_press_rather_than_the_row_under_it():
    gui = _gui()
    bar = gui.objects_bar()
    hit = gui.hit_test(bar.x + 2.0, bar.y + 4.0)
    assert hit.kind == "objects_bar"


def test_the_scroll_position_is_part_of_the_sessions_baseline():
    """`reinit` puts the list back to the top with everything else."""
    assert "_objects_scroll" in InternalGui.BASELINE_FIELDS
