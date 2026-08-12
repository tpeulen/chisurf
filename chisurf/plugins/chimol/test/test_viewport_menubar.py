"""The menu bar, drawn in the 3-D view.

Asked directly: *"where are my menus in the 3d view?"* — and the answer was
that they were a Qt menu bar, which on macOS is taken away to the **system**
bar at the top of the screen, nowhere near the viewport, and in a browser does
not exist at all. Drawn by the chrome they are in the same place everywhere.

The menu *contents* were already viewport-drawable: `object_menus.py` has fed
the in-view A/S/H/L/C pop-ups through the same painter for a long time. What
was missing was the bar itself.
"""
from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chisurf.plugins.chimol.chimol.app.menu_bar import MENU_BAR  # noqa: E402
from chisurf.plugins.chimol.chimol.renderer.internal_gui import (  # noqa: E402
    InternalGui,
    SequenceRow,
)

SIZE = (860, 520)


@pytest.fixture
def gui():
    panel = InternalGui(run_command=lambda _c: None)
    panel.menubar = [(title, entries) for title, entries in MENU_BAR if entries]
    panel.layout(*SIZE)
    return panel


def _title(gui, name):
    for rect, title, _entries in gui._menubar_rects:
        if title == name:
            return rect
    raise AssertionError(f"no {name!r} in the bar")


def test_every_menu_is_on_the_bar(gui):
    drawn = [title for _rect, title, _entries in gui._menubar_rects]
    expected = [title for title, entries in MENU_BAR if entries]
    assert drawn == expected


def test_the_titles_do_not_overlap(gui):
    """Two titles sharing a pixel means one of them cannot be clicked."""
    rects = [rect for rect, _t, _e in gui._menubar_rects]
    for left, right in zip(rects, rects[1:]):
        assert left.x + left.w <= right.x + 0.5


def test_a_title_is_reachable_and_opens_its_menu(gui):
    rect = _title(gui, "Display")
    hit = gui.hit_test(rect.x + rect.w / 2, rect.h / 2)
    assert hit.kind == "menubar"

    assert gui.mouse_press(rect.x + rect.w / 2, rect.h / 2)
    assert len(gui._menus) == 1
    assert gui._menus[-1].title.startswith("Display")
    # Index-derived, not hardcoded: a menu added to the bar (Build was)
    # otherwise fails this test without anything being wrong.
    titles = [title for _rect, title, _entries in gui._menubar_rects]
    assert gui._menubar_open == titles.index("Display")


def test_clicking_the_open_title_again_puts_it_away(gui):
    rect = _title(gui, "File")
    gui.mouse_press(rect.x + rect.w / 2, rect.h / 2)
    assert gui._menus
    gui.mouse_press(rect.x + rect.w / 2, rect.h / 2)
    assert not gui._menus
    assert gui._menubar_open == -1


def test_sliding_along_the_bar_switches_menus(gui):
    """Every menu bar does this; without it each title needs its own click."""
    first = _title(gui, "Display")
    gui.mouse_press(first.x + first.w / 2, first.h / 2)
    opened = gui._menus[-1].title

    second = _title(gui, "Wizard")
    gui.mouse_move(second.x + second.w / 2, second.h / 2)
    assert len(gui._menus) == 1, "sliding stacked a second menu"
    assert gui._menus[-1].title != opened
    assert gui._menus[-1].title.startswith("Wizard")


def test_the_bar_takes_a_band_off_the_top_of_the_scene(gui):
    """The renderer asks for one number; the strip stacks under the bar."""
    assert gui.menubar_height() > 0
    assert gui.top_band_height() == gui.menubar_height() + gui.sequence_height()

    gui.sequence_visible = True
    gui.sequences = [
        SequenceRow(name="148l/E", codes="MNIFEML", object_id="o1", chain="E",
                    numbers=list(range(1, 8)), residue_indices=list(range(7)))
    ]
    gui.layout(*SIZE)
    assert gui._seq_strip.y >= gui.menubar_height(), "the strip is under the bar"
    assert gui.top_band_height() > gui.menubar_height()


def test_no_bar_when_the_host_supplies_no_menus():
    """The panel draws menus; it does not know which ones an app has."""
    bare = InternalGui()
    bare.layout(*SIZE)
    assert bare.menubar_height() == 0
    assert bare.hit_test(10, 5).kind != "menubar"


def test_a_menu_entry_still_runs_its_command(gui):
    """The bar is a way in; the entries are the ones the pop-ups already use."""
    ran: list[str] = []
    gui.set_run_command(ran.append)

    # Help, because Display's top level is almost all submenus and a test that
    # happens to find no leaf would pass by doing nothing.
    rect = _title(gui, "Help")
    gui.mouse_press(rect.x + rect.w / 2, rect.h / 2)
    menu = gui._menus[-1]
    for item_rect, entry in menu.item_rects:
        if entry is not None and entry.command and not entry.children:
            gui.mouse_press(item_rect.x + 4, item_rect.y + item_rect.h / 2)
            break
    assert ran, "no command reached the sink"
