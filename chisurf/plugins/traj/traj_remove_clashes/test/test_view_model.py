"""Headless (Qt-free) tests for the Remove-Clashed-Frames view-model."""

import numpy as np
import pytest


def _read(path):
    """Read a written trajectory back, without needing a topology."""
    from chisurf.core.fio.trajectory import read_dcd
    from chisurf.core.structure import trajectory_data as md

    from chisurf.core.fio.trajectory import read_times

    xyz, _, _ = read_dcd(path)
    return md.Trajectory(xyz, time=read_times(path))


def _clash_trajectory(path: str, spacing: float = 1.0) -> str:
    """Write a four-frame three-atom trajectory to *path* (.dcd).

    Frames 0 and 2 are clash-free (all atoms ~10 Å apart); frames 1 and 3 each
    contain a pair of atoms only 0.1 Å apart (a clash). Coordinates are
    Ångström, in memory and on disk.

    Parameters
    ----------
    path : str
        Destination ``.dcd`` path.
    spacing : float, optional
        Frame interval written to the DCD header.
    """
    from chisurf.core.structure import trajectory_data as md

    topology = md.Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    for name in ("N", "CA", "C"):
        topology.add_atom(name, md.element.carbon, residue)

    xyz = np.zeros((4, 3, 3), dtype=np.float32)
    xyz[0] = [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [20.0, 0.0, 0.0]]
    xyz[1] = [[0.0, 0.0, 0.0], [0.1, 0.0, 0.0], [20.0, 0.0, 0.0]]   # 0-1 clash
    xyz[2] = [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [20.0, 0.0, 0.0]]
    xyz[3] = [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.1, 0.0, 0.0]]  # 1-2 clash
    trajectory = md.Trajectory(xyz=xyz, topology=topology)
    from chisurf.core.fio.trajectory import write_dcd
    write_dcd(path, xyz, delta=spacing)
    pdb = str(path).replace('.dcd', '.pdb')
    trajectory[0].save_pdb(pdb)
    return pdb


def test_log_starts_ready():
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    assert "Ready" in RemoveClashesViewModel().log_html()


def test_atom_selection_round_trips():
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    model = RemoveClashesViewModel()
    model.atom_selection = "name CA"
    assert model.atom_selection == "name CA"


def test_stride_round_trips():
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    model = RemoveClashesViewModel()
    model.stride = 7
    assert model.stride == 7


def test_the_threshold_is_the_frames_own_unit():
    """Ångström, like the coordinates: a /10 here survived the move off nanometres."""
    from chisurf.plugins.traj.traj_remove_clashes.view_model import below_min_distance

    xyz = np.array([[[0.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                    [[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]]], dtype=np.float32)
    assert list(below_min_distance(xyz, min_distance=3.0)) == [1, 0]


def test_set_trajectory_notifies():
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    model = RemoveClashesViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory("/data/traj.dcd")
    assert model.trajectory_filename == "/data/traj.dcd"
    assert "loaded" in events


def test_save_clash_free_without_trajectory_is_noop(tmp_path):
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    model = RemoveClashesViewModel()
    target = tmp_path / "out.dcd"
    model.save_clash_free(str(target))
    assert "No trajectory selected" in model.log_html()
    assert not target.exists()


def test_save_clash_free_drops_clashing_frames(tmp_path):
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    source = tmp_path / "traj.dcd"
    target = tmp_path / "clash_free.dcd"
    topology = _clash_trajectory(str(source))

    model = RemoveClashesViewModel()
    model.set_trajectory(str(source))
    model.set_topology(topology)
    model.atom_selection = "all"
    # 0.5 Å drops the two 0.1-Å clash frames and keeps the two 10-Å ones.
    model.min_distance = 0.5
    model.save_clash_free(str(target))

    assert target.exists()
    result = _read(str(target))
    assert result.n_frames == 2
    assert result.n_atoms == 3
    assert "Clash-free trajectory saved" in model.log_html()


def test_kept_frames_keep_their_source_times(tmp_path):
    """The discarded frames must leave gaps in the time axis (RF-708).

    A running write counter renumbered the survivors ``0, 1, …``, hiding both
    the removals and the read stride from every downstream reader.
    """
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    source = tmp_path / "traj.dcd"
    target = tmp_path / "clashfree.dcd"
    topology = _clash_trajectory(str(source), spacing=5.0)

    model = RemoveClashesViewModel()
    model.set_trajectory(str(source))
    model.set_topology(topology)
    model.atom_selection = "all"
    model.min_distance = 0.5
    model.save_clash_free(str(target))

    # frames 1 and 3 clash; the survivors keep t = 0 and t = 10, not 0 and 1.
    np.testing.assert_allclose(_read(str(target)).time, [0.0, 10.0])


def test_view_spec_loads():
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    spec = RemoveClashesViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)


def test_below_min_distance_kernel():
    pytest.importorskip("numba")
    from chisurf.plugins.traj.traj_remove_clashes.view_model import below_min_distance

    # frame 0: atoms 1 nm apart (no clash); frame 1: atoms 0.01 nm apart (clash).
    xyz = np.zeros((2, 2, 3), dtype=np.float64)
    xyz[0] = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]
    xyz[1] = [[0.0, 0.0, 0.0], [0.01, 0.0, 0.0]]

    # The atom list mirrors what mdtraj's ``top.select`` yields (int64).
    both = np.array([0, 1], dtype=np.int64)
    flags = below_min_distance(xyz, 0.05, atom_list=both)
    assert flags[0] == 0  # no clash → kept
    assert flags[1] > 0  # clash → dropped

    # restricting to a single atom means no pair to compare → never a clash.
    single = below_min_distance(xyz, 0.05, atom_list=np.array([0], dtype=np.int64))
    assert single[0] == 0
    assert single[1] == 0
