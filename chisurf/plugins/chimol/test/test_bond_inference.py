"""Bonds from radii, not from one global distance.

chimol inferred bonds with a single cutoff of 1.9 Å for every pair of atoms. A
single cutoff has to be wide enough for the longest real bond, which makes it wide
enough for a mere *contact* between two heavier atoms — and too narrow for the
longest ones. Both errors were live:

* a **disulfide is 2.05 Å**, so every S–S bond in every structure was missed;
* on hGBP1 (a model *with* hydrogens) the old rule produced 2278 bonds the new one
  does not, of which **2138 are hydrogen-to-hydrogen** — pairs that are never
  bonded — and most of the rest are hydrogen bonds at ~1.65 Å drawn as covalent.

Every bond-based feature inherited those: the stick and line representations drew
them, and ``bymol``, ``bound_to`` and ``extend`` walked across them.

The rule is transcribed from ``is_distance_bonded`` (``layer2/ObjectMolecule2.cpp``)::

    d = |v1 - v2| - (vdw1 + vdw2) / 2
    bonded  iff  d <= connect_cutoff + adjustment

with ``connect_cutoff`` 0.35, ``+0.2`` when either atom is sulfur, ``-0.2`` when
either is hydrogen, and never between two hydrogens.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.geometry.bonds import (
    CONNECT_CUTOFF,
    _build_bond_pairs,
    build_bond_pairs_by_element,
)

_PDB = pathlib.Path(__file__).resolve().parents[4] / "test" / "data" / (
    "atomic_coordinates"
) / "pdb_files"

#: Representative van der Waals radii, as the readers supply them.
_VDW = {"H": 1.2, "C": 1.7, "N": 1.55, "O": 1.52, "S": 1.8}


def _pair(element_a, element_b, distance):
    """Two atoms of the given elements, that far apart."""
    coords = np.array([[0.0, 0.0, 0.0], [float(distance), 0.0, 0.0]])
    radii = np.array([_VDW[element_a], _VDW[element_b]])
    elements = np.array([element_a, element_b])
    return coords, radii, elements


def _bonded(element_a, element_b, distance) -> bool:
    return build_bond_pairs_by_element(*_pair(element_a, element_b, distance)).shape[0] == 1


# --------------------------------------------------------------------------- #
# Real bonds are found
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "a, b, distance, what",
    [
        ("C", "C", 1.54, "a single carbon-carbon bond"),
        ("C", "C", 1.39, "an aromatic carbon-carbon bond"),
        ("C", "N", 1.33, "a peptide bond"),
        ("C", "O", 1.23, "a carbonyl"),
        ("C", "H", 1.09, "a carbon-hydrogen bond"),
        ("O", "H", 0.97, "a hydroxyl"),
        ("S", "S", 2.05, "a disulfide"),
        ("C", "S", 1.81, "a thioether"),
    ],
)
def test_a_real_bond_is_found(a, b, distance, what):
    assert _bonded(a, b, distance), what


def test_the_disulfide_the_old_rule_missed():
    """S-S is 2.05 A, beyond the old 1.9 A cutoff -- so none were ever drawn."""
    coords, radii, elements = _pair("S", "S", 2.05)
    assert _build_bond_pairs(coords, 1.9).shape[0] == 0        # the old rule
    assert build_bond_pairs_by_element(coords, radii, elements).shape[0] == 1


# --------------------------------------------------------------------------- #
# Contacts are not bonds
# --------------------------------------------------------------------------- #
def test_two_hydrogens_are_never_bonded():
    """PyMOL refuses the pair outright, whatever the distance."""
    assert not _bonded("H", "H", 0.74)
    assert not _bonded("H", "H", 1.8)


def test_a_hydrogen_bond_is_not_a_covalent_bond():
    """~1.8 A between an O and an H of another molecule."""
    assert not _bonded("O", "H", 1.8)
    assert _bonded("O", "H", 0.97)      # ...but the covalent one still is


def test_a_distant_pair_is_not_bonded():
    assert not _bonded("C", "C", 3.0)
    assert not _bonded("C", "N", 2.8)


def test_coincident_atoms_are_not_bonded():
    """A zero distance is a duplicate atom, not a bond."""
    assert not _bonded("C", "C", 0.0)


# --------------------------------------------------------------------------- #
# The adjustments
# --------------------------------------------------------------------------- #
def test_sulfur_reaches_further():
    """+0.2, which is what admits the 2.05 A disulfide."""
    # Same radii for both, at a distance inside sulfur's reach but outside the
    # plain cutoff -- otherwise the radii, not the adjustment, decide it.
    #   plain: 1.8 + 0.35 = 2.15     sulfur: 1.8 + 0.55 = 2.35
    coords = np.array([[0.0, 0.0, 0.0], [2.25, 0.0, 0.0]])
    radii = np.array([1.8, 1.8])
    assert build_bond_pairs_by_element(
        coords, radii, np.array(["S", "S"])
    ).shape[0] == 1
    assert build_bond_pairs_by_element(
        coords, radii, np.array(["C", "C"])
    ).shape[0] == 0


def test_hydrogen_reaches_less_far():
    """-0.2, so a hydrogen does not bond at the range a heavy atom would."""
    # 1.9 A: within reach for C-C (1.7 + 0.35 = 2.05), out of reach for C-H.
    assert _bonded("C", "C", 1.9)
    assert not _bonded("C", "H", 1.9)


def test_the_cutoff_is_pymols():
    assert CONNECT_CUTOFF == 0.35


def test_the_boundary_is_where_the_formula_puts_it():
    """d - (vdw1 + vdw2)/2 <= cutoff, evaluated exactly at the edge."""
    limit = (1.7 + 1.7) / 2 + CONNECT_CUTOFF        # 2.05 for carbon
    assert _bonded("C", "C", limit - 1e-6)
    assert not _bonded("C", "C", limit + 1e-3)


# --------------------------------------------------------------------------- #
# Shape and ordering
# --------------------------------------------------------------------------- #
def test_pairs_come_back_ordered():
    coords = np.array([[0.0, 0, 0], [1.5, 0, 0], [3.0, 0, 0]])
    radii = np.full(3, 1.7)
    bonds = build_bond_pairs_by_element(coords, radii, np.array(["C"] * 3))
    assert bonds.shape[1] == 2
    assert np.all(bonds[:, 0] < bonds[:, 1])


def test_a_single_atom_has_no_bonds():
    bonds = build_bond_pairs_by_element(
        np.zeros((1, 3)), np.array([1.7]), np.array(["C"])
    )
    assert bonds.shape == (0, 2)


def test_no_atoms_gives_no_bonds():
    bonds = build_bond_pairs_by_element(
        np.zeros((0, 3)), np.zeros(0), np.array([], dtype="U2")
    )
    assert bonds.shape == (0, 2)


# --------------------------------------------------------------------------- #
# On a real structure with hydrogens
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def hydrogenated():
    cs_struct = pytest.importorskip("chisurf.core.structure")
    from chimol.io.structure import _read_full_model

    path = _PDB / "hGBP1_closed.pdb"
    if not path.exists():
        pytest.skip("no hydrogenated test structure")
    return _read_full_model(cs_struct.Structure, path).atoms


def test_no_hydrogen_pair_survives(hydrogenated):
    """2138 of them did under the old rule."""
    atoms = hydrogenated
    elements = np.char.strip(atoms["element"].astype(str))
    bonds = build_bond_pairs_by_element(
        np.asarray(atoms["xyz"], dtype=float),
        np.asarray(atoms["radius"], dtype=float),
        elements,
    )
    is_hydrogen = np.isin(elements, ("H", "D"))
    assert not np.any(is_hydrogen[bonds[:, 0]] & is_hydrogen[bonds[:, 1]])


def test_every_bond_is_a_plausible_length(hydrogenated):
    """Nothing longer than a real covalent bond survives."""
    atoms = hydrogenated
    xyz = np.asarray(atoms["xyz"], dtype=float)
    bonds = build_bond_pairs_by_element(
        xyz,
        np.asarray(atoms["radius"], dtype=float),
        np.char.strip(atoms["element"].astype(str)),
    )
    lengths = np.linalg.norm(xyz[bonds[:, 1]] - xyz[bonds[:, 0]], axis=1)
    assert lengths.max() < 2.1
    assert lengths.min() > 0.5


def test_the_old_rule_produced_far_more(hydrogenated):
    """The improvement, measured: the difference is hydrogens and hydrogen bonds."""
    atoms = hydrogenated
    xyz = np.asarray(atoms["xyz"], dtype=float)
    old = _build_bond_pairs(xyz, 1.9)
    new = build_bond_pairs_by_element(
        xyz,
        np.asarray(atoms["radius"], dtype=float),
        np.char.strip(atoms["element"].astype(str)),
    )
    assert old.shape[0] > new.shape[0] * 1.1
