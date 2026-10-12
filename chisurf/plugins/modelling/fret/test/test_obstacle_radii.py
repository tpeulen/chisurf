"""The FRET plugin's AV obstacles are IMP's radii times IMP.bff's one scale.

Every AV is grown against an obstacle surface built from per-atom radii. There
is one radius set for accessible volumes (owner, 2026-10-12): IMP's radius for
the atom's residue and name, times ``AV_DEFAULT_RADIUS_SCALE``. The plugin used
to carry FPS's Bondi element table instead, and before that read ``" CA "`` as
calcium (RF-477); a radius keyed by residue and atom name cannot make that
mistake, and the shipped screening structure pins it.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.structure.av import radii as av_radii

from ..core.av import _cached_pdb_records, load_structure_with_vdw

_SCREENING_PDB = (
    pathlib.Path(__file__).resolve().parents[5]
    / "examples"
    / "4w_junction"
    / "fps_test_data"
    / "test_screening"
    / "hivrt_straight_allTraj04791.pdb"
)


def _pdb():
    if not _SCREENING_PDB.is_file():
        pytest.skip(f"missing test structure {_SCREENING_PDB}")
    return str(_SCREENING_PDB)


def test_obstacles_are_imp_radii_times_the_scale():
    """Each row is IMP's radius for that residue and atom name, times the scale."""
    import IMP.bff

    path = _pdb()
    xyzr = load_structure_with_vdw(path)
    records = IMP.bff.read_pdb_records(path)
    assert xyzr.shape == (len(records), 4)
    expected = av_radii.obstacle_radii(
        [r.res_name for r in records], [r.atom_name for r in records]
    )
    np.testing.assert_allclose(xyzr[:, 3], expected, rtol=0, atol=1e-12)
    assert av_radii.radius_scale() == IMP.bff.AV_DEFAULT_RADIUS_SCALE


def test_alpha_carbons_are_carbons_not_calcium():
    """``" CA "`` is IMP's alpha carbon (CHARMM CT1, 2.275 A), never calcium."""
    import IMP.bff

    path = _pdb()
    xyzr = load_structure_with_vdw(path)
    records = IMP.bff.read_pdb_records(path)
    names = np.array([r.atom_name for r in records])
    residues = np.array([r.res_name for r in records])
    assert len(names) == len(xyzr)
    scale = av_radii.radius_scale()
    # glycine's alpha carbon is CT2 (2.175 A); every other one CT1 or CP1.
    # The file's Amber histidines (HIE) are a name IMP does not know, so they
    # take IMP's 1.7 A default -- as read_pdb gives them.
    ca = xyzr[(names == "CA") & ~np.isin(residues, ["GLY", "HIE"]), 3]
    assert np.allclose(xyzr[(names == "CA") & (residues == "HIE"), 3], 1.7 * scale)
    assert len(ca) > 0
    assert np.allclose(ca, 2.275 * scale)


def test_records_align_with_the_obstacles():
    """The identity records and the obstacle rows are the same atoms, in order."""
    path = _pdb()
    xyzr = load_structure_with_vdw(path)
    records = _cached_pdb_records(path)
    assert len(records) == len(xyzr)
    xyz = np.array([r[3:6] for r in records])
    np.testing.assert_allclose(xyz, xyzr[:, :3], atol=1e-9)
