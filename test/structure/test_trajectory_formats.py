"""Opening DCD trajectories through :class:`TrajectoryFile`.

The coordinates come from ChiSurf's own codecs
(:mod:`chisurf.core.fio.trajectory`), which are tested against reference files
elsewhere. What matters here is the wiring: that the loader reaches those
codecs, pairs them with a topology, and refuses the cases where it cannot.

One thing to know before reading the assertions, because it **changed**.
``TrajectoryFile`` computes an RMSD in its constructor, and the implementation
it used to call centred its inputs *in place* — so every trajectory this class
loaded came back recentred, by up to several nanometres, silently and for every
format. ChiSurf's own ``rmsd`` is pure, so that no longer happens: a loaded
trajectory now holds the coordinates the file holds. These tests pin that,
because it is exactly the kind of behaviour a future reimplementation could
reintroduce by accident.
"""

from __future__ import annotations

import pathlib
import tempfile

import numpy as np
import pytest

DATA = pathlib.Path(__file__).resolve().parents[1] / "data/atomic_coordinates/trajectory"
TOPOLOGY = DATA / "hgbp1/topol.pdb"
DCD = DATA / "dcd/hgbp1_transition.dcd"


@pytest.fixture
def trajectory_file():
    from chisurf.core.structure.trajectory import TrajectoryFile

    return TrajectoryFile


def _reference(path, kind):
    """Return the coordinates the file itself holds, in ångströms."""
    from chisurf.core.fio.trajectory import read_dcd

    xyz, _, _ = read_dcd(str(path))
    return xyz  # DCD is already angstroms


@pytest.mark.parametrize(
    "path, kind, atol",
    [
        # The loaded coordinates must be the file's own -- not recentred, not
        # rescaled. DCD stores angstroms, which the interior also uses, so no
        # conversion happens anywhere and the comparison is exact.
        (DCD, "dcd", 0.0),
    ],
)
def test_a_coordinate_trajectory_loads_with_a_topology(trajectory_file, path, kind, atol):
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
    # DCD stores coordinates only. Guessing a topology is not possible,
    # and proceeding without one would produce a trajectory with no atom names.
    with pytest.raises(ValueError, match="coordinates only"):
        trajectory_file(str(DCD))


def test_a_topology_that_does_not_match_is_refused(trajectory_file):
    from chisurf.core.structure import trajectory_data as md

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
