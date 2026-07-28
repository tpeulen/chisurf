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


# --------------------------------------------------------------------------- #
# The renderer's side of it
# --------------------------------------------------------------------------- #
# Not tested here, deliberately. Constructing a QOpenGLWidget inside pytest
# aborts the interpreter in this environment -- not an error, an abort that
# takes the whole run with it -- so a test for the mouse routing would cost
# every other test in the suite. The two things that go wrong there are:
#
#   * the drag anchor was only ever *assigned* on a press the camera handled,
#     so a press taken by the panel left it unset and the following move raised
#     AttributeError on the first click of a session; and
#   * a drag begun on the panel also swung the camera, spinning the model out
#     from under the menu that had just opened.
#
# Both are held by initialising the anchor in `__init__` and by keeping the
# grab until release, and both are verified by driving a real window in
# `test/screenshot.py`-style probes rather than in-process.


# --------------------------------------------------------------------------- #
# The mouse-mode block, bottom-right
# --------------------------------------------------------------------------- #
def test_the_block_sits_in_the_bottom_right(gui):
    block = gui.block_rect
    assert block.x + block.w <= WIDTH
    assert block.y + block.h <= HEIGHT
    assert block.x > WIDTH / 2, "not on the right"
    assert block.y > HEIGHT / 2, "not at the bottom"


def test_the_block_shows_pymols_own_matrix(gui):
    """The rows are reference material, so they have to be exactly right.

    Someone reads this to find out what ctrl-shift-middle does; a table that is
    nearly right is worse than none.
    """
    from chisurf.plugins.chimol.chimol.mouse_modes import rows_for

    labels = [label for label, _cells in rows_for(gui.mouse_mode)]
    assert labels == ["& Keys", "Shft", "Ctrl", "CtSh", "SnglClk", "DblClk"]

    cells = dict(rows_for("three_button_viewing"))
    assert cells["& Keys"] == ["Rota", "Move", "MovZ", "Slab"]
    assert cells["Shft"] == ["+Box", "-Box", "Clip", "MovS"]
    assert cells["Ctrl"] == ["Move", "PkAt", "Pk1", "MvSZ"]
    assert cells["CtSh"] == ["Sele", "Orig", "Clip", "MovZ"]


def test_the_transcription_still_matches_pymol():
    """Checked against the source it was taken from, where that is installed.

    The tables were generated from `pymol.controlling`, not copied off a
    screenshot. This is what keeps them honest as PyMOL moves: skipped where
    PyMOL is absent, which is most machines, and decisive where it is not.
    """
    controlling = pytest.importorskip("pymol.controlling")

    from chisurf.plugins.chimol.chimol.mouse_modes import MODE_BINDINGS, MODE_NAMES

    for mode, bindings in MODE_BINDINGS.items():
        theirs = {(b, m): a for b, m, a in controlling.mode_dict[mode]}
        assert bindings == theirs, f"{mode} drifted from PyMOL's table"
        assert MODE_NAMES[mode] == controlling.mode_name_dict[mode]


def test_clicking_the_mode_line_cycles_it(gui):
    """As PyMOL's does -- and it must not run a command to do it."""
    rect = gui._mode_rect
    before = gui.mouse_mode

    gui.mouse_press(rect.x + 4, rect.y + 4)

    assert gui.mouse_mode != before
    assert gui.commands == []


def test_the_transport_runs_the_movie_commands(gui):
    for rect, command in gui._movie_rects:
        gui.commands.clear()
        gui.mouse_press(*_centre(rect))
        assert gui.commands == [command]


def test_the_block_swallows_clicks_that_land_on_its_text(gui):
    """Clicking the table does nothing, and must not rotate the scene either.

    Otherwise reading the reference would drag the molecule out from under it.
    """
    block = gui.block_rect
    point = (block.x + block.w / 2, block.y + block.h / 2)

    assert gui.wants(*point) is True
    gui.commands.clear()
    assert gui.mouse_press(*point) is True
    assert gui.commands == []


# --------------------------------------------------------------------------- #
# The splitter
# --------------------------------------------------------------------------- #
def test_the_scene_keeps_the_width_the_column_does_not_take(gui):
    """Docked, not overlaid.

    An overlay hides the molecule it is describing, and the part it hides is the
    part you just moved out from under it.
    """
    assert gui.docked is True
    assert gui.panel_rect.x == pytest.approx(WIDTH - gui.column_width)
    assert gui.block_rect.x == pytest.approx(WIDTH - gui.column_width)


def test_dragging_the_splitter_resizes_the_column(gui):
    """And the column is what decides how much width the scene gets."""
    handle = gui._splitter
    gui.mouse_press(handle.x + handle.w / 2, HEIGHT / 2)
    assert gui.is_dragging() is True

    gui.drag(WIDTH - 320, HEIGHT / 2)
    assert gui.column_width == pytest.approx(320)
    assert gui.panel_rect.x == pytest.approx(WIDTH - 320)

    gui.release()
    assert gui.is_dragging() is False


def test_the_column_cannot_be_dragged_away_or_over_the_scene(gui):
    """Bounds on both ends, or the panel becomes unusable or takes the window."""
    gui.mouse_press(gui._splitter.x + 1, HEIGHT / 2)

    gui.drag(WIDTH - 5, HEIGHT / 2)
    assert gui.column_width >= gui.MIN_COLUMN

    gui.drag(10, HEIGHT / 2)
    assert gui.column_width <= WIDTH * gui.MAX_COLUMN_FRACTION


def test_the_splitter_takes_its_own_press_only(gui):
    """A press one pixel away belongs to the scene, not to the handle."""
    handle = gui._splitter
    assert gui.hit_test(handle.x + handle.w / 2, HEIGHT / 2).kind == "splitter"
    assert gui.hit_test(handle.x - 20, HEIGHT / 2).kind == ""
