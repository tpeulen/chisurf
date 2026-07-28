"""The object panel drawn inside the viewport: layout, hits, and commands.

None of this needs a GL context or a window. Layout and hit-testing are
arithmetic over rectangles, and every click is turned into a *command string*
rather than a direct call -- so what the panel does can be asserted exactly, and
nothing can be done by clicking that could not be scripted.
"""
from __future__ import annotations

import pytest

from chisurf.plugins.chimol.chimol.object_menus import OBJECT_MENUS
from chisurf.plugins.chimol.chimol.renderer.internal_gui import GuiRow, InternalGui

WIDTH, HEIGHT = 900, 600


@pytest.fixture
def gui():
    """Return a panel over three rows, laid out for a 900x600 viewport."""
    commands: list[str] = []
    panel = InternalGui(run_command=commands.append)
    panel.commands = commands            # for the tests to read
    panel.set_rows([
        GuiRow(name="all", is_header=True),
        GuiRow(name="148l", enabled=True),
        GuiRow(name="lig", enabled=False),
    ])
    panel.layout(WIDTH, HEIGHT)
    return panel


def _centre(rect):
    return rect.x + rect.w / 2, rect.y + rect.h / 2


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
def test_the_panel_sits_inside_the_viewport(gui):
    """Anchored top-right, and never off the edge of the window it draws in."""
    panel = gui.panel_rect
    assert panel.x >= 0 and panel.y >= 0
    assert panel.x + panel.w <= WIDTH
    assert panel.y + panel.h <= HEIGHT


def test_every_row_carries_the_five_menus(gui):
    for row_buttons in gui._button_rects:
        assert set(row_buttons) == {key for key, _title, _entries in OBJECT_MENUS}


def test_the_buttons_are_flush(gui):
    """Zero spacing, which is the whole reason this moved into the viewport.

    Adjacent boxes share an edge exactly: no layout is negotiating here, so the
    gap is whatever the arithmetic says, and the arithmetic says none.
    """
    for row_buttons in gui._button_rects:
        ordered = [row_buttons[key] for key, _t, _e in OBJECT_MENUS]
        for left, right in zip(ordered, ordered[1:]):
            assert right.x == pytest.approx(left.x + left.w)


def test_the_rows_line_up_in_a_column(gui):
    """Every row puts its buttons in the same place.

    A group row and a molecule row drifting apart is what makes a panel hard to
    read at a glance.
    """
    xs = {tuple(round(r[key].x, 3) for key, _t, _e in OBJECT_MENUS) for r in gui._button_rects}
    assert len(xs) == 1


# --------------------------------------------------------------------------- #
# Hit testing
# --------------------------------------------------------------------------- #
def test_a_click_on_a_button_finds_that_button(gui):
    rect = gui._button_rects[1]["S"]
    hit = gui.hit_test(*_centre(rect))
    assert (hit.kind, hit.row, hit.key) == ("button", 1, "S")


def test_a_click_on_the_name_finds_the_row(gui):
    rect = gui._row_rects[2]
    hit = gui.hit_test(rect.x + 4, rect.y + rect.h / 2)
    assert (hit.kind, hit.row) == ("name", 2)


def test_the_scene_keeps_clicks_that_miss_the_panel(gui):
    """Otherwise the panel would swallow the camera's own drags."""
    assert gui.hit_test(10, HEIGHT - 10).kind == ""
    assert gui.wants(10, HEIGHT - 10) is False


def test_the_panel_takes_clicks_that_land_on_it(gui):
    """A press that opens a menu must not also start rotating the molecule."""
    assert gui.wants(*_centre(gui._button_rects[1]["A"])) is True


# --------------------------------------------------------------------------- #
# What a click does
# --------------------------------------------------------------------------- #
def test_clicking_a_name_toggles_that_object(gui):
    gui.mouse_press(gui._row_rects[1].x + 4, gui._row_rects[1].y + 4)
    assert gui.commands == ["disable 148l"]

    gui.mouse_press(gui._row_rects[2].x + 4, gui._row_rects[2].y + 4)
    assert gui.commands[-1] == "enable lig"


def test_clicking_a_button_opens_its_menu(gui):
    gui.mouse_press(*_centre(gui._button_rects[1]["H"]))
    assert gui.has_menu() is True
    assert gui.commands == [], "opening a menu must not run anything"


def test_right_clicking_a_name_opens_the_action_menu(gui):
    """PyMOL's right-click on an object name is its A menu."""
    gui.mouse_press(gui._row_rects[1].x + 4, gui._row_rects[1].y + 4, right=True)
    assert gui.has_menu() is True
    assert gui.commands == []


def test_choosing_an_entry_runs_it_against_that_object(gui):
    """`{sele}` binds to the row the menu was opened on, not to a selection."""
    gui.mouse_press(*_centre(gui._button_rects[2]["A"]))     # the "lig" row
    entry_rect, entry = next(
        (r, e) for r, e in gui._menus[-1].item_rects if e.command
    )
    gui.mouse_press(*_centre(entry_rect))

    assert gui.commands, "nothing ran"
    assert "lig" in gui.commands[-1]
    assert "{sele}" not in gui.commands[-1]
    assert gui.has_menu() is False, "the menu should close once an entry is chosen"


def test_an_unimplemented_entry_does_nothing_and_stays_open(gui):
    """Shown, disabled, and honest about it -- clicking it must not guess."""
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    disabled = next(
        (r, e) for r, e in gui._menus[-1].item_rects
        if e.command is None and not e.is_submenu
    )
    gui.mouse_press(*_centre(disabled[0]))
    assert gui.commands == []


def test_clicking_away_closes_the_menu(gui):
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    consumed = gui.mouse_press(20, HEIGHT - 20)
    assert gui.has_menu() is False
    assert consumed is True, "the click that dismisses a menu is not also a scene click"


def test_a_submenu_opens_beside_its_parent(gui):
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    parent = gui._menus[-1]
    rect, entry = next((r, e) for r, e in parent.item_rects if e.is_submenu)

    gui.mouse_press(*_centre(rect))

    assert len(gui._menus) == 2
    assert gui._menus[-1].title == entry.label
    assert gui.commands == []


# --------------------------------------------------------------------------- #
# Long menus
# --------------------------------------------------------------------------- #
def test_a_long_menu_stays_inside_the_viewport(gui):
    """Entries that run off the bottom are unreachable, and nothing says so.

    PyMOL's Action menu is two dozen entries; in a viewport sharing its height
    with a sequence strip and a console it does not fit in one column.
    """
    gui.layout(WIDTH, 300)
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    menu = gui._menus[-1]

    assert menu.rect.y >= 0
    assert menu.rect.y + menu.rect.h <= 300 + 1e-6
    for rect, _entry in menu.item_rects:
        assert rect.y >= 0
        assert rect.y + rect.h <= 300 + 1e-6


def test_every_entry_of_a_wrapped_menu_can_still_be_clicked(gui):
    """Wrapping is only worth doing if the hit rectangles wrap with it."""
    gui.layout(WIDTH, 300)
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    menu = gui._menus[-1]

    clickable = [e for e in menu.entries if not e.is_separator]
    assert len(menu.item_rects) == len(clickable), "entries were dropped, not wrapped"
    for rect, entry in menu.item_rects:
        assert gui.hit_test(*_centre(rect)).entry is entry
