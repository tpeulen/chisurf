"""The object panel drawn inside the viewport: layout, hits, and commands.

None of this needs a GL context or a window. Layout and hit-testing are
arithmetic over rectangles, and every click is turned into a *command string*
rather than a direct call -- so what the panel does can be asserted exactly, and
nothing can be done by clicking that could not be scripted.
"""

from __future__ import annotations

import pytest
from chimol.ui.gui import GuiRow, InternalGui, char_width
from chimol.ui.menus.objects import OBJECT_MENUS
from qtpy import QtCore

WIDTH, HEIGHT = 900, 600


@pytest.fixture
def gui():
    """Return a panel over three rows, laid out for a 900x600 viewport."""
    commands: list[str] = []
    panel = InternalGui(run_command=commands.append)
    panel.commands = commands  # for the tests to read
    panel.set_rows(
        [
            GuiRow(name="all", is_header=True),
            GuiRow(name="148l", enabled=True),
            GuiRow(name="lig", enabled=False),
        ]
    )
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
    """Otherwise the panel would swallow the camera's own drags.

    Sampled in the middle of the scene. The bottom-left corner this used to
    test is the command line's now -- see the test below, which pins that
    deliberately rather than leaving it as a corner nobody checks.
    """
    assert gui.hit_test(10, HEIGHT // 2).kind == ""
    assert gui.wants(10, HEIGHT // 2) is False


def test_the_command_line_owns_the_bottom_of_the_scene(gui):
    """One row along the bottom is the in-viewport prompt, and takes clicks."""
    assert gui.hit_test(10, HEIGHT - 10).kind == "command"
    gui.command_line.visible = False
    gui.layout(WIDTH, HEIGHT)
    assert gui.hit_test(10, HEIGHT - 10).kind == "", (
        "with the prompt off the scene gets its corner back"
    )


def test_the_panel_takes_clicks_that_land_on_it(gui):
    """A press that opens a menu must not also start rotating the molecule."""
    assert gui.wants(*_centre(gui._button_rects[1]["A"])) is True


# --------------------------------------------------------------------------- #
# What a click does
# --------------------------------------------------------------------------- #
def test_the_eye_toggles_and_the_name_activates(gui):
    """Visibility moved onto the eye: clicking a name used to disable the
    object the user was trying to make active.
    """
    gui.mouse_press(*_centre(gui._eye_rects[1]))
    assert gui.commands == ["disable 148l"]

    gui.mouse_press(*_centre(gui._eye_rects[2]))
    assert gui.commands[-1] == "enable lig"

    gui.mouse_press(gui._row_rects[1].x + gui.BUTTON_W + gui.PAD + 4, gui._row_rects[1].y + 4)
    assert gui.commands[-1] == "activate 148l"


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
    gui.mouse_press(*_centre(gui._button_rects[2]["A"]))  # the "lig" row
    entry_rect, entry = next((r, e) for r, e in gui._menus[-1].item_rects if e.command)
    gui.mouse_press(*_centre(entry_rect))

    assert gui.commands, "nothing ran"
    assert "lig" in gui.commands[-1]
    assert "{sele}" not in gui.commands[-1]
    assert gui.has_menu() is False, "the menu should close once an entry is chosen"


def test_an_unimplemented_entry_does_nothing_and_stays_open(gui):
    """Shown, disabled, and honest about it -- clicking it must not guess."""
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    disabled = next(
        (r, e) for r, e in gui._menus[-1].item_rects if e.command is None and not e.is_submenu
    )
    gui.mouse_press(*_centre(disabled[0]))
    assert gui.commands == []


def test_refreshing_the_same_rows_keeps_the_menu(gui):
    """A host that re-feeds an unchanged object list must not lose the menu.

    Hosts refresh the panel on all sorts of occasions -- an object-list
    revision, once even on every pointer release -- and ``set_rows`` used
    to dismiss the menus unconditionally, so the click that opened a menu
    was also the click that closed it. Same rows: no change, menu stays.
    Different rows: the menu's target may be gone, so it goes.
    """
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    assert gui.has_menu() is True
    gui.set_rows(list(gui.rows))
    assert gui.has_menu() is True, "an unchanged list closed the menu"
    gui.set_rows(gui.rows[:2])
    assert gui.has_menu() is False, "a changed list must dismiss the menu"


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
# Submenus: where they go, and when they go away
# --------------------------------------------------------------------------- #
def _overlap(a, b) -> bool:
    """Whether two rectangles share any area."""
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def _first_submenu(menu):
    """The first row of *menu* that opens a submenu, and its rectangle."""
    return next((r, e) for r, e in menu.item_rects if e.is_submenu)


def test_a_submenu_never_covers_the_menu_it_came_from(gui):
    """It did, which is what made the C menu unreadable.

    The panel is docked against the right edge of the viewport, so a submenu
    placed to the right of its parent does not fit -- and the layout *clamped*
    it back on screen instead of flipping it, which put it squarely on top of
    the entries either side of the one being hovered.
    """
    gui.mouse_press(*_centre(gui._button_rects[1]["C"]))
    parent = gui._menus[-1]
    rect, entry = _first_submenu(parent)

    gui.mouse_move(*_centre(rect))

    child = gui._menus[-1]
    assert child.owner is entry
    assert not _overlap(parent.rect, child.rect), "the submenu is on its parent"
    assert child.rect.x >= 0
    assert child.rect.x + child.rect.w <= WIDTH + 1e-6
    assert child.affinity == -1, "against the right edge it has to open left"


def test_a_submenu_opens_to_the_right_when_there_is_room(gui):
    """PyMOL's preferred side, and the one a chain keeps until it must flip."""
    from chimol.ui.menus.objects import COLOR_MENU

    gui._open_menu("Color:", "148l", COLOR_MENU, 40.0, 40.0)
    parent = gui._menus[-1]
    rect, _entry = _first_submenu(parent)

    gui.mouse_move(*_centre(rect))

    child = gui._menus[-1]
    assert child.rect.x >= parent.rect.x + parent.rect.w
    assert child.affinity == 1
    assert not _overlap(parent.rect, child.rect)


def test_a_grandchild_keeps_the_side_its_parent_flipped_to(gui):
    """PyMOL's ``PlacementAffinity``: a chain that went left stays left.

    Without it a deep chain zig-zags -- each level flips back across the menu it
    came from as soon as it happens to fit there.
    """
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    rect, entry = next((r, e) for r, e in gui._menus[-1].item_rects if e.label == "find")
    gui.mouse_move(*_centre(rect))
    child = gui._menus[-1]
    assert child.affinity == -1

    grand_rect, _grand = _first_submenu(child)
    gui.mouse_move(*_centre(grand_rect))

    grandchild = gui._menus[-1]
    assert grandchild.affinity == -1
    assert not _overlap(child.rect, grandchild.rect)


def test_moving_to_another_row_collapses_the_submenu(gui):
    """PyMOL's ``PopUp`` frees the child the moment the cursor leaves its row.

    Ours only ever opened them, so every submenu the cursor passed over stayed
    on screen and the menu became a stack of boxes.
    """
    gui.mouse_press(*_centre(gui._button_rects[1]["C"]))
    parent = gui._menus[-1]
    rect, _entry = _first_submenu(parent)
    gui.mouse_move(*_centre(rect))
    assert len(gui._menus) == 2

    plain = next(r for r, e in parent.item_rects if not e.is_submenu and not e.is_separator)
    gui.mouse_move(*_centre(plain))

    assert len(gui._menus) == 1


def test_hovering_a_second_submenu_replaces_the_first(gui):
    gui.mouse_press(*_centre(gui._button_rects[1]["C"]))
    parent = gui._menus[-1]
    submenus = [(r, e) for r, e in parent.item_rects if e.is_submenu]
    gui.mouse_move(*_centre(submenus[0][0]))
    gui.mouse_move(*_centre(submenus[1][0]))

    assert len(gui._menus) == 2
    assert gui._menus[-1].owner is submenus[1][1]


def test_the_submenu_stays_while_the_cursor_is_inside_it(gui):
    """Otherwise it could not be used: crossing the gap would close it.

    Rows that *are* submenus are skipped, because opening a child is exactly
    what hovering one is supposed to do. That distinction only started to
    matter once **C ▸ by element** grew PyMOL's real contents -- one leaf became
    a CNOS entry, eight carbon colours and four further sets -- so a walk down
    the column now passes over rows that legitimately open something.
    """
    gui.mouse_press(*_centre(gui._button_rects[1]["C"]))
    rect, _entry = _first_submenu(gui._menus[-1])
    gui.mouse_move(*_centre(rect))
    child = gui._menus[-1]

    walked = 0
    for item_rect, entry in child.item_rects:
        if entry is not None and entry.children:
            continue
        gui.mouse_move(*_centre(item_rect))
        walked += 1
        assert gui._menus[-1] is child
    assert walked, "every row opened a submenu; nothing was actually tested"


def test_leaving_the_menus_collapses_the_branch_but_keeps_the_menu(gui):
    """A click dismisses the menu, as in PyMOL; the cursor drifting off does not.

    What the cursor leaving *does* close is the branch it walked into, which is
    the half that was missing.
    """
    gui.mouse_press(*_centre(gui._button_rects[1]["C"]))
    rect, _entry = _first_submenu(gui._menus[-1])
    gui.mouse_move(*_centre(rect))
    assert len(gui._menus) == 2

    gui.mouse_move(20, HEIGHT - 20)

    assert len(gui._menus) == 1, "the submenu outlived the cursor"
    assert gui.has_menu() is True


def test_two_submenus_sharing_a_label_are_told_apart(gui):
    """`by element` opens a menu whose only entry is also called `by element`.

    The open-submenu guard used to match on the *label*, so hovering the second
    one found the first still open and left it there.
    """
    gui.mouse_press(*_centre(gui._button_rects[1]["C"]))
    parent = gui._menus[-1]
    rect, entry = next((r, e) for r, e in parent.item_rects if e.label == "by element")
    gui.mouse_move(*_centre(rect))

    child = gui._menus[-1]
    assert child.owner is entry
    assert child.parent is parent


# --------------------------------------------------------------------------- #
# Long menus
# --------------------------------------------------------------------------- #
def test_a_long_menu_stays_inside_the_viewport(gui):
    """The menu itself is never off the window, however many entries it has."""
    gui.layout(WIDTH, 200)
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    menu = gui._menus[-1]

    assert menu.rect.y >= 0
    assert menu.rect.y + menu.rect.h <= 200 + 1e-6
    assert menu.max_scroll > 0, "this menu is meant to be taller than the window"


def test_a_long_menu_keeps_one_column(gui):
    """It used to wrap, and the wrap is what the arrangement complaint was.

    A second column starts wherever the window height happens to put it, so a
    menu's *grouping* -- which is most of what its order says -- is broken at
    an arbitrary place, and the separators were being dropped to keep the two
    columns aligned. PyMOL never wraps: one column, and the pop-up scrolls.
    """
    gui.layout(WIDTH, 200)
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    menu = gui._menus[-1]

    xs = {round(rect.x, 3) for rect, _e in menu.item_rects}
    assert len(xs) == 1, "the menu grew a second column"
    ordered = [rect.y for rect, _e in menu.item_rects]
    assert ordered == sorted(ordered), "the entries are no longer in order"
    gaps = {round(b - a, 3) for a, b in zip(ordered, ordered[1:])}
    assert gaps - {float(gui.MENU_ITEM_H)}, (
        "no gap anywhere: the separators stopped costing height, and the "
        "groups they mark are what the order is saying"
    )


def test_every_entry_of_a_long_menu_can_be_reached_by_scrolling(gui):
    """Scrolling is only worth doing if the hit rectangles scroll with it."""
    gui.layout(WIDTH, 200)
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    menu = gui._menus[-1]
    inside = _centre(menu.rect)

    clickable = [e for e in menu.entries if not e.is_separator]
    assert len(menu.item_rects) == len(clickable), "entries were dropped"

    reached = set()
    for _ in range(60):
        for rect, entry in menu.item_rects:
            if gui.hit_test(*_centre(rect)).entry is entry:
                reached.add(entry.label)
        if not gui.scroll_menu(inside[0], inside[1], -1):
            break
    assert {e.label for e in clickable} <= reached, (
        f"entries below the fold could not be reached: { {e.label for e in clickable} - reached }"
    )


def test_a_scrolled_out_row_does_not_take_the_click(gui):
    """Its rectangle is still in the list; the visibility test is the guard."""
    gui.layout(WIDTH, 200)
    gui.mouse_press(*_centre(gui._button_rects[1]["A"]))
    menu = gui._menus[-1]
    inside = _centre(menu.rect)
    gui.scroll_menu(inside[0], inside[1], -3)

    for rect, entry in menu.item_rects:
        if rect.y + rect.h <= menu.rect.y or rect.y >= menu.rect.y + menu.rect.h:
            assert gui.hit_test(*_centre(rect)).entry is not entry


def test_a_menu_that_fits_does_not_scroll(gui):
    gui.mouse_press(*_centre(gui._button_rects[1]["C"]))
    menu = gui._menus[-1]
    assert menu.max_scroll == 0
    assert gui.scroll_menu(*_centre(menu.rect), -1) is False


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
    from chimol.ui.input.mouse_modes import rows_for

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

    from chimol.ui.input.mouse_modes import MODE_BINDINGS, MODE_NAMES

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
def _docked(gui):
    """Opt a panel into the docked column, the pre-window layout."""
    gui.docked = True
    gui.layout(WIDTH, HEIGHT)
    return gui


def test_the_scene_keeps_the_width_the_column_does_not_take(gui):
    """Docked, not overlaid -- the column layout, now opt-in.

    The default became floating windows (the object list and mouse block are
    draggable, closable and remembered), but the docked column remains and
    keeps its contract.
    """
    gui = _docked(gui)
    assert gui.docked is True
    assert gui.panel_rect.x == pytest.approx(WIDTH - gui.column_width)
    assert gui.block_rect.x == pytest.approx(WIDTH - gui.column_width)


def test_dragging_the_splitter_resizes_the_column(gui):
    gui = _docked(gui)
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
    gui = _docked(gui)
    """Bounds on both ends, or the panel becomes unusable or takes the window."""
    gui.mouse_press(gui._splitter.x + 1, HEIGHT / 2)

    gui.drag(WIDTH - 5, HEIGHT / 2)
    assert gui.column_width >= gui.minimum_column_width()

    gui.drag(10, HEIGHT / 2)
    assert gui.column_width <= WIDTH * gui.MAX_COLUMN_FRACTION


def test_the_floor_is_what_the_control_actually_needs(gui):
    """Measured from the contents, not a constant.

    A fixed floor either cuts off the widest thing in the column -- the object
    rows, the mouse-mode table or the nine transport buttons -- or stops the
    splitter well before it had to.
    """
    floor = gui.minimum_column_width()

    rows_need = gui.PAD + gui._name_width + gui.PAD + gui.BUTTON_W * len(OBJECT_MENUS) + gui.PAD
    transport_need = 2 * gui.PAD + gui.MIN_BUTTON_W * 9

    assert floor >= rows_need
    assert floor >= transport_need


def test_a_wider_name_pushes_the_floor_out(gui):
    """The floor follows the contents rather than being decided once."""
    before = gui.minimum_column_width()
    gui.layout(WIDTH, HEIGHT, name_width=gui._name_width + 80)
    assert gui.minimum_column_width() > before


def test_the_clamp_survives_a_window_narrower_than_the_floor(gui):
    """On a window too small for the panel the bounds cross over.

    Clamping to `min(max(x, floor), 0.6 * width)` inverts when the ceiling falls
    below the floor, and the column snaps to the *widest* it may be -- the
    opposite of respecting a minimum.
    """
    gui = _docked(gui)
    gui.layout(200, HEIGHT)
    gui.mouse_press(gui._splitter.x + 1, HEIGHT / 2)
    gui.drag(190, HEIGHT / 2)

    assert gui.column_width >= gui.minimum_column_width()


def test_the_splitter_takes_its_own_press_only(gui):
    gui = _docked(gui)
    """A press one pixel away belongs to the scene, not to the handle."""
    handle = gui._splitter
    assert gui.hit_test(handle.x + handle.w / 2, HEIGHT / 2).kind == "splitter"
    assert gui.hit_test(handle.x - 20, HEIGHT / 2).kind == ""


# --------------------------------------------------------------------------- #
# The sequence strip
# --------------------------------------------------------------------------- #
@pytest.fixture
def sequences(gui):
    """Return the panel with two sequences shown."""
    from chimol.ui.gui import SequenceRow

    gui.sequence_visible = True
    gui.set_sequences(
        [
            SequenceRow(name="148l", codes="MNIFEMLRIDEGLRLKIYKD", numbers=list(range(1, 21))),
            SequenceRow(name="pep", codes="ACDEFGHIK", numbers=list(range(1, 10))),
        ]
    )
    gui.layout(WIDTH, HEIGHT)
    return gui


def test_the_strip_takes_a_band_rather_than_covering_the_scene(sequences):
    """The strip gets a band of its own rather than covering the scene.

    PyMOL's `seq_view_overlay` is off by default for a good reason: a sequence
    drawn over the molecule hides the thing it is indexing.
    """
    assert sequences.sequence_height() > 0
    assert sequences._seq_strip.y == 0, "the strip belongs at the top"
    # Nothing is docked by default any more, so the strip may run the full
    # width; docked, it still stops at the column.
    assert sequences._seq_strip.w <= WIDTH + 1e-6
    sequences.docked = True
    sequences.layout(WIDTH, HEIGHT)
    assert sequences._seq_strip.w <= WIDTH - sequences.column_width + 1e-6


def test_no_sequences_means_no_band(gui):
    """The scene keeps its full height when there is nothing to show."""
    gui.sequence_visible = True
    gui.set_sequences([])
    assert gui.sequence_height() == 0


def test_switching_the_strip_off_gives_the_height_back(sequences):
    sequences.sequence_visible = False
    assert sequences.sequence_height() == 0


def test_clicking_a_residue_selects_it(sequences):
    picked: list[tuple] = []
    sequences.on_select = lambda name, indices, additive: picked.append(
        (name, list(indices), additive)
    )
    row = sequences._seq_rows[0]
    char_w = char_width(sequences.FONT_PT)

    sequences.mouse_press(sequences._seq_origin + char_w * 3.5, row.y + 4)

    assert picked, "nothing was selected"
    name, indices, _additive = picked[-1]
    assert name == "148l"
    assert indices == [3]
    assert sequences.sequences[0].selected == {3}


def test_dragging_selects_a_range(sequences):
    picked: list[list[int]] = []
    sequences.on_select = lambda name, indices, additive: picked.append(list(indices))
    row = sequences._seq_rows[0]
    char_w = char_width(sequences.FONT_PT)

    sequences.mouse_press(sequences._seq_origin + char_w * 2.5, row.y + 4)
    sequences.drag(sequences._seq_origin + char_w * 7.5, row.y + 4)
    sequences.release()

    assert picked[-1] == [2, 3, 4, 5, 6, 7]
    assert sequences.is_dragging() is False


def test_a_drag_does_not_stray_onto_the_other_object(sequences):
    """A range belongs to one sequence.

    An object is not a continuation of the one above it, and joining them would
    select residues nobody pointed at.
    """
    sequences.on_select = lambda *a: None
    first, second = sequences._seq_rows
    char_w = char_width(sequences.FONT_PT)

    sequences.mouse_press(sequences._seq_origin + char_w * 2.5, first.y + 4)
    sequences.drag(sequences._seq_origin + char_w * 5.5, second.y + 4)

    assert sequences.sequences[1].selected == set()


def test_the_strip_takes_its_own_clicks(sequences):
    """Selecting a residue must not also rotate the molecule."""
    row = sequences._seq_rows[0]
    assert sequences.wants(sequences._seq_origin + 4, row.y + 4) is True


def test_clicking_past_the_end_of_a_sequence_selects_nothing(sequences):
    picked: list = []
    sequences.on_select = lambda *a: picked.append(a)
    row = sequences._seq_rows[1]  # the nine-residue one
    char_w = char_width(sequences.FONT_PT)

    sequences.mouse_press(sequences._seq_origin + char_w * 40, row.y + 4)

    assert picked == []


def test_clicking_a_selected_residue_toggles_it_off(sequences):
    """PyMOL's Seeker flips a residue: the same click again deselects it."""
    picked: list[list[int]] = []
    sequences.on_select = lambda name, indices, additive: picked.append(list(indices))
    row = sequences._seq_rows[0]
    char_w = char_width(sequences.FONT_PT)
    x = sequences._seq_origin + char_w * 3.5

    sequences.mouse_press(x, row.y + 4)
    sequences.mouse_press(x, row.y + 4)

    assert picked[-1] == []
    assert sequences.sequences[0].selected == set()


def test_shift_click_extends_the_previous_gesture(sequences):
    """Shift continues the drag gesture from where it left off, additively."""
    picked: list[list[int]] = []
    sequences.on_select = lambda name, indices, additive: picked.append(list(indices))
    row = sequences._seq_rows[0]
    char_w = char_width(sequences.FONT_PT)
    origin = sequences._seq_origin

    sequences.mouse_press(origin + char_w * 2.5, row.y + 4)  # anchor at 2
    sequences.mouse_press(origin + char_w * 7.5, row.y + 4, modifiers=QtCore.Qt.ShiftModifier)

    assert sequences.sequences[0].selected == set(range(2, 8))
    assert picked[-1] == [2, 3, 4, 5, 6, 7]


def test_ctrl_click_toggles_and_keeps_the_rest(sequences):
    """Ctrl is PyMOL's Seeker toggle; it merges, never replaces."""
    picked: list[list[int]] = []
    sequences.on_select = lambda name, indices, additive: picked.append(list(indices))
    row = sequences._seq_rows[0]
    char_w = char_width(sequences.FONT_PT)
    origin = sequences._seq_origin

    sequences.mouse_press(origin + char_w * 2.5, row.y + 4)  # {2}
    sequences.mouse_press(
        origin + char_w * 5.5, row.y + 4, modifiers=QtCore.Qt.ControlModifier
    )  # +{5}

    assert sequences.sequences[0].selected == {2, 5}
    assert picked[-1] == [2, 5]


def test_ctrl_drag_merges_into_the_selection(sequences):
    """A range dragged with ctrl held adds to, rather than replaces, the set."""
    picked: list[list[int]] = []
    sequences.on_select = lambda name, indices, additive: picked.append(list(indices))
    row = sequences._seq_rows[0]
    char_w = char_width(sequences.FONT_PT)
    origin = sequences._seq_origin

    sequences.mouse_press(origin + char_w * 2.5, row.y + 4)  # {2}
    sequences.mouse_press(
        origin + char_w * 4.5, row.y + 4, modifiers=QtCore.Qt.ControlModifier
    )  # {2,4}
    sequences.drag(origin + char_w * 8.5, row.y + 4)

    assert sequences.sequences[0].selected == {2, 4, 5, 6, 7, 8}
    assert picked[-1] == [2, 4, 5, 6, 7, 8]


def test_double_click_on_blank_sequence_area_clears(sequences):
    """PyMOL's Seeker: a double-click on empty sequence space deselects all."""
    sequences.sequences[0].selected = {1, 2, 3}
    x = sequences._seq_strip.x + 4
    y = sequences._seq_strip.y + 2  # the number line, not a residue

    sequences.mouse_press(x, y, double=True)

    assert all(not row.selected for row in sequences.sequences)


# --------------------------------------------------------------------------- #
# The `sele` pseudo-object
# --------------------------------------------------------------------------- #
def _panel_with_sele(commands):
    from chimol.ui.gui import InternalGui

    panel = InternalGui(run_command=commands.append)
    panel.commands = commands
    panel.set_rows(
        [
            GuiRow(name="all", is_header=True),
            GuiRow(name="148l", enabled=True),
            GuiRow(name="sele", enabled=True, is_selection=True),
        ]
    )
    panel.layout(WIDTH, HEIGHT)
    return panel


def test_the_sele_row_is_pinned_last():
    """PyMOL pins its `sele` pseudo-object below every real object and header."""
    panel = _panel_with_sele([])

    assert panel.rows[-1].name == "sele"
    assert panel.rows[-1].is_selection is True


def test_the_sele_row_has_no_on_off_state():
    """`sele` is a selection, not a molecule: its name click does nothing."""
    commands: list[str] = []
    panel = _panel_with_sele(commands)
    sele_row = len(panel.rows) - 1

    panel.mouse_press(panel._row_rects[sele_row].x + 4, panel._row_rects[sele_row].y + 4)

    assert commands == []


def test_the_sele_row_buttons_address_the_selection():
    """The sele row's A/S/H/L/C menus run against ``sele``, like PyMOL's."""
    commands: list[str] = []
    panel = _panel_with_sele(commands)
    sele_row = len(panel.rows) - 1

    panel.mouse_press(*_centre(panel._button_rects[sele_row]["A"]))
    entry_rect, entry = next(
        (r, e) for r, e in panel._menus[-1].item_rects if e.command and "{sele}" in e.command
    )
    panel.mouse_press(*_centre(entry_rect))

    assert commands, "nothing ran"
    assert "{sele}" not in commands[-1]
    assert "sele" in commands[-1]


# --------------------------------------------------------------------------- #
# Scrolling a long sequence
# --------------------------------------------------------------------------- #
@pytest.fixture
def long_sequence(gui):
    """Return the panel with a sequence far longer than the strip."""
    from chimol.ui.gui import SequenceRow

    gui.sequence_visible = True
    gui.set_sequences(
        [SequenceRow(name="148l", codes="ACDEFGHIKLMNPQRSTVWY" * 20, numbers=list(range(1, 401)))]
    )
    gui.layout(WIDTH, HEIGHT)
    return gui


def test_a_long_sequence_can_be_scrolled(long_sequence):
    """A sequence wider than the strip must be reachable.

    Otherwise it just ends at the edge of the window with nothing to say there
    is more of it.
    """
    assert long_sequence.max_scroll() > 0

    moved = long_sequence.scroll_sequence(10)
    assert moved is True
    assert long_sequence._seq_scroll == 10


def test_scrolling_stops_at_both_ends(long_sequence):
    long_sequence.scroll_sequence(-100)
    assert long_sequence._seq_scroll == 0

    long_sequence.scroll_sequence(10_000)
    assert long_sequence._seq_scroll == long_sequence.max_scroll()


def test_a_sequence_that_fits_does_not_scroll(sequences):
    assert sequences.max_scroll() == 0
    assert sequences.scroll_sequence(5) is False


def test_dragging_the_scrollbar_scrolls(long_sequence):
    track = long_sequence._seq_track
    long_sequence.mouse_press(track.x + track.w * 0.5, track.y + 2)
    assert long_sequence._seq_scroll == pytest.approx(long_sequence.max_scroll() // 2, abs=1)

    long_sequence.drag(track.x + track.w, track.y + 2)
    assert long_sequence._seq_scroll == long_sequence.max_scroll()
    long_sequence.release()


def test_the_thumb_shows_how_much_is_off_screen(long_sequence):
    """A full-width thumb would say the whole sequence is visible."""
    assert long_sequence._seq_thumb.w < long_sequence._seq_track.w


def test_a_scrolled_click_selects_the_residue_under_the_cursor(long_sequence):
    """The column under the cursor is an offset into the *scrolled* sequence.

    Getting this wrong selects a residue some fixed distance from the one that
    was clicked, which looks like the selection being off by a random amount.
    """
    picked: list[list[int]] = []
    long_sequence.on_select = lambda name, indices, additive: picked.append(list(indices))
    long_sequence.scroll_sequence(30)
    row = long_sequence._seq_rows[0]
    char_w = char_width(long_sequence.FONT_PT)

    long_sequence.mouse_press(long_sequence._seq_origin + char_w * 2.5, row.y + 4)

    assert picked[-1] == [32]


def test_clearing_drops_every_highlight(sequences):
    sequences.sequences[0].selected = {1, 2, 3}
    sequences.clear_selection()
    assert all(not row.selected for row in sequences.sequences)


def test_the_letters_take_the_structures_colours(sequences):
    """The letters follow the structure's own colours.

    A sequence in one flat colour says nothing about a molecule coloured by
    chain or by spectrum.
    """
    from chimol.ui.gui import _residue_color

    row = sequences.sequences[0]
    row.colors = [(1.0, 0.0, 0.0)] * len(row.codes)
    assert _residue_color(row, 0) == (255, 0, 0)

    row.colors = []
    assert _residue_color(row, 0) != (255, 0, 0), "should fall back, not crash"


# --------------------------------------------------------------------------- #
# Mouse-mode rings, stride and averaging
# --------------------------------------------------------------------------- #
def test_the_mode_line_cycles_within_pymols_ring(gui):
    """Not through every mode it knows.

    A viewing ring steps viewing -> editing -> viewing and never lands on the
    lights or maestro modes, which is the point of having a ring: cycling all
    ten walks someone through modes they did not choose.
    """
    from chimol.ui.input.mouse_modes import MODE_RINGS

    ring = MODE_RINGS[gui.mouse_ring]
    seen = []
    for _ in range(len(ring) + 1):
        gui.cycle_mouse_mode()
        seen.append(gui.mouse_mode)

    assert set(seen) <= set(ring), f"cycled outside the ring: {set(seen) - set(ring)}"
    assert seen[len(ring)] == seen[0], "the ring did not wrap round"


def test_the_ring_matches_pymols():
    """Checked against the source it came from, where PyMOL is installed."""
    controlling = pytest.importorskip("pymol.controlling")

    from chimol.ui.input.mouse_modes import MODE_RINGS

    for name, modes in MODE_RINGS.items():
        assert list(modes) == list(controlling.ring_dict[name]), f"{name} drifted"


def test_stride_and_averaging_are_clickable(gui):
    """PyMOL has neither, and a long or noisy trajectory needs both."""
    applied: list[tuple[int, int]] = []
    gui.on_playback_change = lambda stride, average: applied.append((stride, average))

    gui.mouse_press(*_centre(gui._stride_rect))
    assert gui.stride == 2
    gui.mouse_press(*_centre(gui._average_rect))
    assert gui.average == 1
    assert applied == [(2, 0), (2, 1)]


def test_right_clicking_steps_them_back(gui):
    """A value overshot is one click away, not a trip round the whole cycle."""
    gui.on_playback_change = lambda *a: None
    gui.stride, gui.average = 4, 3

    gui.mouse_press(*_centre(gui._stride_rect), right=True)
    gui.mouse_press(*_centre(gui._average_rect), right=True)

    assert (gui.stride, gui.average) == (3, 2)


def test_neither_goes_below_its_floor(gui):
    """A stride of zero would advance nothing; a negative window is meaningless."""
    gui.on_playback_change = lambda *a: None
    for _ in range(5):
        gui.mouse_press(*_centre(gui._stride_rect), right=True)
        gui.mouse_press(*_centre(gui._average_rect), right=True)

    assert gui.stride == 1
    assert gui.average == 0


# --------------------------------------------------------------------------- #
# The timeline, and staying on screen
# --------------------------------------------------------------------------- #
def test_the_timeline_thumb_follows_the_state(gui):
    gui.state = (1, 10)
    gui.layout(WIDTH, HEIGHT)
    at_start = gui._timeline_thumb.x

    gui.state = (10, 10)
    gui.layout(WIDTH, HEIGHT)
    assert gui._timeline_thumb.x > at_start
    assert (
        gui._timeline_thumb.x + gui._timeline_thumb.w
        <= gui._timeline_track.x + gui._timeline_track.w + 1e-6
    )


def test_dragging_the_timeline_seeks(gui):
    """Dragging the timeline jumps to that frame.

    Stepping frame by frame through a long trajectory is not a way to get
    somewhere: the counter says where you are, this is how you move.
    """
    seen: list[int] = []
    gui.on_frame_change = seen.append
    gui.state = (1, 100)
    gui.layout(WIDTH, HEIGHT)

    track = gui._timeline_track
    gui.mouse_press(track.x + track.w / 2, track.y + 2)
    assert seen and abs(seen[-1] - 50) <= 2

    gui.drag(track.x + track.w, track.y + 2)
    assert seen[-1] == 100
    gui.release()
    assert gui.is_dragging() is False


def test_a_single_frame_movie_does_not_divide_by_zero(gui):
    """One frame is not a movie, so there is no timeline to place.

    This used to assert the thumb had a width -- the span-1 case the division
    guard exists for. PyMOL gives the movie panel zero height until a movie
    exists (``MovieGetPanelHeight``), so the guard is now unreachable from here
    and the assertion is that nothing is laid out rather than that something is.
    """
    gui.state = (1, 1)
    gui.layout(WIDTH, HEIGHT)  # must not raise
    assert gui._timeline_thumb.w == 0
    assert gui._movie_rects == []


def test_the_timeline_tracks_a_frame_change_it_did_not_make(gui):
    """Playback moves the frame on a timer, not through this panel.

    A slider wired only to its own clicks sits still while the molecule moves,
    which is worse than having no slider: it says the movie is at frame one
    while frame forty is on screen.
    """
    gui.state = (1, 50)
    gui.layout(WIDTH, HEIGHT)
    start = gui._timeline_thumb.x

    gui.state = (40, 50)  # as playback would leave it
    gui.layout(WIDTH, HEIGHT)

    assert gui._timeline_thumb.x > start


# --------------------------------------------------------------------------- #
# The bindings behind the table
# --------------------------------------------------------------------------- #
def test_the_table_and_the_mouse_read_the_same_bindings():
    """The block is a reference, so it has to describe what actually happens.

    Writing the bindings out a second time in the event handlers is how a panel
    ends up promising `CtSh + L = Sele` while the code does something else, and
    nothing catches it because both look right on their own.
    """
    from qtpy import QtCore, QtWidgets

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chimol.ui.input.mouse_modes import action_of, rows_for

    mode = "three_button_viewing"
    cells = dict(rows_for(mode))

    assert action_of(mode, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier) == "rota"
    assert cells["& Keys"][0] == "Rota"

    assert (
        action_of(
            mode,
            QtCore.Qt.LeftButton,
            QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier,
        )
        == "sele"
    )
    assert cells["CtSh"][0] == "Sele"

    assert action_of(mode, QtCore.Qt.RightButton, QtCore.Qt.ControlModifier) == "pk1"
    assert cells["Ctrl"][2] == "Pk1"


def test_ctrl_shift_is_its_own_row_not_a_ctrl_row():
    """`CtSh` is a row of its own; testing ctrl first would swallow it."""
    from qtpy import QtCore, QtWidgets

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chimol.ui.input.mouse_modes import modifier_of

    assert modifier_of(QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier) == "ctsh"
    assert modifier_of(QtCore.Qt.ControlModifier) == "ctrl"
    assert modifier_of(QtCore.Qt.ShiftModifier) == "shft"
    assert modifier_of(QtCore.Qt.NoModifier) == "none"


def test_the_wheel_bindings_come_from_the_table_too():
    from qtpy import QtCore, QtWidgets

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chimol.ui.input.mouse_modes import wheel_action_of

    mode = "three_button_viewing"
    assert wheel_action_of(mode, QtCore.Qt.NoModifier) == "slab"
    assert wheel_action_of(mode, QtCore.Qt.ShiftModifier) == "movs"
    assert wheel_action_of(mode, QtCore.Qt.ControlModifier) == "mvsz"


# Selection cost is not tested here for the same reason the mouse routing is
# not: it needs a real `Viewer`, and constructing a QOpenGLWidget inside pytest
# aborts the interpreter in this environment, taking every other test with it.
#
# Measured with a standalone probe instead, on 148L:
#
#     set_selected_residues        88.01 ms  ->  0.11 ms
#     _update_selection_highlight   0.01 ms
#     update_view (full rebuild)  85.73 ms
#
# The first used to *be* the third: selecting rebuilt every representation. A
# drag over the sequence fires one per mouse move, so the highlight lagged the
# cursor by a full rebuild each step, for work that had nothing to do with what
# changed.


# --------------------------------------------------------------------------- #
# The object list and mouse block as windows: snap, anchor, remember
# --------------------------------------------------------------------------- #
def test_the_panel_and_block_are_windows_snapped_to_the_right_corners(gui):
    """The user ask: the PyMOL column becomes windows, top- and bottom-right."""
    objects = gui.window("objects")
    mouse = gui.window("mouse")
    assert objects is not None and mouse is not None
    assert objects.anchor == "top-right"
    assert mouse.anchor == "bottom-right"
    assert gui.panel_rect.x + gui.panel_rect.w == pytest.approx(WIDTH)
    assert gui.block_rect.x + gui.block_rect.w == pytest.approx(WIDTH)
    # Above the command row, not on it: the prompt band is out of bounds for
    # windows, so the bottom anchor stops at its top edge.
    assert gui.block_rect.y + gui.block_rect.h == pytest.approx(
        HEIGHT - gui._bottom_chrome_height()
    )


def test_closing_the_object_window_removes_its_hit_targets(gui):
    gui.window("objects").visible = False
    gui.layout(WIDTH, HEIGHT)
    assert gui._row_rects == [], "a closed window left clickable ghosts"
    gui.window("objects").visible = True
    gui.layout(WIDTH, HEIGHT)
    assert gui._row_rects, "reopening did not bring the rows back"


def test_a_dragged_window_snaps_to_the_edge_and_anchors_in_corners(gui):
    win = gui.window("objects")
    frame = gui.window_frame(win)
    grab = (frame.x + frame.w / 2, frame.y + 6)  # the title bar
    gui.mouse_press(*grab)

    # Near the left edge: the x snaps flush and the window anchors to the
    # side, so it follows that edge through resizes.
    gui.drag(frame.w / 2 + 5, HEIGHT / 2)
    assert win.x == pytest.approx(0.0)
    assert win.anchor == "left"

    # Into the bottom-left corner -- the window's *bottom* near the edge --
    # snapped on both axes, and anchored there.
    gui.drag(frame.w / 2 + 5, HEIGHT - frame.h + 10)
    assert win.anchor == "bottom-left"
    gui.release()


def test_window_states_survive_a_restart(tmp_path, monkeypatch):
    """The ask: chimol must remember window states between restarts."""
    from chimol.ui.gui import windows

    path = tmp_path / "chimol_windows.json"
    monkeypatch.setattr(windows, "window_state_path", lambda: path)

    first = InternalGui()
    first.enable_persistence()
    first.layout(WIDTH, HEIGHT)
    mouse = first.window("mouse")
    mouse.visible = False
    objects = first.window("objects")
    objects.anchor = None
    objects.x, objects.y = 111.0, 77.0
    first.persist_windows()

    second = InternalGui()
    second.enable_persistence()
    second.layout(WIDTH, HEIGHT)
    assert second.window("mouse").visible is False
    restored = second.window("objects")
    assert restored.anchor is None
    assert (restored.x, restored.y) == (111.0, 77.0)


def test_a_bare_panel_never_touches_the_saved_states(tmp_path, monkeypatch):
    """Tests and headless probes must not read or write real preferences."""
    from chimol.ui.gui import windows

    path = tmp_path / "chimol_windows.json"
    monkeypatch.setattr(windows, "window_state_path", lambda: path)

    gui = InternalGui()  # persistence never enabled
    gui.layout(WIDTH, HEIGHT)
    gui.persist_windows()
    assert not path.exists(), "a bare panel wrote preferences"


def test_an_edge_hit_by_overshooting_still_sticks(gui):
    """An edge is hit by flinging the cursor at it, and the frame overshoots.

    The first snap tested ``abs(edge - frame)`` and concluded a window slammed
    100px past the right edge was nowhere near it -- the reported "sides not
    sticky". Past the line counts as on it.
    """
    win = gui.window("objects")
    frame = gui.window_frame(win)
    gui.mouse_press(frame.x + frame.w / 2, frame.y + 6)
    gui.drag(WIDTH + 200, HEIGHT / 2)  # far past the right edge
    assert win.x == pytest.approx(WIDTH - frame.w)
    assert win.anchor == "right"
    gui.release()


def test_a_side_anchored_window_follows_the_edge_through_a_resize(gui):
    win = gui.window("mouse")
    frame = gui.window_frame(win)
    gui.mouse_press(frame.x + frame.w / 2, frame.y + 6)
    gui.drag(WIDTH + 100, HEIGHT / 2)  # park it on the right side
    gui.release()
    assert win.anchor == "right"
    kept_y = win.y

    gui.layout(WIDTH + 300, HEIGHT)
    frame = gui.window_frame(win)
    assert win.x == pytest.approx(WIDTH + 300 - frame.w), (
        "the window stayed behind when its edge moved"
    )
    assert win.y == pytest.approx(kept_y), (
        "a side anchor must keep the window's own position on the free axis"
    )


def test_the_snap_hint_lights_while_glued_and_clears_on_release(gui):
    """The visual half of stickiness: the edge announces the glue, live."""
    win = gui.window("objects")
    frame = gui.window_frame(win)
    gui.mouse_press(frame.x + frame.w / 2, frame.y + 6)

    gui.drag(WIDTH / 2, HEIGHT / 2)  # the open: no hint
    assert gui._snap_hint == ()

    gui.drag(WIDTH + 100, HEIGHT / 2)  # glued to the right side
    assert gui._snap_hint == ("right",)

    gui.drag(WIDTH + 100, HEIGHT + 100)  # into the corner: both edges lit
    assert set(gui._snap_hint) == {"bottom", "right"}

    gui.release()
    assert gui._snap_hint == (), "the hint outlived the drag"


def test_snapping_can_be_turned_off(gui):
    """The `window_snap` setting: off means windows go where they are dropped."""
    gui.window_snap = False
    win = gui.window("objects")
    frame = gui.window_frame(win)
    gui.mouse_press(frame.x + frame.w / 2, frame.y + 6)
    gui.drag(WIDTH - frame.w / 2 - 4, HEIGHT / 2)  # 4px from the right edge
    assert win.x == pytest.approx(WIDTH - frame.w - 4), (
        "with snapping off the window must not jump to the edge"
    )
    assert win.anchor is None
    assert gui._snap_hint == ()
    gui.release()


def test_the_snap_setting_is_declared():
    """`set window_snap, off` must reach a real, documented setting."""
    from chimol.core.settings.registry import SETTINGS

    spec = SETTINGS.get("window_snap")
    assert spec is not None, "window_snap is not a registered setting"
    assert tuple(spec.path) == ("layout", "window_snap")
    assert spec.default is True


# --------------------------------------------------------------------------- #
# Hover tooltips
# --------------------------------------------------------------------------- #
def test_hovering_explains_the_thing_under_the_cursor(gui):
    # An object-menu button says what its letter means.
    gui.mouse_move(*_centre(gui._button_rects[1]["S"]))
    assert gui._tooltip is not None and "Show" in gui._tooltip[2]

    # The eye says it toggles visibility.
    gui.mouse_move(*_centre(gui._eye_rects[1]))
    assert "show or hide" in gui._tooltip[2]

    # A mouse-binding cell is spelled out, not left as an abbreviation.
    block = gui.block_rect
    char_w = char_width(gui.FONT_PT)
    x = block.x + gui.PAD + 10.0 * char_w + 2  # first cell of a binding row
    y = block.y + gui.PAD + 2.5 * gui.BLOCK_ROW_H
    gui.mouse_move(x, y)
    assert gui._tooltip is not None
    assert "left" in gui._tooltip[2], gui._tooltip[2]

    # Off everything, the tooltip goes away.
    gui.mouse_move(WIDTH / 2, HEIGHT / 2)
    assert gui._tooltip is None


# --------------------------------------------------------------------------- #
# Windows stick to each other and move together
# --------------------------------------------------------------------------- #
def _title_grab(gui, win):
    frame = gui.window_frame(win)
    return frame.x + frame.w / 2, frame.y + 6


def test_a_window_dragged_near_another_snaps_flush(gui):
    from chimol.ui.gui import GuiWindow

    a = gui.add_window(GuiWindow(key="a", title="A", x=100, y=200, w=120, h=90))
    b = gui.add_window(GuiWindow(key="b", title="B", x=400, y=210, w=120, h=90))
    gui.layout(WIDTH, HEIGHT)

    gui.mouse_press(*_title_grab(gui, b))
    # Bring B's left edge within stick range of A's right edge, and its top
    # within the perpendicular-align threshold of A's.
    gui.drag(100 + 120 + 60 + 5, 210)
    assert b.x == pytest.approx(a.x + 120), "the windows did not snap flush"
    assert b.y == pytest.approx(a.y), "the near-level tops did not align"
    assert "a" in gui._snap_hint_keys, "the stuck partner is not announced"
    gui.release()
    assert gui._snap_hint_keys == set()


def test_stuck_windows_move_together_and_shift_detaches(gui):
    from chimol.ui.gui import GuiWindow

    a = gui.add_window(GuiWindow(key="a", title="A", x=100, y=200, w=120, h=90))
    b = gui.add_window(GuiWindow(key="b", title="B", x=220, y=200, w=120, h=90))
    gui.layout(WIDTH, HEIGHT)  # flush: b.x == a.x + a.w

    # Dragging A moves B with it, offsets intact.
    gui.mouse_press(*_title_grab(gui, a))
    gui.drag(_title_grab(gui, a)[0] + 40, 260)
    assert b.x == pytest.approx(a.x + 120)
    assert b.y == pytest.approx(a.y)
    gui.release()

    # A shift-drag pulls A out alone.
    before_b = (b.x, b.y)
    gx, gy = _title_grab(gui, a)
    gui.mouse_press(gx, gy, modifiers=QtCore.Qt.ShiftModifier)
    gui.drag(gx - 60, gy + 80)
    assert (b.x, b.y) == pytest.approx(before_b), "shift-drag must move alone"
    assert a.x != pytest.approx(b.x - 120)
    gui.release()
