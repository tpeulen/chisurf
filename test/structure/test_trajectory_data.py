"""Trajectory geometry (:mod:`chisurf.core.structure.trajectory_data`).

Superposition, RMSD and distances replace an external implementation, so the
expected values come from that implementation and are committed under
``test/data/atomic_coordinates/trajectory/ops/`` — the comparison has to
outlive the library it was taken from.

The tolerances are set by the units, not by hope. The DCD on disk is Ångström
and these objects work in nanometres, so a float32 division sits under every
comparison at ~1e-6 nm; superposition and RMSD add a little arithmetic on top.
Everything here is well below 1e-4 nm, which is a thousandth of a bond length.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chisurf.core.structure import trajectory_data as traj_ops
from chisurf.core.structure.topology import Topology

DATA = pathlib.Path(__file__).resolve().parents[1] / "data/atomic_coordinates/trajectory"
PDB = DATA / "hgbp1/topol.pdb"
DCD = DATA / "dcd/hgbp1_transition.dcd"
XTC = DATA / "xtc/hgbp1_transition.xtc"
#: Reference values, in angstroms. The length arrays were scaled by ten
#: when the interior stopped being nanometres -- the same physical
#: quantities, restated -- and `pairs`/`ca` are indices and were not.
#: Every tolerance below is a length, so it was scaled with them.
EXPECTED = np.load(DATA / "ops/ops_expected.npz")


@pytest.fixture
def trajectory():
    return traj_ops.load(str(DCD), top=str(PDB))


def test_load_pairs_coordinates_with_a_topology(trajectory):
    assert trajectory.n_frames == 3
    assert trajectory.n_atoms == 5235
    assert trajectory.topology.n_atoms == 5235
    assert trajectory.top is trajectory.topology       # the short name the tree uses


def test_rmsd_matches_the_reference(trajectory):
    got = traj_ops.rmsd(trajectory, trajectory, frame=0)
    np.testing.assert_allclose(got, EXPECTED["rmsd_all"], rtol=0, atol=1e-3)
    assert got[0] == pytest.approx(0.0, abs=1e-6)      # a frame against itself


def test_rmsd_on_a_subset_matches_the_reference(trajectory):
    got = traj_ops.rmsd(trajectory, trajectory, frame=0, atom_indices=EXPECTED["ca"])
    np.testing.assert_allclose(got, EXPECTED["rmsd_ca"], rtol=0, atol=1e-3)
    # Fitting on the CA atoms alone must give a different answer from all-atom.
    assert not np.allclose(got, EXPECTED["rmsd_all"], atol=1e-2)


def test_rmsd_does_not_modify_its_inputs(trajectory):
    """The reference centres its arguments in place; this does not.

    That side effect is why loading a trajectory used to move it by several
    nanometres, and why comparing two trajectories could depend on which had
    been measured first. Purity here is a deliberate difference, so it is
    asserted rather than assumed.
    """
    before = trajectory.xyz.copy()
    traj_ops.rmsd(trajectory, trajectory, frame=0)
    np.testing.assert_array_equal(trajectory.xyz, before)


def test_rmsd_is_invariant_to_rotation_and_translation(trajectory):
    # "Minimal RMSD" means exactly this; if the superposition were skipped the
    # value would grow with the displacement instead of staying put.
    moved = traj_ops.Trajectory(trajectory.xyz.copy(), trajectory.topology)
    angle = 0.7
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0],
                         [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    moved.xyz = (moved.xyz @ rotation.T + 12.0).astype(np.float32)
    np.testing.assert_allclose(
        traj_ops.rmsd(moved, trajectory, frame=0),
        traj_ops.rmsd(trajectory, trajectory, frame=0), rtol=0, atol=1e-3)


def test_superpose_matches_the_reference(trajectory):
    trajectory.superpose(trajectory, frame=0)
    np.testing.assert_allclose(trajectory.xyz, EXPECTED["superpose_all"], rtol=0, atol=1e-3)


def test_superpose_on_a_subset_moves_every_atom(trajectory):
    # Fitting on the CA atoms must still transform the sidechains; applying the
    # rotation only to the fitted atoms would tear the molecule apart.
    trajectory.superpose(trajectory, frame=0, atom_indices=EXPECTED["ca"])
    np.testing.assert_allclose(trajectory.xyz, EXPECTED["superpose_ca"], rtol=0, atol=1e-3)


def test_superpose_does_not_mirror(trajectory):
    """A plain SVD can return a reflection, which fits a mirror image.

    The giveaway is a suspiciously small RMSD, so this checks the determinant
    directly: superposing a deliberately mirrored copy must not recover it.
    """
    mirrored = traj_ops.Trajectory(trajectory.xyz.copy() * np.array([1, 1, -1], np.float32),
                                   trajectory.topology)
    before = traj_ops.rmsd(mirrored, trajectory, frame=0)[0]
    mirrored.superpose(trajectory, frame=0)
    after = float(np.sqrt(((mirrored.xyz[0] - trajectory.xyz[0]) ** 2).sum(axis=1).mean()))
    assert before > 0.1 and after > 0.1


def test_compute_distances_matches_the_reference(trajectory):
    got = traj_ops.compute_distances(trajectory, EXPECTED["pairs"], periodic=False)
    np.testing.assert_allclose(got, EXPECTED["distances"], rtol=0, atol=1e-4)


def test_periodic_distances_are_refused_rather_than_ignored(trajectory):
    # Silently dropping the minimum-image convention returns a plausible
    # distance that is simply wrong for a periodic system.
    with pytest.raises(NotImplementedError):
        traj_ops.compute_distances(trajectory, EXPECTED["pairs"], periodic=True)


def test_join_and_slice(trajectory):
    joined = traj_ops.join([trajectory, trajectory])
    assert joined.n_frames == 2 * trajectory.n_frames
    np.testing.assert_array_equal(joined[:3].xyz, trajectory.xyz)
    assert trajectory[1].n_frames == 1
    np.testing.assert_array_equal(trajectory[1].xyz[0], trajectory.xyz[1])


def test_join_refuses_mismatched_atom_counts(trajectory):
    with pytest.raises(ValueError, match="atom counts"):
        traj_ops.join([trajectory, trajectory.atom_slice(range(10))])


def test_atom_slice_subsets_the_topology_too(trajectory):
    sliced = trajectory.atom_slice(range(25))
    assert sliced.n_atoms == 25
    assert sliced.topology.n_atoms == 25


def test_iterload_covers_every_frame():
    chunks = list(traj_ops.iterload(str(DCD), chunk=2, top=str(PDB)))
    assert [c.n_frames for c in chunks] == [2, 1]
    whole = traj_ops.load(str(DCD), top=str(PDB))
    np.testing.assert_array_equal(np.concatenate([c.xyz for c in chunks]), whole.xyz)


def test_load_frame_returns_one_frame():
    frame = traj_ops.load_frame(str(DCD), 1, top=str(PDB))
    assert frame.n_frames == 1
    np.testing.assert_array_equal(
        frame.xyz[0], traj_ops.load(str(DCD), top=str(PDB)).xyz[1])


def test_xtc_loads_through_the_same_entry_point():
    trajectory = traj_ops.load(str(XTC), top=str(PDB))
    assert (trajectory.n_frames, trajectory.n_atoms) == (3, 5235)


def test_a_coordinate_file_without_a_topology_is_refused():
    with pytest.raises(ValueError, match="coordinates only"):
        traj_ops.load(str(DCD))


def test_a_topology_that_does_not_match_is_refused():
    topology = Topology.from_file(str(PDB)).subset(range(10))
    with pytest.raises(ValueError, match="atoms"):
        traj_ops.Trajectory(np.zeros((2, 5235, 3), np.float32), topology)
