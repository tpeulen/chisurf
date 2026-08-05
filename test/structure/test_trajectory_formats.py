"""Opening DCD and XTC trajectories through :class:`TrajectoryFile`.

The coordinates come from ChiSurf's own codecs
(:mod:`chisurf.core.fio.trajectory`), which are tested against reference files
elsewhere. What matters here is the wiring: that the loader reaches those
codecs, pairs them with a topology, and refuses the cases where it cannot.

One thing to know before reading the assertions. ``TrajectoryFile`` computes an
RMSD in its constructor, and ``mdtraj.rmsd`` **centres its inputs in place** —
so every trajectory this class loads comes back recentred, by up to several
nanometres. That is long-standing behaviour for every format, not something the
DCD/XTC path introduced, and it is why the comparisons below put the reference
through the same treatment rather than comparing against the file's own
coordinates.
"""

from __future__ import annotations

import pathlib
import tempfile

import numpy as np
import pytest

DATA = pathlib.Path(__file__).resolve().parents[1] / "data/atomic_coordinates/trajectory"
TOPOLOGY = DATA / "h5-file/topol.pdb"
DCD = DATA / "dcd/hgbp1_transition.dcd"
XTC = DATA / "xtc/hgbp1_transition.xtc"


@pytest.fixture
def trajectory_file():
    from chisurf.core.structure.trajectory import TrajectoryFile
    return TrajectoryFile


def _reference(path, kind):
    """Load *path* with the reference reader and apply the same centring."""
    import mdtraj as md

    top = md.load_topology(str(TOPOLOGY))
    traj = md.load_dcd(str(path), top=top) if kind == "dcd" else md.load_xtc(str(path), top=top)
    md.rmsd(traj, traj, 0)          # centres in place, as the loader's does
    return traj.xyz


@pytest.mark.parametrize("path, kind, atol", [
    # XTC stores nanometres, which is what the loader wants, so nothing is
    # converted and the agreement is exact. DCD stores Angstrom and is divided
    # by ten on the way in; that float32 division is the entire difference, and
    # a tolerance here is honest rather than slack. The codecs themselves are
    # checked bit-exactly against reference files in test/fio/.
    (DCD, "dcd", 1e-5),
    (XTC, "xtc", 0.0),
])
def test_a_coordinate_trajectory_loads_with_a_topology(trajectory_file, path, kind, atol):
    pytest.importorskip("mdtraj")
    traj = trajectory_file(str(path), topology=str(TOPOLOGY))
    assert traj.xyz.shape == (3, 5235, 3)
    assert traj.topology.n_atoms == 5235
    reference = _reference(path, kind)
    if atol == 0.0:
        np.testing.assert_array_equal(traj.xyz, reference)
    else:
        np.testing.assert_allclose(traj.xyz, reference, rtol=0, atol=atol)


def test_stride_reaches_the_reader(trajectory_file):
    traj = trajectory_file(str(DCD), topology=str(TOPOLOGY), stride=2)
    assert traj.xyz.shape[0] == 2


def test_atom_indices_subset_the_topology_too(trajectory_file):
    # Selecting atoms without subsetting the topology leaves a trajectory whose
    # atom names belong to different atoms -- wrong silently, not loudly.
    traj = trajectory_file(str(DCD), topology=str(TOPOLOGY), atom_indices=list(range(10)))
    assert traj.xyz.shape[1] == 10
    assert traj.topology.n_atoms == 10


def test_a_trajectory_without_a_topology_is_refused(trajectory_file):
    # DCD and XTC store coordinates only. Guessing a topology is not possible,
    # and proceeding without one would produce a trajectory with no atom names.
    with pytest.raises(ValueError, match="coordinates only"):
        trajectory_file(str(DCD))


def test_a_topology_that_does_not_match_is_refused(trajectory_file):
    pytest.importorskip("mdtraj")
    import mdtraj as md

    with tempfile.TemporaryDirectory() as tmp:
        small = pathlib.Path(tmp) / "ten_atoms.pdb"
        md.load(str(TOPOLOGY)).atom_slice(range(10)).save_pdb(str(small))
        with pytest.raises(ValueError, match="atoms but"):
            trajectory_file(str(DCD), topology=str(small))


def test_an_unreadable_suffix_is_refused(trajectory_file):
    # Previously anything that was not .pdb or .h5 fell through to a branch
    # that never set the trajectory, and failed later with an AttributeError
    # far from the cause.
    with pytest.raises(ValueError, match="expected .pdb"):
        trajectory_file("trajectory.bogus", topology=str(TOPOLOGY))
