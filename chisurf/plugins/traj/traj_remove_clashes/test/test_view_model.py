"""Headless (Qt-free) tests for the Remove-Clashed-Frames view-model."""

import numpy as np
import pytest


def _clash_trajectory(path: str) -> None:
    """Write a four-frame three-atom trajectory to *path* (.h5).

    Frames 0 and 2 are clash-free (all atoms ~1 nm apart); frames 1 and 3 each
    contain a pair of atoms only 0.01 nm apart (a clash).
    """
    md = pytest.importorskip("mdtraj")
    topology = md.Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    for name in ("N", "CA", "C"):
        topology.add_atom(name, md.element.carbon, residue)

    xyz = np.zeros((4, 3, 3), dtype=np.float32)
    # frame 0 – well separated
    xyz[0] = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]
    # frame 1 – atoms 0 and 1 clash (0.01 nm apart)
    xyz[1] = [[0.0, 0.0, 0.0], [0.01, 0.0, 0.0], [2.0, 0.0, 0.0]]
    # frame 2 – well separated
    xyz[2] = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]
    # frame 3 – atoms 1 and 2 clash (0.01 nm apart)
    xyz[3] = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.01, 0.0, 0.0]]
    md.Trajectory(xyz=xyz, topology=topology).save(path)


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


def test_min_distance_applies_tenth():
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    model = RemoveClashesViewModel()
    model.min_distance = 2.85
    assert model.min_distance_nm() == pytest.approx(0.285)
    model.min_distance = 5.0
    assert model.min_distance_nm() == pytest.approx(0.5)


def test_set_trajectory_notifies():
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    model = RemoveClashesViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory("/data/traj.h5")
    assert model.trajectory_filename == "/data/traj.h5"
    assert "loaded" in events


def test_save_clash_free_without_trajectory_is_noop(tmp_path):
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    model = RemoveClashesViewModel()
    target = tmp_path / "out.h5"
    model.save_clash_free(str(target))
    assert "No trajectory selected" in model.log_html()
    assert not target.exists()


def test_save_clash_free_drops_clashing_frames(tmp_path):
    md = pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_remove_clashes.view_model import RemoveClashesViewModel

    source = tmp_path / "traj.h5"
    target = tmp_path / "clash_free.h5"
    _clash_trajectory(str(source))

    model = RemoveClashesViewModel()
    model.set_trajectory(str(source))
    model.atom_selection = "all"
    # consumed threshold = 0.5 / 10 = 0.05 nm: drops the two 0.01-nm clash frames,
    # keeps the two well-separated frames.
    model.min_distance = 0.5
    model.save_clash_free(str(target))

    assert target.exists()
    result = md.load(str(target))
    assert result.n_frames == 2
    assert result.n_atoms == 3
    assert "Clash-free trajectory saved" in model.log_html()


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
