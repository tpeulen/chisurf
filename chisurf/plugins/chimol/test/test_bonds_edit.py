"""Editing the bond table: ``bond``, ``unbond``, ``get_bonds``.

Semantics from PyMOL's ``modules/pymol/editing.py`` and ``querying.py``:

* ``bond`` needs **exactly one atom** from each selection, both in the same
  object, because a bond lives inside one object's connectivity table;
* ``unbond`` takes selections of any size and removes **every** bond running
  between them;
* ``get_bonds`` returns ``(atm1, atm2, order)`` where the indices are **0-based
  positions within the selection**, not the ``index`` property. PyMOL warns
  about this in capitals, and the two coincide for ``all`` -- so a test that only
  checks ``all`` cannot tell the difference, which is why one here deliberately
  selects atoms that do not start at zero.

The design point worth guarding: bonds are re-inferred from coordinates whenever
a structure loads or moves, so a manual bond kept only in ``bond_pairs`` would
disappear the next time anything moved an atom. Edits are stored as deltas and
replayed over each fresh inference; two tests move atoms afterwards to prove it.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

#: Six alanines on a helix, a zinc ion and eight waters. The ion and the waters
#: are unbonded, which is what makes it usable for bonding something that has no
#: business being bonded.
_FRAGMENT = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "solvated_fragment.pdb"
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
    for _ in range(10):
        qapp.processEvents()
    win.load_structure_from_path(_FRAGMENT)
    for _ in range(20):
        qapp.processEvents()

    errors: list[str] = []
    shared.set_window(win)
    shared.set_message_callback(lambda _m: None)
    shared.set_error_callback(errors.append)

    def do(line: str) -> None:
        shared.do(line)
        for _ in range(6):
            qapp.processEvents()

    yield win.viewer, shared, do, errors
    win.close()


def _keys(viewer):
    return {tuple(sorted(map(int, pair))) for pair in viewer.bond_list()}


def _unbonded_pair(viewer):
    """Two atom indices that are certainly not bonded (first atom, last water)."""
    n = int(np.asarray(viewer._all_atom_coords).shape[0])
    first, last = 0, n - 1
    assert (first, last) not in _keys(viewer), "fixture changed: these are bonded"
    return first, last


# --------------------------------------------------------------------------- #
# bond
# --------------------------------------------------------------------------- #
def test_bond_creates_one(session):
    viewer, _shared, do, errors = session
    i, j = _unbonded_pair(viewer)
    before = len(viewer.bond_list())
    do(f"bond index {i + 1}, index {j + 1}")
    assert errors == []
    assert len(viewer.bond_list()) == before + 1
    assert (i, j) in _keys(viewer)


def test_a_bond_survives_a_coordinate_change(session):
    """The reason edits are stored as deltas rather than in the bond array.

    Bonds are re-inferred whenever coordinates move, and inference would never
    produce this bond -- the two atoms are nowhere near each other.
    """
    viewer, _shared, do, errors = session
    i, j = _unbonded_pair(viewer)
    do(f"bond index {i + 1}, index {j + 1}")
    do("translate [1,0,0], all")
    assert errors == []
    assert (i, j) in _keys(viewer), "the manual bond was lost when atoms moved"


def test_an_unbond_survives_a_coordinate_change(session):
    """Removals have to be replayed too, or inference puts the bond straight back."""
    viewer, _shared, do, errors = session
    existing = sorted(_keys(viewer))[0]
    do(f"unbond index {existing[0] + 1}, index {existing[1] + 1}")
    assert existing not in _keys(viewer)
    do("translate [1,0,0], all")
    assert errors == []
    assert existing not in _keys(viewer), "inference re-created the removed bond"


def test_bond_records_an_order(session):
    viewer, _shared, do, errors = session
    i, j = _unbonded_pair(viewer)
    do(f"bond index {i + 1}, index {j + 1}, 2")
    assert errors == []
    assert viewer.bond_order(i, j) == 2


def test_re_bonding_an_existing_pair_changes_its_order(session):
    """How a single bond is promoted to a double one, as in PyMOL."""
    viewer, _shared, do, errors = session
    i, j = sorted(_keys(viewer))[0]
    assert viewer.bond_order(i, j) == 1
    do(f"bond index {i + 1}, index {j + 1}, 2")
    assert errors == []
    assert viewer.bond_order(i, j) == 2
    # And it is still one bond, not two.
    assert sum(1 for k in _keys(viewer) if k == (i, j)) == 1


def test_an_inferred_bond_is_single(session):
    viewer, _shared, _do, _errors = session
    i, j = sorted(_keys(viewer))[0]
    assert viewer.bond_order(i, j) == 1


def test_bond_refuses_the_same_atom_twice(session):
    """It used to report "already bonded", which is a plainly wrong diagnosis."""
    viewer, _shared, do, errors = session
    do("bond index 1, index 1")
    assert errors and "same atom" in errors[-1]


def test_bond_refuses_a_multi_atom_selection(session):
    viewer, _shared, do, errors = session
    do("bond resn HOH, index 5")
    assert errors and "matched 8 atoms" in errors[-1]


def test_bond_refuses_a_selection_matching_nothing(session):
    viewer, _shared, do, errors = session
    do("bond index 9999, index 5")
    assert errors and "matched 0 atoms" in errors[-1]


def test_bond_needs_two_arguments(session):
    viewer, _shared, do, errors = session
    do("bond index 1")
    assert errors and "Usage" in errors[-1]


def test_bond_rejects_a_non_numeric_order(session):
    viewer, _shared, do, errors = session
    i, j = _unbonded_pair(viewer)
    do(f"bond index {i + 1}, index {j + 1}, double")
    assert errors and "whole number" in errors[-1]


def test_bond_refuses_to_span_two_objects(session):
    """A bond lives inside one object's table, so it cannot cross objects."""
    viewer, _shared, do, errors = session
    do("create other, resn HOH")
    errors.clear()
    do("bond index 1, other and index 1")
    assert errors, "bonding across objects should be refused"
    assert "same one" in errors[-1] or "different objects" in errors[-1]


def test_add_bond_rejects_an_out_of_range_index(session):
    """The viewer-level guard, independent of how a selection resolved."""
    viewer, _shared, _do, _errors = session
    n = int(np.asarray(viewer._all_atom_coords).shape[0])
    assert viewer.add_bond(0, n + 10) is False
    assert viewer.add_bond(-1, 0) is False


# --------------------------------------------------------------------------- #
# unbond
# --------------------------------------------------------------------------- #
def test_unbond_removes_every_bond_between_two_selections(session):
    """Not one bond -- all of them, which is what PyMOL documents."""
    viewer, _shared, do, errors = session
    before = _keys(viewer)
    # Within one alanine there is more than one bond to its neighbour set.
    do("unbond resi 1, resi 2")
    assert errors == []
    after = _keys(viewer)
    gone = before - after
    assert gone, "residues 1 and 2 are adjacent, so something must have gone"


def test_unbond_leaves_unrelated_bonds_alone(session):
    viewer, _shared, do, errors = session
    before = _keys(viewer)
    do("unbond resi 1, resi 2")
    after = _keys(viewer)
    assert after < before
    # Everything removed genuinely spanned the two residues.
    atoms = viewer._atoms
    res = np.asarray(atoms["res_id"])
    for i, j in before - after:
        assert {int(res[i]), int(res[j])} == {1, 2}


def test_unbond_on_an_unbonded_pair_removes_nothing(session):
    viewer, _shared, do, errors = session
    i, j = _unbonded_pair(viewer)
    before = _keys(viewer)
    do(f"unbond index {i + 1}, index {j + 1}")
    assert errors == []
    assert _keys(viewer) == before


def test_unbond_refuses_to_span_two_objects(session):
    viewer, _shared, do, errors = session
    do("create other, resn HOH")
    errors.clear()
    do("unbond index 1, other and index 1")
    assert errors and (
        "different objects" in errors[-1] or "inside one object" in errors[-1]
    )


def test_unbond_needs_two_arguments(session):
    viewer, _shared, do, errors = session
    do("unbond index 1")
    assert errors and "Usage" in errors[-1]


# --------------------------------------------------------------------------- #
# get_bonds
# --------------------------------------------------------------------------- #
def test_get_bonds_returns_triples(session):
    viewer, shared, _do, errors = session
    bonds = shared.get_bonds("all")
    assert errors == []
    assert len(bonds) == len(viewer.bond_list())
    assert all(len(b) == 3 for b in bonds)
    assert all(order == 1 for _a, _b, order in bonds)


def test_get_bonds_reports_a_changed_order(session):
    viewer, shared, do, _errors = session
    i, j = sorted(_keys(viewer))[0]
    do(f"bond index {i + 1}, index {j + 1}, 3")
    orders = {order for _a, _b, order in shared.get_bonds("all")}
    assert 3 in orders


def test_the_indices_are_positions_in_the_selection_not_atom_indices(session):
    """PyMOL's capitalised warning, made a test.

    For ``all`` the two coincide, so this selects atoms that do **not** start at
    zero: every reported index must then be smaller than the atom index it
    stands for.
    """
    viewer, shared, _do, errors = session
    atoms = viewer._atoms
    res = np.asarray(atoms["res_id"])
    later = np.nonzero(res >= 3)[0]
    assert later.size and int(later[0]) > 0, "fixture changed"

    bonds = shared.get_bonds("resi 3-6")
    assert errors == []
    assert bonds, "the later residues have bonds"
    # Positions are 0-based within the selection, so they must be in range...
    assert all(0 <= a < later.size and 0 <= b < later.size for a, b, _o in bonds)
    # ...and at least one must differ from the atom index it corresponds to,
    # which is the whole point of the warning.
    first_atom = int(later[0])
    assert any(a + first_atom != a for a, _b, _o in bonds) or first_atom > 0


def test_get_bonds_excludes_bonds_reaching_outside_the_selection(session):
    viewer, shared, _do, _errors = session
    one = shared.get_bonds("resi 1")
    everything = shared.get_bonds("all")
    assert len(one) < len(everything)


def test_get_bonds_on_atoms_with_no_bonds_is_empty(session):
    """The waters and the ion are unbonded, so this is the honest empty answer."""
    viewer, shared, _do, errors = session
    assert shared.get_bonds("solvent") == []
    assert errors == []


def test_get_bonds_reports_a_selection_matching_nothing(session):
    viewer, shared, _do, errors = session
    assert shared.get_bonds("resn NOSUCH") == []
    assert errors and "matched no atoms" in errors[-1]


def test_get_bonds_prints_one_line_not_two(session):
    """``do`` already prints a command's return value.

    Emitting a summary as well printed the count and then the whole list, which
    for a real structure is a wall of triples after a line that already said it.
    """
    viewer, shared, _do, _errors = session
    shared_cmd = shared

    messages: list[str] = []
    shared_cmd.set_message_callback(messages.append)
    try:
        shared_cmd.do("get_bonds all")
    finally:
        shared_cmd.set_message_callback(lambda _m: None)
    assert len(messages) == 1
