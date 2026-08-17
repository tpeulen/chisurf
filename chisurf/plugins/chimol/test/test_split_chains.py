"""``split_chains``, and the visibility bug behind "the cartoons look weird".

Two defects, and the second is the one with reach beyond this command.

PyMOL's ``split_chains`` ends with ``_self.disable(model)`` -- it **hides the
source** after making the per-chain copies. chimol did not, so the whole
structure stayed drawn on top of every chain: two cartoons per residue in the
same place, fighting for the depth buffer.

Hiding it then did not stick, because ``_add_object_list_item`` set every row's
checkbox to ``Checked`` unconditionally. Any panel rebuild therefore re-showed
whatever had been hidden -- not just here, but for any ``disable`` at all.
"""

from __future__ import annotations

import pathlib

import pytest

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
    pytest.importorskip("chisurf.core.structure")
    from chimol.hosts.qt.window import MolViewPluginWindow

    win = MolViewPluginWindow()
    shared = win.cmd
    win.resize(900, 650)
    win.show()
    for _ in range(12):
        qapp.processEvents()
    win.load_structure_from_path(_PDB)
    for _ in range(25):
        qapp.processEvents()

    errors: list[str] = []
    messages: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(20):
            qapp.processEvents()

    yield win, do, messages, errors
    win.close()


def _visibility(win):
    return {o["name"]: bool(o["visible"]) for o in win.viewer.list_objects()}


def test_split_chains_makes_one_object_per_chain(session):
    win, do, _messages, errors = session
    before = set(_visibility(win))
    do("split_chains")
    assert errors == []
    created = set(_visibility(win)) - before
    assert len(created) >= 2


def test_the_source_is_hidden_afterwards(session):
    """PyMOL calls disable(model). Leaving it visible draws the whole structure
    on top of every chain copy, which is what "looks weird" is."""
    win, do, _messages, errors = session
    source = next(iter(_visibility(win)))
    do("split_chains")
    assert errors == []
    assert _visibility(win)[source] is False


def test_the_chain_copies_are_visible(session):
    win, do, _messages, _errors = session
    before = set(_visibility(win))
    do("split_chains")
    visibility = _visibility(win)
    for name in set(visibility) - before:
        assert visibility[name] is True, name


def test_the_source_is_not_deleted(session):
    """Hidden, not removed: re-enabling it is how the split is undone, and it
    still carries anything the per-chain copies do not."""
    win, do, _messages, _errors = session
    source = next(iter(_visibility(win)))
    do("split_chains")
    assert source in _visibility(win)


def test_hiding_survives_a_panel_rebuild(session):
    """The bug with reach beyond this command.

    The object panel set every checkbox to Checked regardless of the entry, so a
    rebuild silently re-showed anything hidden -- any `disable`, not just this.
    """
    win, do, _messages, _errors = session
    source = next(iter(_visibility(win)))
    do("split_chains")
    assert _visibility(win)[source] is False
    win.refresh_objects()
    # The rebuild that used to re-show it. `sync_internal_gui` is what rebuilds
    # the panel now the Qt dock is gone -- same act, one list instead of two.
    win.sync_internal_gui()
    assert _visibility(win)[source] is False, "the rebuild re-showed the source"


def test_an_explicitly_hidden_object_stays_hidden_across_a_rebuild(session):
    """The same guarantee, reached without split_chains."""
    win, do, _messages, _errors = session
    name = next(iter(_visibility(win)))
    object_id = next(
        o["id"] for o in win.viewer.list_objects() if o["name"] == name
    )
    win.set_object_visible(object_id, False)
    win.refresh_objects()
    assert _visibility(win)[name] is False


def test_the_checkbox_matches_the_stored_visibility(session):
    """What the user sees has to agree with what is drawn."""
    win, do, _messages, _errors = session
    do("split_chains")
    win.sync_internal_gui()
    # The panel's own rows. `enabled` is the eye -- what the user sees switched
    # on -- and it has to agree with the stored visibility for every object.
    rows = [
        r for r in win.viewer.gui.rows
        if not r.is_header and not r.is_selection and not r.is_measurement
        and not r.is_group
    ]
    visibility = _visibility(win)
    seen = 0
    for row in rows:
        name = row.name
        if name not in visibility:
            continue
        seen += 1
        assert bool(row.enabled) is visibility[name], name
    assert seen, "no object rows were inspected"


def test_split_chains_can_group_the_result(session):
    """PyMOL's `group` argument, which is what makes the result tidy."""
    win, do, _messages, errors = session
    before = set(_visibility(win))
    do("split_chains , chains")
    assert errors == []
    created = set(_visibility(win)) - before
    assert created
    assert "chains" in win.viewer.group_names()
    names = {
        o["name"] for o in win.viewer.list_objects()
        if str(o["id"]) in set(win.viewer.group_members("chains"))
    }
    assert names == created
