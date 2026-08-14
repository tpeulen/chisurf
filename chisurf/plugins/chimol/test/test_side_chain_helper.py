"""``cartoon_side_chain_helper``: side chains that grow out of the ribbon.

The commonest figure in structural biology is a cartoon with sticks on a few
residues. Drawn naively it is a mess: each stick residue also draws its backbone
N, C and O, which run inside the ribbon and poke out of it. PyMOL's setting drops
exactly those bonds where a cartoon already covers them, so the side chain reads
as growing out of the ribbon -- and it is a **bond** filter, not an atom filter,
so the atoms stay in the model and stay pickable.

Photographing this setting is also what turned up the camera defect recorded in
``okf/references/known-issues.md``: the framing kept resetting between the off
and on shots, because every scene rebuild refits the camera.
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
    pytest.importorskip("chisurf.core.structure")
    from chimol.app.molview_main_window import (
        MolViewPluginWindow,
    )
    from chimol.cmd import cmd as shared
    from chimol.config import _DISPLAY_CONFIG

    win = MolViewPluginWindow()
    win.resize(800, 640)
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

    before = _DISPLAY_CONFIG.get("cartoon", {}).get("side_chain_helper", False)
    yield win, do, errors
    # One process-wide config: leaving it on breaks other test *files*.
    _DISPLAY_CONFIG.setdefault("cartoon", {})["side_chain_helper"] = before
    win.close()


def _stick_bonds(win):
    """The bonds the stick representation would draw, after every filter."""
    viewer = win.viewer
    object_id = viewer.get_active_object_id()
    with viewer._activate_object(object_id):
        bonds = np.asarray(viewer._bond_pairs, dtype=int)
        mask = np.asarray(viewer._sticks_mask, dtype=bool)
        scoped = bonds[mask[bonds[:, 0]] & mask[bonds[:, 1]]]
        return viewer._apply_side_chain_helper(scoped)


def _names(win):
    atoms = win.viewer._atoms
    return np.char.upper(np.char.strip(np.asarray(atoms["atom_name"]).astype(str)))


def _kinds(win, bonds):
    names = _names(win)
    return {tuple(sorted((names[i], names[j]))) for i, j in bonds.tolist()}


# --------------------------------------------------------------------------- #
# The bond filter
# --------------------------------------------------------------------------- #
def test_off_by_default_nothing_is_hidden(session):
    win, do, errors = session
    do("hide everything")
    do("show cartoon")
    do("show sticks, byres (resi 20-26)")
    assert errors == []
    kinds = _kinds(win, _stick_bonds(win))
    assert ("C", "CA") in kinds, "the helper hid bonds while off"


def test_it_hides_exactly_the_backbone_bonds(session):
    """N-CA, CA-C, C-N and C-O, and nothing else -- PyMOL's list."""
    win, do, errors = session
    do("hide everything")
    do("show cartoon")
    do("show sticks, byres (resi 20-26)")
    before = _stick_bonds(win)
    do("set cartoon_side_chain_helper, on")
    after = _stick_bonds(win)
    assert errors == []
    assert len(after) < len(before)

    hidden = _kinds(win, before) - _kinds(win, after)
    assert hidden == {("CA", "N"), ("C", "CA"), ("C", "O"), ("C", "N")}, hidden


def test_the_side_chain_bond_survives(session):
    """CA-CB is the bond the side chain hangs from; hiding it would empty it."""
    win, do, errors = session
    do("hide everything")
    do("show cartoon")
    do("show sticks, byres (resi 20-26)")
    do("set cartoon_side_chain_helper, on")
    assert errors == []
    assert ("CA", "CB") in _kinds(win, _stick_bonds(win))


def test_proline_keeps_its_n_ca(session):
    """Proline's N-CA closes its ring: PyMOL keeps it and hands the colour over."""
    win, do, errors = session
    do("hide everything")
    do("show cartoon")
    do("show sticks, byres (resn PRO)")
    do("set cartoon_side_chain_helper, on")
    assert errors == []
    kept = _kinds(win, _stick_bonds(win))
    assert ("CA", "N") in kept, "proline lost the N-CA its ring needs"
    assert ("C", "CA") not in kept, "the non-ring backbone bonds should still go"


def test_nothing_is_hidden_where_no_cartoon_covers_it(session):
    """The bonds are dropped because a cartoon already draws them, so with the
    cartoon off there is nothing to defer to."""
    win, do, errors = session
    do("hide everything")
    do("show sticks, byres (resi 20-26)")
    do("set cartoon_side_chain_helper, on")
    assert errors == []
    assert ("C", "CA") in _kinds(win, _stick_bonds(win))
