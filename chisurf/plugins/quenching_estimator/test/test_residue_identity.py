"""A residue is (chain, number, insertion code) — never a number alone.

PDB residue numbering restarts per chain, so `res_id` names a *set* of residues
in any multi-chain structure. Until 2026-07-28 everything that grouped atoms
into residues keyed on it: `Structure.residue_dict`, `residue_ids`, the CA/CB/
C/N/H lookup tables built from them, and `move_center_of_mass`. On
`tests/data/mc4r_dimer.cif` all **534** residue numbers occur in both chains, so
each entry held the union of two residues' atoms — whichever chain came second
overwrote the first, atom name by atom name — and one chain's side chains were
folded into the other chain's CB pseudo-atom.

The reader now assigns `residue_index` from the reader's residues, one per distinct
`(chain, res_id, insertion_code)`, and everything groups on that.

These tests assert the *mechanism*. The numeric consequence — the dimer's CB
centroid moving while a structure with no colliding numbers stays byte-identical
— is pinned in `tests/baselines/`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.structure import Structure

SINGLE = Path(__file__).parent / "148l.pdb"
DIMER = Path(__file__).parent / "data" / "mc4r_dimer.cif"


@pytest.fixture(scope="module")
def dimer():
    return Structure(str(DIMER), make_coarse=True, verbose=False)


@pytest.fixture(scope="module")
def dimer_all_atom():
    return Structure(str(DIMER), make_coarse=False, verbose=False)


def test_the_fixture_actually_has_colliding_residue_numbers(dimer_all_atom) -> None:
    """Otherwise this file proves nothing.

    A single-chain structure passes every assertion below under either the old
    or the new identity, which is exactly how the defect survived.
    """
    atoms = dimer_all_atom.atoms
    per_chain: dict[str, set[int]] = {chain: set() for chain in set(atoms["chain"])}
    for chain, res_id in zip(atoms["chain"], atoms["res_id"]):
        per_chain[chain].add(int(res_id))

    assert len(per_chain) > 1, "the dimer fixture has only one chain"
    chains = sorted(per_chain)
    shared = per_chain[chains[0]] & per_chain[chains[1]]
    assert len(shared) > 100, f"only {len(shared)} residue numbers collide"


def test_the_reader_gives_every_residue_its_own_index(dimer_all_atom) -> None:
    atoms = dimer_all_atom.atoms
    keys = {
        (str(c), int(r), str(i))
        for c, r, i in zip(atoms["chain"], atoms["res_id"], atoms["insertion_code"])
    }
    indices = {int(v) for v in atoms["residue_index"]}

    assert len(indices) == len(keys), (
        "residue_index must be one-to-one with (chain, res_id, insertion_code)"
    )
    # And it is dense and zero-based, so it can index an array of residues.
    assert indices == set(range(len(keys)))


def test_a_residue_index_never_spans_two_chains(dimer_all_atom) -> None:
    """The defect, stated directly."""
    atoms = dimer_all_atom.atoms
    chains_per_residue: dict[int, set[str]] = {}
    for index, chain in zip(atoms["residue_index"], atoms["chain"]):
        chains_per_residue.setdefault(int(index), set()).add(str(chain))

    mixed = {k: v for k, v in chains_per_residue.items() if len(v) > 1}
    assert not mixed, f"{len(mixed)} residues gather atoms from several chains"


def test_residue_dict_groups_by_identity_not_by_number(dimer) -> None:
    residues = dimer.residue_dict

    assert len(residues) == dimer.n_residues
    assert len(residues) > len(dimer.residue_ids), (
        "a dimer has more residues than distinct residue numbers; if these are "
        "equal the grouping has collapsed the chains again"
    )

    for key, atoms in residues.items():
        chains = {str(atom["chain"]) for atom in atoms.values()}
        assert len(chains) == 1, f"residue {key} mixes chains {chains}"


def test_each_chain_keeps_its_own_cb_for_a_shared_residue_number(dimer) -> None:
    """Two chains, one residue number, two distinct centres of mass."""
    atoms = dimer.atoms
    cb = atoms[atoms["atom_name"] == "CB"]
    by_number = Counter(int(r) for r in cb["res_id"])
    shared_number = next(number for number, count in by_number.items() if count > 1)

    matching = cb[cb["res_id"] == shared_number]
    assert len({str(c) for c in matching["chain"]}) == len(matching), (
        "the CBs sharing a residue number should be one per chain"
    )
    coords = np.asarray([row["coord"] for row in matching], dtype=float)
    separation = np.linalg.norm(coords[0] - coords[1])
    assert separation > 1.0, (
        f"the two chains' CB for residue {shared_number} are {separation:.3f} A "
        "apart; folding both side chains into one centre of mass pulls them "
        "together"
    )


def test_the_lookup_table_rows_line_up_with_the_residue_order(dimer) -> None:
    """`l_cb[i]` must be the CB of `residue_indices[i]`.

    These were built from two independently constructed orderings —
    `residue_dict` for the table, `set(res_id)` for the loop — which agreed only
    because both iterated a `set()` of small integers.
    """
    order = dimer.residue_indices
    assert len(order) == dimer.n_residues == len(dimer.l_cb)

    atoms = dimer.atoms
    checked = 0
    for row, residue_index in enumerate(order):
        cb_row = int(dimer.l_cb[row])
        if cb_row <= 0:
            continue
        assert int(atoms[cb_row]["residue_index"]) == residue_index
        checked += 1
    assert checked > 100, "too few CBs checked for this to mean anything"


def test_a_structure_without_colliding_numbers_is_unaffected() -> None:
    """The control.

    148L has chains A, E and S, but no residue *number* appears twice, so the
    old and new identities agree and nothing about it may move.
    """
    structure = Structure(str(SINGLE), make_coarse=True, verbose=False)
    atoms = structure.atoms
    cb = atoms[atoms["atom_name"] == "CB"]

    duplicated = [n for n, c in Counter(int(r) for r in cb["res_id"]).items() if c > 1]
    assert not duplicated, (
        "148L gained a duplicated residue number; it is the control precisely because it has none"
    )
    assert structure.n_residues == len(structure.residue_indices)
