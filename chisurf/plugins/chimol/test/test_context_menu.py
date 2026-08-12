"""Right-click in the scene opens the object menus.

The mouse-mode block has always promised this — its `SnglClk` row reads
`R  Menu` — while the five per-object menus were reachable only from the object
list's A/S/H/L/C buttons. A promise printed on screen with nothing behind it is
worse than no promise.
"""
from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chisurf.plugins.chimol.chimol.object_menus import OBJECT_MENUS  # noqa: E402
from chisurf.plugins.chimol.chimol.renderer.internal_gui import (  # noqa: E402
    GuiRow,
    InternalGui,
)

SIZE = (900, 620)


@pytest.fixture
def gui():
    ran: list[str] = []
    panel = InternalGui(run_command=ran.append)
    panel.rows = [
        GuiRow(name="all", is_header=True),
        GuiRow(name="148l"),
        GuiRow(name="sele", is_selection=True),
    ]
    panel.layout(*SIZE)
    panel.ran = ran
    return panel


def test_it_offers_all_five_object_menus(gui):
    assert gui.open_context_menu(240, 300, "148l")
    menu = gui._menus[-1]
    labels = [entry.label for _rect, entry in menu.item_rects if entry]
    assert labels == [title for _key, title, _rows in OBJECT_MENUS]


def test_it_names_what_it_will_act_on(gui):
    gui.open_context_menu(240, 300, "148l")
    assert gui._menus[-1].title.startswith("148l")
    assert gui._menus[-1].target == "148l"


def test_opening_it_again_replaces_rather_than_stacks(gui):
    gui.open_context_menu(240, 300, "148l")
    gui.open_context_menu(400, 200, "148l")
    assert len(gui._menus) == 1


def test_a_submenu_entry_runs_against_the_target(gui):
    gui.open_context_menu(240, 300, "148l")
    menu = gui._menus[-1]
    show = next(r for r, e in menu.item_rects if e is not None and e.label == "Show")
    gui.mouse_move(show.x + 8, show.y + show.h / 2)

    child = gui._menus[-1]
    assert child.title.startswith("Show")
    for rect, entry in child.item_rects:
        if entry is not None and entry.command and not entry.children:
            gui.mouse_press(rect.x + 6, rect.y + rect.h / 2)
            break
    assert gui.ran, "no command reached the sink"
    assert gui.ran[-1].endswith("148l"), gui.ran[-1]


def test_the_target_is_quoted_when_it_needs_to_be():
    """An EMDB map is called `EMD-3061`, which the selection grammar splits."""
    from chisurf.plugins.chimol.chimol.object_menus import quote_selection_name

    ran: list[str] = []
    panel = InternalGui(run_command=ran.append)
    panel.layout(*SIZE)
    panel.open_context_menu(200, 200, quote_selection_name("EMD-3061"))
    menu = panel._menus[-1]
    action = next(r for r, e in menu.item_rects if e is not None and e.label == "Action")
    panel.mouse_move(action.x + 8, action.y + action.h / 2)
    child = panel._menus[-1]
    rect, _entry = child.item_rects[0]
    panel.mouse_press(rect.x + 6, rect.y + rect.h / 2)
    assert ran and '"EMD-3061"' in ran[-1], ran[-1]
