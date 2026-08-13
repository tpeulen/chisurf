"""Object groups: ``group``, ``ungroup``, ``order``, and the panel rows.

PyMOL's group is a container row in the object panel, and the semantics come
straight from ``modules/pymol/creating.py``: eleven actions, one of which
(``auto``) is resolved before dispatch, and a second argument that means either
*members* or an *action* depending on what it looks like.

Two things here are easy to get wrong and are pinned deliberately:

* membership lives on the member, so a group has no existence apart from its
  members -- deleting the last one must take the group with it rather than leave
  a row nothing can be dragged out of;
* a group's members must be drawn **contiguously** under its header. The
  viewer's registry does not keep them adjacent, so grouping the first and third
  objects used to draw the third under a later group's header.
"""

from __future__ import annotations

import pathlib

import pytest

from chisurf.plugins.chimol.chimol.object_menus import OBJECT_MENUS, targets_for

_PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    """A window with three derived objects to group in various ways."""
    pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd import cmd as shared

    win = MolViewPluginWindow()
    win.resize(1000, 700)
    win.show()
    for _ in range(10):
        qapp.processEvents()
    win._load_structure_from_path(_PDB)
    for _ in range(20):
        qapp.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(8):
            qapp.processEvents()

    do("create lig, organic")
    do("create pep, chain S and polymer")
    do("create nag, resn NAG")
    errors.clear()

    yield win, do, errors
    win.close()


def _names(viewer, group):
    by_id = {str(o["id"]): o["name"] for o in viewer.list_objects()}
    return [by_id[oid] for oid in viewer.group_members(group)]


def _rows(win):
    """(kind, label) for each panel row, in order.

    Read from the in-viewport panel rather than a ``QListWidget``. The Qt
    object dock this used to inspect is gone; the panel that replaced it holds
    the same list as :class:`~chimol.renderer.internal_gui.GuiRow` records,
    which is a better thing to assert against anyway -- it is the state the
    renderer draws from, not a widget mirroring it.

    The ``all`` header and the ``sele`` pseudo-object are filtered out: they
    are chrome, not objects, and the dock did not list them.
    """
    gui = win.viewer._renderer._internal_gui
    return [
        ("group" if row.is_group else "object", row.name)
        for row in gui.rows
        if not row.is_header and not row.is_selection and not row.is_measurement
    ]


# --------------------------------------------------------------------------- #
# group: membership
# --------------------------------------------------------------------------- #
def test_add_puts_objects_in_a_group(session):
    win, do, errors = session
    do("group ligands, lig nag")
    assert errors == []
    assert _names(win.viewer, "ligands") == ["lig", "nag"]
    assert win.viewer.group_names() == ["ligands"]


def test_remove_takes_them_out_again(session):
    win, do, errors = session
    do("group ligands, lig nag")
    do("group ligands, lig, remove")
    assert errors == []
    assert _names(win.viewer, "ligands") == ["nag"]


def test_a_group_cannot_contain_itself(session):
    """Otherwise the panel gets a row that is its own parent."""
    win, do, errors = session
    do("group lig, lig")
    assert errors and "itself" in errors[-1]


def test_an_unknown_member_is_named_not_ignored(session):
    win, do, errors = session
    do("group ligands, lig nosuchthing")
    assert errors and "nosuchthing" in errors[-1]
    assert win.viewer.group_names() == []


def test_empty_releases_the_members_and_keeps_them(session):
    win, do, errors = session
    do("group ligands, lig nag")
    do("group ligands, empty")
    assert errors == []
    assert win.viewer.group_names() == []
    assert {o["name"] for o in win.viewer.list_objects()} >= {"lig", "nag"}


def test_purge_deletes_the_members(session):
    win, do, errors = session
    do("group ligands, lig nag")
    do("group ligands, purge")
    assert errors == []
    names = {o["name"] for o in win.viewer.list_objects()}
    assert "lig" not in names and "nag" not in names


def test_excise_deletes_the_members_and_the_group(session):
    win, do, errors = session
    do("group ligands, lig nag")
    do("group ligands, excise")
    assert errors == []
    assert win.viewer.group_names() == []


def test_deleting_the_last_member_removes_the_group(session):
    """A group with no members is a row nothing can be dragged out of."""
    win, do, errors = session
    do("group ligands, lig")
    assert win.viewer.group_names() == ["ligands"]
    do("delete lig")
    assert win.viewer.group_names() == []


# --------------------------------------------------------------------------- #
# group: open / close, and the two meanings of the second argument
# --------------------------------------------------------------------------- #
def test_close_and_open(session):
    win, do, errors = session
    do("group ligands, lig nag")
    assert win.viewer.is_group_open("ligands")
    do("group ligands, close")
    assert not win.viewer.is_group_open("ligands")
    do("group ligands, open")
    assert win.viewer.is_group_open("ligands")
    assert errors == []


def test_an_action_in_the_members_slot_is_read_as_one(session):
    """``group kinases, close`` is how PyMOL's own menu writes it.

    Treating the word as an object name instead would report a missing object
    for every documented example in the command's help text.
    """
    win, do, errors = session
    do("group ligands, lig nag")
    errors.clear()
    do("group ligands, close")
    assert errors == []
    assert not win.viewer.is_group_open("ligands")


def test_auto_toggles_an_existing_group_and_adds_otherwise(session):
    win, do, errors = session
    do("group ligands, lig nag")          # auto with members -> add
    assert _names(win.viewer, "ligands") == ["lig", "nag"]
    do("group ligands")                   # auto, no members -> toggle
    assert not win.viewer.is_group_open("ligands")
    do("group ligands")
    assert win.viewer.is_group_open("ligands")
    assert errors == []


def test_toggling_a_group_that_does_not_exist_says_so(session):
    win, do, errors = session
    do("group nope, close")
    assert errors and "nope" in errors[-1]


def test_an_unknown_action_lists_the_valid_ones(session):
    win, do, errors = session
    do("group ligands, lig nag")
    errors.clear()
    do("group ligands, lig, flibble")
    assert errors and "flibble" in errors[-1] and "add" in errors[-1]


# --------------------------------------------------------------------------- #
# ungroup
# --------------------------------------------------------------------------- #
def test_ungroup_by_member_names(session):
    win, do, errors = session
    do("group ligands, lig nag")
    do("ungroup lig")
    assert errors == []
    assert _names(win.viewer, "ligands") == ["nag"]


def test_ungroup_by_group_name_empties_it(session):
    win, do, errors = session
    do("group ligands, lig nag")
    do("ungroup ligands")
    assert errors == []
    assert win.viewer.group_names() == []


def test_ungroup_names_what_it_could_not_find(session):
    win, do, errors = session
    do("ungroup nothinghere")
    assert errors and "nothinghere" in errors[-1]


# --------------------------------------------------------------------------- #
# order
# --------------------------------------------------------------------------- #
def _panel_order(viewer):
    return [o["name"] for o in viewer.list_objects()]


def test_order_sets_a_relative_order(session):
    win, do, errors = session
    do("order nag lig")
    assert errors == []
    order = _panel_order(win.viewer)
    assert order.index("nag") < order.index("lig")


def test_order_to_the_top_and_bottom(session):
    win, do, errors = session
    do("order nag, location=top")
    assert _panel_order(win.viewer)[0] == "nag"
    do("order nag, location=bottom")
    assert _panel_order(win.viewer)[-1] == "nag"
    assert errors == []


def test_order_sorts_when_asked(session):
    win, do, errors = session
    do("order lig nag pep, yes")
    assert errors == []
    order = _panel_order(win.viewer)
    picked = [n for n in order if n in ("lig", "nag", "pep")]
    assert picked == ["lig", "nag", "pep"]


def test_order_accepts_a_pattern(session):
    win, do, errors = session
    do("order *, yes")
    assert errors == []
    assert _panel_order(win.viewer) == sorted(_panel_order(win.viewer), key=str.lower)


def test_order_rejects_an_unknown_location(session):
    win, do, errors = session
    do("order lig, no, sideways")
    assert errors and "location" in errors[-1]


def test_order_names_an_object_that_does_not_exist(session):
    win, do, errors = session
    do("order lig nosuchthing")
    assert errors and "nosuchthing" in errors[-1]


def test_a_group_name_expands_to_its_members(session):
    """PyMOL: a group can be used wherever an object name can."""
    win, do, errors = session
    do("group ligands, lig nag")
    do("order ligands, location=top")
    assert errors == []
    assert set(_panel_order(win.viewer)[:2]) == {"lig", "nag"}


# --------------------------------------------------------------------------- #
# the panel rows
# --------------------------------------------------------------------------- #
def test_a_group_gets_a_header_row_and_indented_members(session):
    win, do, _ = session
    do("group ligands, lig nag")
    rows = _rows(win)
    assert ("group", "ligands") in rows
    header = rows.index(("group", "ligands"))
    assert rows[header + 1][0] == "object"


def test_members_are_drawn_contiguously_under_their_header(session):
    """`lig` and `nag` are not adjacent in the registry -- `pep` is between them.

    Walking the registry directly drew `nag` under whichever group header came
    last, which for two groups is the wrong one.
    """
    win, do, _ = session
    do("group ligands, lig nag")
    do("group parts, pep")
    rows = _rows(win)
    kinds = [k for k, _ in rows]
    labels = [lbl for _, lbl in rows]

    li = labels.index("ligands")
    assert kinds[li] == "group"
    # Everything up to the next group row belongs to `ligands`.
    block = []
    for kind, label in rows[li + 1:]:
        if kind == "group":
            break
        block.append(label)
    assert set(block) == {"lig", "nag"}, f"ligands block was {block}"


def test_a_closed_group_hides_its_members_but_keeps_them_loaded(session):
    win, do, _ = session
    do("group ligands, lig nag")
    do("group ligands, close")
    labels = [lbl for kind, lbl in _rows(win) if kind == "object"]
    assert "lig" not in labels and "nag" not in labels
    # Still loaded: a collapsed row is a display state, not an unload.
    assert {o["name"] for o in win.viewer.list_objects()} >= {"lig", "nag"}
    assert "lig" in {e["name"] for e in win._object_store.values()}


def test_the_members_are_indented_and_the_header_is_not(session):
    """Asked of the row's own ``indent``, not a widget's left margin.

    The Qt dock expressed this as ``contentsMargins().left()`` on a row widget;
    the panel that replaced it carries the depth on the row itself, which is
    the thing the renderer actually offsets by.
    """
    win, do, _ = session
    do("group ligands, lig")
    rows = {row.name: row for row in win.viewer._renderer._internal_gui.rows}
    assert "ligands" in rows and "lig" in rows
    assert rows["lig"].indent > rows["ligands"].indent, (
        "a group member has to look like one"
    )


def test_the_group_header_carries_the_same_five_menus(session):
    """A group is a command target, so it needs the menus that act on one."""
    win, do, _ = session
    do("group ligands, lig nag")
    gui = win.viewer._renderer._internal_gui
    index = next(
        (i for i, r in enumerate(gui.rows) if r.is_group and r.name == "ligands"),
        None,
    )
    assert index is not None, "no group header row was built"

    # The buttons are laid out, not stored on a widget: `layout` fills one
    # dict of hit-rects per row, keyed by the menu letter. So the question
    # "does this row carry the five menus" is asked of the geometry the panel
    # actually clicks against, which is stricter than the old check against a
    # widget's own list.
    gui.layout(1000, 700)
    assert set(gui._button_rects[index]) == {"A", "S", "H", "L", "C"}
    # ... and they are the five from the shared table, not a private copy.
    assert [letter for letter, _label, _entries in OBJECT_MENUS] == [
        "A", "S", "H", "L", "C",
    ]


def test_a_menu_entry_on_a_group_runs_once_per_member(session):
    """"The command should be applied to all members of the group."" -- PyMOL."""
    win, do, _ = session
    do("group ligands, lig nag")
    targets = targets_for(win.viewer, "show cartoon, {sele}", "ligands")
    assert sorted(targets) == ["lig", "nag"]


def test_a_group_aware_command_is_not_expanded(session):
    """`group ligands, toggle` per member would toggle nothing at all."""
    win, do, _ = session
    do("group ligands, lig nag")
    assert targets_for(win.viewer, "group {sele}, toggle", "ligands") == ["ligands"]


def test_an_ordinary_object_is_its_own_target(session):
    win, do, _ = session
    assert targets_for(win.viewer, "show cartoon, {sele}", "lig") == ["lig"]


# --------------------------------------------------------------------------- #
# the display-order helper on its own
# --------------------------------------------------------------------------- #
def test_grouped_display_order_keeps_blocks_together():
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow as W,
    )

    objects = [
        {"id": "a", "name": "a", "group": None},
        {"id": "b", "name": "b", "group": "g"},
        {"id": "c", "name": "c", "group": None},
        {"id": "d", "name": "d", "group": "g"},
    ]
    assert [o["id"] for o in W._grouped_display_order(objects)] == [
        "a", "b", "d", "c",
    ]


def test_grouped_display_order_is_identity_without_groups():
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow as W,
    )

    objects = [{"id": c, "name": c, "group": None} for c in "abc"]
    assert [o["id"] for o in W._grouped_display_order(objects)] == ["a", "b", "c"]
