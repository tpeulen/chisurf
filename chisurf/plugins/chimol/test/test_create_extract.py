"""Splitting a selection into its own object -- PyMOL ``create`` / ``extract``.

Isolating a chain or a ligand for separate treatment is routine work, and without
it a selection can only ever be shown or hidden, never handled as a thing of its
own. ``extract`` differs from ``create`` in exactly one way: it also removes the
atoms from the source.

Two traps are guarded here, both of which are invisible on screen:

* the new object must be drawn **in its parent's frame**, or it jumps to the scene
  origin -- while its stored coordinates must stay true, or ``save`` writes a file
  that loads somewhere else;
* creating an object must not steal the active one, or the next unqualified
  selection silently resolves against the child.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

_PDB_148L = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def session(qapp):
    """Build a fresh viewer with 148L loaded, plus a command interpreter over it."""
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.commands.command import Cmd
    from chimol.io.structure import _read_full_model
    from chimol.core.viewer import MolView

    view = MolView()
    view.add_structure(
        _read_full_model(cs_struct.Structure, _PDB_148L),
        name="148l",
        source_path=str(_PDB_148L),
    )

    class _Window:
        viewer = view

        def _refresh_objects_from_viewer(self):
            pass

        def windowTitle(self):
            return "chimol"

    cmd = Cmd(_Window())
    messages: list[str] = []
    errors: list[str] = []
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    return cmd, view, messages, errors


def _names(view) -> list[str]:
    return [str(o["name"]) for o in view.list_objects()]


def _object(view, name: str):
    for obj in view.list_objects():
        if str(obj["name"]) == name:
            return view._objects[obj["id"]]
    raise AssertionError(f"no object named {name!r}")


def _atom_count(view, name: str) -> int:
    return int(len(_object(view, name).state.atoms))


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
def test_create_makes_a_new_object(session):
    cmd, view, messages, errors = session
    cmd.do("create sugars, resn NAG+MUB")
    assert errors == []
    assert "sugars" in _names(view)
    assert "copied" in messages[-1]


def test_create_copies_exactly_the_selection(session):
    cmd, view, _, _ = session
    expected = int(
        np.count_nonzero(
            np.isin(
                np.char.strip(_object(view, "148l").state.atoms["res_name"].astype(str)),
                ("NAG", "MUB"),
            )
        )
    )
    cmd.do("create sugars, resn NAG+MUB")
    assert _atom_count(view, "sugars") == expected


def test_create_leaves_the_source_intact(session):
    """The only difference from `extract`."""
    cmd, view, _, _ = session
    before = _atom_count(view, "148l")
    cmd.do("create sugars, resn NAG+MUB")
    assert _atom_count(view, "148l") == before


def test_the_child_keeps_its_true_coordinates(session):
    """`save` on the new object must write where the atoms really are.

    The viewer centres every object on its own centroid for rendering, so it is
    tempting to shift the stored coordinates to place the child in its parent's
    frame -- which looks identical on screen and writes a wrong file.
    """
    cmd, view, _, _ = session
    parent = _object(view, "148l").state.atoms
    wanted = np.isin(
        np.char.strip(parent["res_name"].astype(str)), ("NAG", "MUB")
    )
    expected = np.asarray(parent["xyz"], dtype=float)[wanted]

    cmd.do("create sugars, resn NAG+MUB")
    child = np.asarray(_object(view, "sugars").state.atoms["xyz"], dtype=float)
    assert np.allclose(child, expected)


def test_the_child_is_drawn_in_its_parents_frame(session):
    """Otherwise the subset appears at the scene origin, away from its parent."""
    cmd, view, _, _ = session
    cmd.do("create sugars, resn NAG+MUB")
    parent_centre = np.asarray(_object(view, "148l").state.raw_center, dtype=float)
    child_centre = np.asarray(_object(view, "sugars").state.raw_center, dtype=float)
    assert np.allclose(child_centre, parent_centre)


def test_creating_does_not_steal_the_active_object(session):
    """A following unqualified selection must still mean the source.

    `create sugars, resn NAG` then `extract stem, resn DAL` reported that DAL
    matched nothing, because the second selection was resolved against `sugars`.
    """
    cmd, view, _, errors = session
    cmd.do("create sugars, resn NAG+MUB")
    cmd.do("extract stem, resn DAL+FGA")
    assert errors == []
    assert _atom_count(view, "stem") > 0


# --------------------------------------------------------------------------- #
# extract
# --------------------------------------------------------------------------- #
def test_extract_moves_the_atoms(session):
    cmd, view, messages, errors = session
    before = _atom_count(view, "148l")
    cmd.do("extract stem, resn DAL+FGA")
    assert errors == []
    moved = _atom_count(view, "stem")
    assert moved > 0
    assert _atom_count(view, "148l") == before - moved
    assert "moved" in messages[-1]


def test_extract_conserves_the_atom_count(session):
    cmd, view, _, _ = session
    before = _atom_count(view, "148l")
    cmd.do("extract stem, resn DAL+FGA")
    assert _atom_count(view, "148l") + _atom_count(view, "stem") == before


def test_the_extracted_atoms_are_gone_from_the_source(session):
    cmd, view, _, _ = session
    cmd.do("extract stem, resn DAL+FGA")
    remaining = np.char.strip(
        _object(view, "148l").state.atoms["res_name"].astype(str)
    )
    assert not np.isin(remaining, ("DAL", "FGA")).any()


def test_extracting_everything_removes_the_source(session):
    """An object with no atoms left is not an object."""
    cmd, view, _, _ = session
    cmd.do("extract everything, all")
    assert "148l" not in _names(view)
    assert "everything" in _names(view)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def test_an_empty_selection_is_reported(session):
    cmd, view, _, errors = session
    cmd.do("create nothing, resn ZZZ")
    assert errors and "matched no atoms" in errors[-1]
    assert "nothing" not in _names(view)


def test_a_missing_name_is_reported(session):
    cmd, _, _, errors = session
    cmd.do("create")
    assert errors and "Usage" in errors[-1]


def test_a_missing_selection_is_reported(session):
    cmd, _, _, errors = session
    cmd.do("create sugars")
    assert errors and "Usage" in errors[-1]


# --------------------------------------------------------------------------- #
# The child is a real object
# --------------------------------------------------------------------------- #
def test_the_child_can_be_selected_against(session):
    cmd, view, _, errors = session
    cmd.do("create sugars, resn NAG+MUB")
    cmd.do("count_atoms sugars and resn NAG")
    assert errors == []


def test_the_child_can_be_saved(session, tmp_path):
    """The point of extracting a ligand is usually to write it out."""
    cmd, view, _, errors = session
    cmd.do("create sugars, resn NAG+MUB")
    out = tmp_path / "sugars.pdb"
    cmd.do(f"save {out}, sugars")
    assert errors == []
    assert out.exists()
    records = [
        line for line in out.read_text().splitlines()
        if line.startswith(("ATOM", "HETATM"))
    ]
    assert len(records) == _atom_count(view, "sugars")


def test_the_saved_child_carries_its_original_coordinates(session, tmp_path):
    """The frame shift is for drawing only; a file must not inherit it."""
    cmd, view, _, _ = session
    cmd.do("create sugars, resn NAG+MUB")
    out = tmp_path / "sugars.pdb"
    cmd.do(f"save {out}, sugars")
    written = np.array(
        [
            [float(line[30:38]), float(line[38:46]), float(line[46:54])]
            for line in out.read_text().splitlines()
            if line.startswith(("ATOM", "HETATM"))
        ]
    )
    expected = np.asarray(
        _object(view, "sugars").state.atoms["xyz"], dtype=float
    )
    assert np.allclose(written, expected, atol=5e-4)
