"""Atom-level selections stay atom-level through `sele`.

The report: mouse-selecting *atoms* worked, but `show sticks, sele` changed
the representation of the whole residue. `sele`'s fallback to the live
viewport selection resolved through the residue list -- which exists at every
level because it drives the sequence-strip highlight -- and silently widened
the atom picks.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

pytest.importorskip("qtpy")


@pytest.fixture(scope="session")
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def shell(qapp):
    pytest.importorskip("chisurf.core.structure")
    from chisurf.plugins.chimol.chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chisurf.plugins.chimol.chimol.cmd.command import Cmd

    pdb = (
        pathlib.Path(__file__).resolve().parents[4]
        / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
    )
    if not pdb.is_file():
        pytest.skip("148l.pdb fixture not present")

    win = MolViewPluginWindow()
    win.resize(900, 650)
    win.show()
    for _ in range(10):
        qapp.processEvents()
    win._load_structure_from_path(pdb)
    for _ in range(20):
        qapp.processEvents()

    messages, errors = [], []
    cmd = Cmd()
    cmd.set_window(win)
    cmd.set_message_callback(messages.append)
    cmd.set_error_callback(errors.append)
    yield win.viewer, cmd, messages, errors
    win.close()


def _atoms_of_first_residue(view):
    per_atom = view._atom_residue_indices()
    assert per_atom is not None
    residue = int(per_atom[per_atom >= 0][0])
    atoms = np.flatnonzero(np.asarray(per_atom) == residue)
    assert atoms.size >= 3, "need a residue with several atoms to tell levels apart"
    return residue, atoms


def test_sele_at_atom_level_means_exactly_the_picked_atoms(shell):
    view, cmd, _messages, errors = shell
    view.set_selection_level("Atoms")
    _residue, atoms = _atoms_of_first_residue(view)
    picked = [int(atoms[0]), int(atoms[1])]
    view._apply_atom_selection(picked, mode="set")
    view._apply_selection_indices(
        view._residues_holding_selected_atoms([]), None, mode="set"
    )

    cmd.do("show sticks, sele")
    assert not errors, errors

    state = view._get_active_state()
    mask = np.asarray(getattr(state, "sticks_mask"))
    assert int(mask.sum()) == 2, (
        f"two picked atoms became {int(mask.sum())} shown atoms -- the "
        "selection was widened to the residue"
    )
    assert mask[picked].all()


def test_sele_at_residue_level_still_means_the_residue(shell):
    """The fix must not narrow the level everyone else uses."""
    view, cmd, _messages, errors = shell
    view.set_selection_level("Residues")
    _residue, atoms = _atoms_of_first_residue(view)
    view._apply_selection_indices([0], None, mode="set")

    cmd.do("show sticks, sele")
    assert not errors, errors

    state = view._get_active_state()
    mask = np.asarray(getattr(state, "sticks_mask"))
    assert int(mask.sum()) >= atoms.size, (
        "a residue-level selection must keep reaching the whole residue"
    )
