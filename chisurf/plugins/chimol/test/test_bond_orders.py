"""Bond orders from residue nomenclature, and the second line they draw.

The analysis and the geometry; nothing is wired into the renderer yet, so these
are the only tests of it. See ``okf/plugins/pymol-parity.md`` for what remains.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.analysis.bond_orders import (
    DOUBLE_BONDS,
    assign_bond_orders,
)
from chisurf.plugins.chimol.chimol.geometry.wireframe import (
    bond_line_segments,
    valence_offsets,
)

PDB = (
    pathlib.Path(__file__).resolve().parents[4]
    / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
)

ATOM_DTYPE = np.dtype([
    ("atom_name", "U4"), ("res_name", "U4"), ("res_id", "i4"),
    ("chain", "U2"), ("element", "U2"), ("xyz", "f8", 3),
])


def _atoms(rows):
    return np.array(
        [(n, r, i, "A", e, (0.0, 0.0, float(k)))
         for k, (n, r, i, e) in enumerate(rows)],
        dtype=ATOM_DTYPE,
    )


def test_the_backbone_carbonyl_is_double():
    atoms = _atoms([("C", "ALA", 1, "C"), ("O", "ALA", 1, "O")])
    assert assign_bond_orders(atoms, [(0, 1)]).tolist() == [2]


def test_only_one_oxygen_of_a_carboxylate_is_double():
    """The same bookkeeping choice the formal-charge table makes.

    ``OD1`` takes the double bond and ``OD2`` the negative charge; doubling both
    would give the carbon five bonds.
    """
    atoms = _atoms([
        ("CG", "ASP", 1, "C"), ("OD1", "ASP", 1, "O"), ("OD2", "ASP", 1, "O"),
    ])
    assert assign_bond_orders(atoms, [(0, 1), (0, 2)]).tolist() == [2, 1]


def test_the_guanidinium_partner_is_forced_single():
    """PyMOL sets ``CZ=NH1`` and then forces ``CZ-NH2`` back down (PYMOL-5019).

    They are one resonance hybrid, and the bookkeeping has to pick one.
    """
    atoms = _atoms([
        ("CZ", "ARG", 1, "C"), ("NH1", "ARG", 1, "N"), ("NH2", "ARG", 1, "N"),
    ])
    assert assign_bond_orders(atoms, [(0, 1), (0, 2)]).tolist() == [2, 1]


def test_histidine_follows_the_tautomer_in_the_residue_name():
    """``CE1=ND1`` for HIS, ``CE1=NE2`` for the ND1-protonated HID."""
    for residue, expect in (("HIS", [2, 1]), ("HID", [1, 2])):
        atoms = _atoms([
            ("CE1", residue, 1, "C"),
            ("ND1", residue, 1, "N"),
            ("NE2", residue, 1, "N"),
        ])
        assert assign_bond_orders(atoms, [(0, 1), (0, 2)]).tolist() == expect


def test_a_ligand_gets_no_double_bonds():
    """An untemplated residue has no entry, and PyMOL is in the same position:
    for a PDB ligand it has bond orders only from a format that carries them."""
    atoms = _atoms([("C1", "NAG", 1, "C"), ("O5", "NAG", 1, "O")])
    assert assign_bond_orders(atoms, [(0, 1)]).tolist() == [1]


def test_the_rule_does_not_reach_across_residues():
    """Two neighbouring glutamates both have a ``CD`` and an ``OE1``."""
    atoms = _atoms([("CD", "GLU", 1, "C"), ("OE1", "GLU", 2, "O")])
    assert assign_bond_orders(atoms, [(0, 1)]).tolist() == [1]


def test_an_aromatic_ring_alternates():
    """Kekule, not a delocalised circle -- and no carbon carries two doubles."""
    for residue in ("PHE", "TYR"):
        pairs = DOUBLE_BONDS[residue]
        atoms_in_doubles = [name for pair in pairs for name in pair]
        assert len(atoms_in_doubles) == len(set(atoms_in_doubles)), residue


def test_a_real_protein_is_mostly_backbone_carbonyls():
    """148L: 258 double bonds of 1384, and every residue's C=O among them."""
    from chisurf.plugins.chimol.chimol.analysis.clashes import VDW_RADII
    from chisurf.plugins.chimol.chimol.geometry.bonds import (
        build_bond_pairs_by_element,
    )
    from chisurf.plugins.chimol.chimol.io.structure import _parse_pdb_backbone

    if not PDB.exists():
        pytest.skip("no 148l fixture")
    atoms = _parse_pdb_backbone(str(PDB)).atoms
    elements = np.char.upper(np.char.strip(atoms["element"].astype(str)))
    radii = np.array([VDW_RADII.get(e, 1.7) for e in elements])
    bonds = build_bond_pairs_by_element(
        np.asarray(atoms["xyz"], dtype=float), radii, elements, cutoff=0.35
    )

    orders = assign_bond_orders(atoms, bonds)

    assert int((orders == 2).sum()) == 258
    names = np.char.upper(np.char.strip(atoms["atom_name"].astype(str)))
    carbonyls = sum(
        1 for (i, j), order in zip(bonds, orders)
        if order == 2 and {str(names[i]), str(names[j])} == {"C", "O"}
    )
    assert carbonyls > 150, "the backbone carbonyls are most of them"


# --------------------------------------------------------------------------- #
# The second line
# --------------------------------------------------------------------------- #
def _benzene():
    pts = np.array([
        [1.4 * np.cos(a), 1.4 * np.sin(a), 0.0]
        for a in np.arange(6) * np.pi / 3
    ])
    bonds = np.array([[k, (k + 1) % 6] for k in range(6)])
    orders = np.array([2 if k % 2 == 0 else 1 for k in range(6)])
    return pts, bonds, orders


def test_the_second_line_goes_inside_the_ring():
    """PyMOL's ``valence_mode 1``: beside the bond, towards the molecule.

    Inside a ring that reads as a Kekule structure. Offsetting the other way
    gives two rails around the outside of the ring, which reads as a mistake.
    """
    pts, bonds, orders = _benzene()
    offsets = valence_offsets(pts, bonds, orders)

    mid = 0.5 * (pts[bonds[:, 0]] + pts[bonds[:, 1]])
    double = orders == 2
    assert np.all(
        np.linalg.norm((mid + offsets)[double], axis=1)
        < np.linalg.norm(mid[double], axis=1)
    )
    assert np.allclose(offsets[~double], 0.0), "a single bond is not offset"


def test_a_single_bonded_wireframe_is_unchanged():
    """Passing no orders must produce exactly what it always produced."""
    pts, bonds, orders = _benzene()
    plain, _ = bond_line_segments(pts, bonds, None)
    same, _ = bond_line_segments(pts, bonds, None, orders=np.ones(6, dtype=int))
    assert np.array_equal(plain, same)


def test_every_double_bond_adds_one_line():
    pts, bonds, orders = _benzene()
    plain, _ = bond_line_segments(pts, bonds, None)
    doubled, _ = bond_line_segments(pts, bonds, None, orders=orders)
    # Four vertices per extra line, because the halves keep their own colours.
    assert doubled.shape[0] == plain.shape[0] + 4 * int((orders == 2).sum())


def test_the_extra_lines_carry_the_bond_s_colours():
    pts, bonds, orders = _benzene()
    colours = np.tile(np.array([[1.0, 0.0, 0.0, 1.0]]), (6, 1))
    vertices, out = bond_line_segments(pts, bonds, colours, orders=orders)
    assert out is not None
    assert out.shape[0] == vertices.shape[0]


def test_a_bond_with_no_neighbours_still_offsets_somewhere():
    """A diatomic has no plane to choose, and any perpendicular will do --
    but the line must not land on top of the bond it is doubling."""
    pts = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 1.2]])
    offsets = valence_offsets(pts, np.array([[0, 1]]), np.array([2]))
    assert offsets is not None
    assert np.linalg.norm(offsets[0]) > 1e-6
    assert abs(float(offsets[0] @ np.array([0.0, 0.0, 1.0]))) < 1e-9
