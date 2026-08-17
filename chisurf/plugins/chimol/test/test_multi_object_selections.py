"""Selections reach every object, not only the active one.

PyMOL's selector runs over one atom table spanning every loaded object
(``layer3/Selector.cpp``), so three things follow that chimol used to get wrong,
each of them *silently*:

* a **group name** is an ordinary selection word covering all of its members --
  ``count_atoms ligands`` answered ``0``, and every representation, colour and
  camera command pointed at a group did nothing at all;
* a plain expression such as ``chain A`` means chain A **wherever it is**, not
  in whichever object happens to be active;
* a name that resolves to nothing is an **error** (``Invalid selection name``),
  not an empty answer -- a typo used to read as "no atoms match".

The group case is the one the object panel depends on: its group rows emit
``show sticks, <group>`` and friends, so the whole row of A/S/H/L/C buttons was
inert before this.
"""

from __future__ import annotations

import pathlib

import numpy as np
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
    """A window with three derived objects, two of them grouped."""
    pytest.importorskip("chisurf.core.structure")
    from chimol.hosts.qt.window import MolViewPluginWindow
    from chimol.commands import cmd as shared

    win = MolViewPluginWindow()
    win.resize(900, 600)
    win._load_structure_from_path(_PDB)
    for _ in range(20):
        qapp.processEvents()

    messages: list[str] = []
    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(messages.append)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(8):
            qapp.processEvents()

    do("create lig, organic")
    do("create nag, resn NAG")
    do("group ligands, lig nag")
    messages.clear()
    errors.clear()

    yield win, do, messages, errors
    win.close()


def _ids(viewer) -> dict[str, str]:
    return {o["name"]: str(o["id"]) for o in viewer.list_objects()}


def _state(viewer, name):
    return viewer._objects[_ids(viewer)[name]].state


# --------------------------------------------------------------------------- #
# A group is a selection word
# --------------------------------------------------------------------------- #
def test_a_group_counts_all_of_its_members(session):
    win, do, _msgs, errors = session
    from chimol.commands import cmd as shared

    lig = shared.count_atoms("lig")
    nag = shared.count_atoms("nag")
    assert lig and nag
    assert shared.count_atoms("ligands") == lig + nag
    assert errors == []


def test_a_group_narrows_like_any_other_word(session):
    """``ligands and elem C`` must be the group's carbons, not the group."""
    win, do, _msgs, errors = session
    from chimol.commands import cmd as shared

    whole = shared.count_atoms("ligands")
    carbons = shared.count_atoms("ligands and elem C")
    assert 0 < carbons < whole
    assert errors == []


def test_showing_a_representation_on_a_group_reaches_every_member(session):
    """The object panel's group row emits exactly this."""
    win, do, _msgs, errors = session
    viewer = win.viewer

    do("hide everything")
    do("show spheres, ligands")
    assert errors == []
    for name in ("lig", "nag"):
        state = _state(viewer, name)
        assert state.show_atoms, f"{name} did not get the representation"
        assert state.ball_mask is None or state.ball_mask.any()
    # and not to an object outside the group
    assert not _state(viewer, "148l").show_atoms


def test_colouring_a_group_reaches_every_member(session):
    win, do, _msgs, errors = session
    viewer = win.viewer

    do("color red, ligands")
    assert errors == []
    for name in ("lig", "nag"):
        override = _state(viewer, name).colors_per_atom_override
        assert override is not None, f"{name} kept its colour"
        assert np.isfinite(override).any()


def test_hide_everything_hides_every_object(session):
    """PyMOL's unscoped ``hide`` means *everything*, not the active object.

    Only ``spheres`` had a spanning setter, so ``hide everything`` left a second
    molecule's cartoon on screen while reporting that it had hidden it.
    """
    win, do, _msgs, errors = session
    viewer = win.viewer

    do("show cartoon")
    do("show sticks")
    do("hide everything")
    assert errors == []
    for name in ("148l", "lig", "nag"):
        state = _state(viewer, name)
        assert not state.show_cartoon, f"{name} kept its cartoon"
        assert not state.show_sticks, f"{name} kept its sticks"
        assert not state.show_atoms, f"{name} kept its spheres"


def test_a_colour_reaches_the_geometry_of_a_created_object(session):
    """The scene, not just the state: the two used to disagree.

    An object with no residue table is drawn by the point-sphere path, which
    read ``colors_per_ca`` alone -- so ``color`` wrote an override that nothing
    ever looked at, and the molecule stayed its default colour while the command
    reported success.
    """
    win, do, _msgs, errors = session
    viewer = win.viewer

    do("hide everything")
    do("show spheres, lig")
    do("color red, lig")
    assert errors == []

    object_id = _ids(viewer)["lig"]
    with viewer._activate_object(object_id):
        objects = viewer._build_scene_for_current_object(object_prefix=object_id)
    drawn = [
        np.asarray(o.geometry.colors)[:, :3]
        for o in (objects or [])
        if o.geometry.colors is not None and len(o.geometry.colors)
    ]
    assert drawn, "the object drew nothing"
    reds = np.concatenate(drawn, axis=0)
    assert np.allclose(reds, [1.0, 0.0, 0.0]), (
        f"the geometry is not red: first colour {reds[0]}"
    )


def test_a_created_ligand_can_be_coloured_at_all(session):
    """`create` leaves no residue table; colouring atoms never needed one.

    Requiring one meant every object made by ``create`` refused to colour, with
    a message about atom coordinates that were in fact present.
    """
    win, do, _msgs, errors = session
    viewer = win.viewer

    assert _state(viewer, "lig").residue_ids is None
    do("color blue, lig")
    assert errors == []
    assert _state(viewer, "lig").colors_per_atom_override is not None


def test_zoom_on_a_group_frames_all_of_it(session):
    """Framing one member is the failure this hides: it looks like it worked."""
    win, do, _msgs, errors = session
    viewer = win.viewer

    do("zoom lig")
    only_lig = viewer.get_view_state()[15]  # the camera's z distance
    do("zoom ligands")
    both = viewer.get_view_state()[15]
    assert errors == []
    assert abs(both) > abs(only_lig), (
        "zooming a group framed no more than its first member"
    )


# --------------------------------------------------------------------------- #
# An expression is not confined to the active object
# --------------------------------------------------------------------------- #
def test_a_plain_expression_counts_every_object(session):
    win, do, _msgs, errors = session
    from chimol.commands import cmd as shared

    total = shared.count_atoms("all")
    per_object = sum(
        shared.count_atoms(name)
        for name in ("148l", "lig", "nag")
    )
    assert total == per_object
    assert errors == []


def test_a_selection_spanning_objects_stores_all_of_them(session):
    win, do, _msgs, errors = session
    from chimol.commands import cmd as shared

    do("select ligs, ligands")
    entry = shared._named_selections["ligs"]
    assert {p["object_id"] for p in entry["objects"]} == {
        _ids(win.viewer)["lig"], _ids(win.viewer)["nag"]
    }
    # and the name recalls the same atoms it captured
    assert shared.count_atoms("ligs") == shared.count_atoms("ligands")
    assert errors == []


# --------------------------------------------------------------------------- #
# An unknown name is an error
# --------------------------------------------------------------------------- #
def test_an_unknown_name_is_reported_not_answered_as_zero(session):
    win, do, _msgs, errors = session

    do("count_atoms lgi")
    assert errors and "lgi" in errors[-1]
    assert "Invalid selection name" in errors[-1]


def test_a_question_mark_allows_an_undefined_name(session):
    """PyMOL's `?sele` spelling: undefined is allowed here."""
    win, do, _msgs, errors = session
    from chimol.commands import cmd as shared

    assert shared.count_atoms("?nosuchthing") == 0
    assert errors == []


def test_a_real_name_still_answers_after_the_error_path(session):
    """The unknown-name check must not fire for a name only *some* object has."""
    win, do, _msgs, errors = session
    from chimol.commands import cmd as shared

    assert shared.count_atoms("lig") > 0
    assert errors == []
