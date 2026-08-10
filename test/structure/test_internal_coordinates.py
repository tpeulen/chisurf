"""Backbone internal coordinates: what the residue walk must tolerate.

Every failure pinned here was a ``KeyError`` or ``ValueError`` raised while
building ``coord_i``, and every one of them fired on an ordinary crystallographic
PDB -- 148L, the structure this project uses as its protein fixture. The common
shape is code that decides which atoms a residue has from its *name* rather than
from the file, so this module works from a real X-ray entry rather than a
synthetic residue.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

import chisurf.core.math.linalg as linalg
from chisurf.core.structure.protein import ProteinCentroid

PDB_DIR = pathlib.Path(__file__).resolve().parents[1] / "data" / "atomic_coordinates" / "pdb_files"


@pytest.fixture(scope="module")
def lysozyme() -> ProteinCentroid:
    """T4 lysozyme (148L): an X-ray structure, so no hydrogens and many waters."""
    return ProteinCentroid(str(PDB_DIR / "148l.pdb"))


def test_a_structure_without_hydrogens_loads(lysozyme):
    """X-ray does not resolve hydrogens, so most PDB entries have none.

    The side-chain branch used to place an ``H`` for every residue that was not
    a proline, keyed on the residue *name*, and raised ``KeyError: 'H'`` on the
    first one. That rejected essentially every crystallographic structure.
    """
    assert lysozyme.n_residues == 164
    assert len(lysozyme.coord_i) > 0


def test_waters_and_heteroatoms_do_not_reach_the_backbone_walk(lysozyme):
    """``residue_dict`` holds every residue in the file, waters included.

    Those have no N/CA/C, and the walk used to die on ``KeyError: 'CA'``. They
    have to be skipped rather than merely tolerated: a water must not become the
    "previous residue" that the next real residue measures its dihedral against.
    """
    residues = list(lysozyme.residue_dict.values())
    assert any(not {"N", "CA", "C"} <= r.keys() for r in residues), (
        "fixture no longer contains a residue without a backbone -- this test "
        "would pass without exercising the skip"
    )
    placed = {int(i) for i in lysozyme.coord_i["i"]}
    for residue in residues:
        if not {"N", "CA", "C"} <= residue.keys():
            for atom in residue.values():
                assert int(atom["i"]) not in placed


def test_the_absent_atom_sentinel_is_not_used_as_a_lookup_key(lysozyme):
    """``l_c``/``l_ca``/``l_n``/``l_cb`` are pre-filled with -1 for "no such atom".

    Looking one up as though it were an atom index raised
    ``ValueError: -1 is not in list``. Every water contributes three sentinels,
    so this fired on the same structures as the case above.
    """
    assert int(np.min(lysozyme.l_c)) == -1, "fixture has no absent-atom sentinel"
    n = len(lysozyme.coord_i)
    for name in ("_phi_indices", "_omega_indices", "_psi_indices", "_chi_indices"):
        idx = getattr(lysozyme, name)
        assert len(idx) > 0
        assert all(0 <= int(i) < n for i in idx), name


def test_every_internal_coordinate_matches_its_own_four_atoms(lysozyme):
    """The stacked measurement must equal the per-row definition.

    ``coord_i`` stores the four atom indices beside the bond length, angle and
    dihedral, so each row can be re-derived from the coordinates it names. This
    checks the vectorised path against the definition rather than against a
    previous implementation, which is what makes it survive the next rewrite.
    The first three rows are partial by construction (the first residue has no
    predecessor) and are excluded.
    """
    ci = lysozyme.coord_i
    xyz = lysozyme.atoms["xyz"]
    names = ci.dtype.names
    i4, i3, i2, i1 = (np.asarray(ci[n]) for n in names[:4])
    bond, ang, dih = (np.asarray(ci[n]) for n in names[4:7])

    assert np.isfinite(bond).all() and np.isfinite(ang).all() and np.isfinite(dih).all()

    for k in range(3, len(ci)):
        v1, v2, v3, vn = xyz[i1[k]], xyz[i2[k]], xyz[i3[k]], xyz[i4[k]]
        assert float(linalg.norm3(v3 - vn)) == pytest.approx(bond[k], abs=1e-12)
        assert float(linalg.angle(v2, v3, vn)) == pytest.approx(ang[k], abs=1e-12)
        assert float(linalg.dihedral(v1, v2, v3, vn)) == pytest.approx(dih[k], abs=1e-12)


def test_angle_is_defined_for_collinear_points():
    """Three nearly collinear points overshoot ``|cos| = 1`` and gave ``NaN``.

    The normalised dot product reaches ``1 + 4.4e-16`` in double precision, and
    ``arccos`` of that is not a number. Collinear backbone atoms are ordinary,
    so this reached real structures. ``dihedral`` had always clamped; ``angle``
    had not.
    """
    a = np.array([0.0, 0.0, 0.0])
    b = np.array([1.0, 0.0, 0.0])
    assert float(linalg.angle(a, b, np.array([2.0, 0.0, 0.0]))) == pytest.approx(np.pi)
    assert float(linalg.angle(a, b, np.array([-1.0, 0.0, 0.0]))) == pytest.approx(0.0)

    rng = np.random.default_rng(0)
    for _ in range(2000):
        origin = rng.normal(size=3)
        direction = rng.normal(size=3)
        p = origin + direction * rng.uniform(0.5, 2.0) + rng.normal(size=3) * 1e-9
        assert np.isfinite(linalg.angle(origin + direction, origin, p))


def test_the_helpers_measure_a_stack_the_same_as_one_at_a_time():
    """The stacked form is the whole reason the walk is affordable; pin it."""
    rng = np.random.default_rng(3)
    a, b, c, d = (rng.normal(size=(64, 3)) for _ in range(4))

    np.testing.assert_array_equal(
        linalg.angle(a, b, c),
        np.array([linalg.angle(a[i], b[i], c[i]) for i in range(64)]),
    )
    np.testing.assert_array_equal(
        linalg.dihedral(a, b, c, d),
        np.array([linalg.dihedral(a[i], b[i], c[i], d[i]) for i in range(64)]),
    )
    np.testing.assert_array_equal(
        linalg.norm3(a), np.array([linalg.norm3(a[i]) for i in range(64)])
    )
