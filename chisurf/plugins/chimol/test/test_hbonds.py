"""Polar contacts: the geometry, the typing, and a check against reality.

The geometry is transcribed from ``ObjectMoleculeTestHBond``, so the tests here
assert the *curve* it is supposed to produce rather than the constants it uses.
The curve is the part a reader loses: the donor--acceptor cutoff is not one
number but slides from ``h_bond_cutoff_center`` head-on down to
``h_bond_cutoff_edge`` at the maximum angle, and the two names read backwards
from what they do.

The ground truth is the last section. ``hGBP1_closed.pdb`` carries its
hydrogens, so the finder can be asked the same question twice -- once with them
and once with them stripped -- and the answers compared. That is the only check
that says anything about whether the *chemistry* is right rather than the
arithmetic: the hydrogen-less path has to invent every hydrogen it uses.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.plugins.chimol.chimol.analysis.hbonds import (
    HBond,
    HBondCriteria,
    find_hydrogen_bonds,
    type_atoms,
)

_PDB = pathlib.Path(__file__).resolve().parents[4] / "test" / "data" / (
    "atomic_coordinates"
) / "pdb_files"


def _atoms(*rows) -> np.ndarray:
    """A minimal structured atom array: ``(name, resn, resi, element, xyz)``."""
    dtype = np.dtype([
        ("atom_name", "U4"), ("res_name", "U4"), ("res_id", "i4"),
        ("element", "U2"), ("xyz", "f8", 3),
    ])
    return np.array(
        [(n, r, i, e, tuple(v)) for n, r, i, e, v in rows], dtype=dtype
    )


def _read(name: str):
    """A fixture PDB with its bonds, keeping waters and ligands."""
    from chisurf.core.fio.structure.coordinates import read_coordinates
    from chisurf.plugins.chimol.chimol.geometry.bonds import (
        build_bond_pairs_by_element,
    )

    path = _PDB / name
    if not path.exists():
        pytest.skip(f"no {name} fixture")
    atoms = read_coordinates(
        str(path), keep_water=True, only_standard_residues=False
    )
    elements = np.char.strip(np.asarray(atoms["element"]).astype(str))
    bonds = build_bond_pairs_by_element(
        np.asarray(atoms["xyz"], dtype=float),
        np.asarray(atoms["radius"], dtype=float),
        elements,
    )
    return atoms, bonds


# --------------------------------------------------------------------------- #
# The criteria are one curve, not six numbers
# --------------------------------------------------------------------------- #
def test_the_cutoff_slides_from_center_to_edge():
    """At zero angle the cutoff is ``center``; at the maximum it is ``edge``.

    Read as two independent distances -- which the names invite -- the
    interpolation is dead code and every contact is tested at 3.6 A.
    """
    hbc = HBondCriteria()
    # curve(0) = 0 -> cutoff = center; curve(max_angle) = 1 -> cutoff = edge.
    for angle, expected in ((0.0, hbc.cutoff_center), (hbc.max_angle, hbc.cutoff_edge)):
        curve = (
            (angle ** hbc.power_a) * hbc.factor_a
            + (angle ** hbc.power_b) * hbc.factor_b
        )
        cutoff = hbc.cutoff_edge * curve + hbc.cutoff_center * (1.0 - curve)
        assert cutoff == pytest.approx(expected, abs=1e-6)


def test_the_curve_is_monotone_between_the_two_ends():
    """A bent hydrogen bond is never allowed to be *longer* than a straight one."""
    hbc = HBondCriteria()
    angles = np.linspace(0.0, hbc.max_angle, 64)
    curve = (angles ** hbc.power_a) * hbc.factor_a + (angles ** hbc.power_b) * hbc.factor_b
    cutoffs = hbc.cutoff_edge * curve + hbc.cutoff_center * (1.0 - curve)
    assert np.all(np.diff(cutoffs) <= 1e-9)


def test_a_zero_edge_flattens_the_curve_to_a_plain_distance():
    """PyMOL's own escape hatch, and the branch that reads it."""
    from chisurf.plugins.chimol.chimol.analysis.hbonds import _test_hbond

    hbc = HBondCriteria(cutoff_edge=0.0)
    don_to_acc = np.array([3.5, 0.0, 0.0])
    don_to_h = np.array([1.0, 0.0, 0.0])
    h_to_acc = don_to_acc - don_to_h
    assert _test_hbond(don_to_acc, don_to_h, h_to_acc, None, hbc)
    assert not _test_hbond(
        don_to_acc * 1.1, don_to_h, don_to_acc * 1.1 - don_to_h, None, hbc
    )


def test_a_hydrogen_pointing_away_is_rejected():
    """The A-D-H angle test: 63 degrees is the limit, not 90."""
    from chisurf.plugins.chimol.chimol.analysis.hbonds import _test_hbond

    hbc = HBondCriteria()
    don_to_acc = np.array([3.0, 0.0, 0.0])
    for degrees, accepted in ((0.0, True), (60.0, True), (70.0, False), (120.0, False)):
        radians = np.radians(degrees)
        don_to_h = np.array([np.cos(radians), np.sin(radians), 0.0])
        assert _test_hbond(
            don_to_acc, don_to_h, don_to_acc - don_to_h, None, hbc
        ) is accepted, degrees


def test_the_cone_rejects_a_hydrogen_behind_the_acceptor():
    """``h_bond_cone``: an acceptor does not accept from behind its neighbours."""
    from chisurf.plugins.chimol.chimol.analysis.hbonds import _test_hbond

    hbc = HBondCriteria()
    don_to_acc = np.array([3.0, 0.0, 0.0])
    don_to_h = np.array([1.0, 0.0, 0.0])
    h_to_acc = don_to_acc - don_to_h
    # Lone pairs pointing back at the hydrogen: accepted.
    assert _test_hbond(don_to_acc, don_to_h, h_to_acc, np.array([-1.0, 0.0, 0.0]), hbc)
    # Lone pairs pointing away: the hydrogen is behind the acceptor.
    assert not _test_hbond(don_to_acc, don_to_h, h_to_acc, np.array([1.0, 0.0, 0.0]), hbc)


# --------------------------------------------------------------------------- #
# Typing
# --------------------------------------------------------------------------- #
def test_a_backbone_carbonyl_accepts_but_does_not_donate():
    """Where valence counting goes wrong, and why the template is used.

    Counting free valences makes every carbonyl oxygen a donor, because a
    double bond looks like a free valence when no bond orders are known.
    """
    atoms = _atoms(
        ("N", "ALA", 1, "N", (0.0, 0.0, 0.0)),
        ("CA", "ALA", 1, "C", (1.4, 0.0, 0.0)),
        ("C", "ALA", 1, "C", (2.0, 1.4, 0.0)),
        ("O", "ALA", 1, "O", (3.2, 1.6, 0.0)),
    )
    bonds = np.array([[0, 1], [1, 2], [2, 3]])
    typing = type_atoms(atoms, bonds)
    assert typing.acceptor[3] and not typing.donor[3], "carbonyl O donated"
    assert typing.donor[0] and not typing.acceptor[0], "backbone N did not donate"


def test_a_serine_hydroxyl_both_donates_and_accepts():
    atoms = _atoms(
        ("CB", "SER", 1, "C", (0.0, 0.0, 0.0)),
        ("OG", "SER", 1, "O", (1.4, 0.0, 0.0)),
    )
    typing = type_atoms(atoms, np.array([[0, 1]]))
    assert typing.donor[1] and typing.acceptor[1]


def test_proline_does_not_donate():
    """A measured deviation from PyMOL, kept deliberately.

    PyMOL reads a proline nitrogen's three single bonds as a tertiary amine with
    a free valence, marks it a donor, and then invents a hydrogen for it.
    Proline has no amide hydrogen; the template says zero and that wins.
    """
    atoms = _atoms(
        ("N", "PRO", 2, "N", (0.0, 0.0, 0.0)),
        ("CA", "PRO", 2, "C", (1.4, 0.0, 0.0)),
        ("CD", "PRO", 2, "C", (-0.7, 1.3, 0.0)),
        ("C", "ALA", 1, "C", (-0.7, -1.3, 0.0)),
    )
    bonds = np.array([[0, 1], [0, 2], [0, 3]])
    typing = type_atoms(atoms, bonds)
    assert not typing.donor[0]


def test_a_water_oxygen_donates_and_accepts_without_its_hydrogens():
    atoms = _atoms(("O", "HOH", 1, "O", (0.0, 0.0, 0.0)))
    typing = type_atoms(atoms, np.zeros((0, 2), dtype=int))
    assert typing.donor[0] and typing.acceptor[0]


def test_an_untemplated_residue_is_reported_as_such():
    """The approximation has to be visible, or it reads as measured."""
    atoms = _atoms(
        ("C1", "LIG", 1, "C", (0.0, 0.0, 0.0)),
        ("O1", "LIG", 1, "O", (1.4, 0.0, 0.0)),
    )
    typing = type_atoms(atoms, np.array([[0, 1]]))
    assert not typing.templated.any()
    assert typing.acceptor[1]


# --------------------------------------------------------------------------- #
# The finder
# --------------------------------------------------------------------------- #
def test_a_straight_pair_at_three_angstrom_is_a_contact():
    atoms = _atoms(
        ("CB", "SER", 1, "C", (-1.4, 0.0, 0.0)),
        ("OG", "SER", 1, "O", (0.0, 0.0, 0.0)),
        ("O", "HOH", 2, "O", (3.0, 0.0, 0.0)),
    )
    bonds = np.array([[0, 1]])
    found = find_hydrogen_bonds(atoms, bonds, criteria=HBondCriteria())
    assert len(found) == 1
    assert found[0].distance == pytest.approx(3.0)


def test_the_same_pair_too_far_apart_is_not():
    atoms = _atoms(
        ("CB", "SER", 1, "C", (-1.4, 0.0, 0.0)),
        ("OG", "SER", 1, "O", (0.0, 0.0, 0.0)),
        ("O", "HOH", 2, "O", (4.2, 0.0, 0.0)),
    )
    assert find_hydrogen_bonds(atoms, np.array([[0, 1]])) == []


def test_bonded_neighbours_are_excluded():
    """``h_bond_exclusion``: a covalent bond is not a polar contact.

    Two atoms three bonds apart are inside the default exclusion, so no amount
    of good geometry makes them a contact.
    """
    atoms = _atoms(
        ("CB", "SER", 1, "C", (-1.4, 0.0, 0.0)),
        ("OG", "SER", 1, "O", (0.0, 0.0, 0.0)),
        ("O", "HOH", 2, "O", (3.0, 0.0, 0.0)),
        ("C1", "LIG", 3, "C", (1.5, 2.0, 0.0)),
    )
    # OG - CB - C1 - Owat: three bonds apart, inside the default exclusion of 3.
    chained = np.array([[0, 1], [0, 3], [3, 2]])
    assert find_hydrogen_bonds(atoms, chained) == []
    # The same coordinates with that path cut are a contact.
    assert find_hydrogen_bonds(atoms, np.array([[0, 1]]))


def test_masks_restrict_both_ends():
    atoms = _atoms(
        ("CB", "SER", 1, "C", (-1.4, 0.0, 0.0)),
        ("OG", "SER", 1, "O", (0.0, 0.0, 0.0)),
        ("O", "HOH", 2, "O", (3.0, 0.0, 0.0)),
    )
    bonds = np.array([[0, 1]])
    only_serine = np.array([False, True, False])
    assert find_hydrogen_bonds(atoms, bonds, only_serine, only_serine) == []
    assert len(find_hydrogen_bonds(atoms, bonds, only_serine, ~only_serine)) == 1


# --------------------------------------------------------------------------- #
# On a real structure
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def lysozyme():
    return _read("148l.pdb")


def test_the_helices_of_148l_hydrogen_bond_i_to_i_plus_four(lysozyme):
    """An alpha helix is *defined* by its N(i) to O(i-4) bonds.

    A finder that produced nothing here would still pass every unit test above,
    because the unit tests choose their own geometry.
    """
    atoms, bonds = lysozyme
    found = find_hydrogen_bonds(atoms, bonds)
    names = np.char.strip(np.asarray(atoms["atom_name"]).astype(str))
    res_ids = np.asarray(atoms["res_id"])

    helical = [
        b for b in found
        if names[b.donor] == "N" and names[b.acceptor] == "O"
        and res_ids[b.donor] - res_ids[b.acceptor] == 4
    ]
    assert len(helical) > 40, f"only {len(helical)} i->i-4 backbone bonds"


def test_a_salt_bridge_is_found(lysozyme):
    """Arginine to glutamate: the contact a figure is usually drawn for."""
    atoms, bonds = lysozyme
    found = find_hydrogen_bonds(atoms, bonds)
    names = np.char.strip(np.asarray(atoms["atom_name"]).astype(str))
    res = np.char.strip(np.asarray(atoms["res_name"]).astype(str))
    pairs = {
        (res[b.donor], names[b.donor], res[b.acceptor], names[b.acceptor])
        for b in found
    }
    assert any(
        d_res == "ARG" and d_name.startswith("NH") and a_res == "GLU"
        for d_res, d_name, a_res, _a_name in pairs
    )


def test_every_contact_is_between_a_donor_and_an_acceptor(lysozyme):
    atoms, bonds = lysozyme
    typing = type_atoms(atoms, bonds)
    for b in find_hydrogen_bonds(atoms, bonds, typing=typing):
        assert typing.donor[b.donor] and typing.acceptor[b.acceptor]
        assert isinstance(b, HBond)


def test_no_contact_is_longer_than_the_widest_cutoff(lysozyme):
    atoms, bonds = lysozyme
    hbc = HBondCriteria()
    for b in find_hydrogen_bonds(atoms, bonds, criteria=hbc):
        assert b.distance <= hbc.search_cutoff + 1e-6


# --------------------------------------------------------------------------- #
# Ground truth: the same protein with and without its hydrogens
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def hydrogenated():
    return _read("hGBP1_closed.pdb")


def test_stripping_the_hydrogens_keeps_almost_every_contact(hydrogenated):
    """The measurement that says the invented hydrogens are in the right place.

    Measured at the time of writing: 735 contacts with the hydrogens present,
    803 without, 729 shared -- **99.2 % recall** of the explicit-hydrogen
    answer. The 9 % extra are rotatable donors (hydroxyls, ammonium groups)
    whose real hydrogen points elsewhere while a placed one is free to aim at
    the acceptor, plus a handful of 3-10-like i->i+3 backbone pairs. That is the
    direction the error should go: a contact the geometry permits, drawn.
    """
    atoms, _bonds = hydrogenated
    elements = np.char.strip(np.asarray(atoms["element"]).astype(str))
    heavy = elements != "H"
    if not (~heavy).any():
        pytest.skip("fixture carries no hydrogens")

    from chisurf.plugins.chimol.chimol.geometry.bonds import (
        build_bond_pairs_by_element,
    )

    def run(subset):
        e = np.char.strip(np.asarray(subset["element"]).astype(str))
        b = build_bond_pairs_by_element(
            np.asarray(subset["xyz"], dtype=float),
            np.asarray(subset["radius"], dtype=float),
            e,
        )
        return find_hydrogen_bonds(subset, b)

    index = np.nonzero(heavy)[0]
    remap = {int(original): new for new, original in enumerate(index)}
    with_h = {
        tuple(sorted((remap[b.donor], remap[b.acceptor]))) for b in run(atoms)
    }
    without_h = {
        tuple(sorted((b.donor, b.acceptor))) for b in run(atoms[heavy])
    }
    assert with_h and without_h
    recall = len(with_h & without_h) / len(with_h)
    assert recall > 0.95, f"recall {recall:.1%}"
    # The hydrogen-less path is allowed to be generous, but not wildly so.
    assert len(without_h) < 1.25 * len(with_h)


def test_a_hydrogenated_structure_uses_its_real_hydrogens(hydrogenated):
    """Not the invented ones -- ``FindBestDonorH`` prefers a real hydrogen."""
    atoms, bonds = hydrogenated
    elements = np.char.strip(np.asarray(atoms["element"]).astype(str))
    if not (elements == "H").any():
        pytest.skip("fixture carries no hydrogens")
    found = find_hydrogen_bonds(atoms, bonds)
    real = sum(1 for b in found if b.hydrogen is not None)
    assert real / len(found) > 0.9, f"only {real}/{len(found)} used a real H"
