"""Headless (Qt-free) tests for the Join-Trajectories view-model."""

import numpy as np


def _read(path):
    """Read a written trajectory back, without needing a topology."""
    from chisurf.core.fio.trajectory import read_dcd, read_time_axis
    from chisurf.core.structure import trajectory_data as md

    xyz, _, _ = read_dcd(path)
    return md.Trajectory(xyz, time=read_time_axis(path)[: len(xyz)])


def _tiny_trajectory(path: str, n_frames: int = 5, n_atoms: int = 3) -> None:
    """Write a minimal *n_frames* × *n_atoms* trajectory to *path* (.dcd)."""
    from chisurf.core.structure import trajectory_data as md

    topology = md.Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    names = ("N", "CA", "C", "O", "CB", "CG")
    for i in range(n_atoms):
        topology.add_atom(names[i % len(names)], md.element.carbon, residue)
    rng = np.random.default_rng(0)
    xyz = rng.random((n_frames, n_atoms, 3)).astype(np.float32)
    trajectory = md.Trajectory(xyz=xyz, topology=topology)
    trajectory.save_dcd(path)
    pdb = str(path).replace(".dcd", ".pdb")
    trajectory[0].save_pdb(pdb)
    return pdb


def test_log_starts_ready():
    from chisurf.plugins.traj.traj_join.view_model import JoinTrajectoriesViewModel

    assert "Ready" in JoinTrajectoriesViewModel().log_html()


def test_set_trajectory_1_notifies():
    from chisurf.plugins.traj.traj_join.view_model import JoinTrajectoriesViewModel

    model = JoinTrajectoriesViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory_1("/data/a.dcd")
    assert model.trajectory_filename_1 == "/data/a.dcd"
    assert "loaded" in events


def test_set_trajectory_2_notifies():
    from chisurf.plugins.traj.traj_join.view_model import JoinTrajectoriesViewModel

    model = JoinTrajectoriesViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory_2("/data/b.dcd")
    assert model.trajectory_filename_2 == "/data/b.dcd"
    assert "loaded" in events


def test_state_round_trips():
    from chisurf.plugins.traj.traj_join.view_model import JoinTrajectoriesViewModel

    model = JoinTrajectoriesViewModel()
    model.join_mode = "atoms"
    model.reverse_traj_1 = True
    model.reverse_traj_2 = True
    model.chunk_size = 250
    assert model.join_mode == "atoms"
    assert model.reverse_traj_1 is True
    assert model.reverse_traj_2 is True
    assert model.chunk_size == 250


def test_save_joined_without_trajectories_is_noop(tmp_path):
    from chisurf.plugins.traj.traj_join.view_model import JoinTrajectoriesViewModel

    model = JoinTrajectoriesViewModel()
    target = tmp_path / "out.dcd"
    model.save_joined(str(target))
    assert "Two trajectories are required" in model.log_html()
    assert not target.exists()


def test_save_joined_time_appends_frames(tmp_path):
    from chisurf.plugins.traj.traj_join.view_model import JoinTrajectoriesViewModel

    fn1 = tmp_path / "a.dcd"
    fn2 = tmp_path / "b.dcd"
    target = tmp_path / "joined.dcd"
    topology = _tiny_trajectory(str(fn1), n_frames=4, n_atoms=3)
    _tiny_trajectory(str(fn2), n_frames=6, n_atoms=3)

    model = JoinTrajectoriesViewModel()
    model.set_trajectory_1(str(fn1))
    model.set_trajectory_2(str(fn2))
    model.set_topology(topology)
    model.join_mode = "time"
    model.save_joined(str(target))

    assert target.exists()
    joined = _read(str(target))
    # Time-join concatenates frames on axis 0; per matched chunk both are read.
    assert joined.n_atoms == 3
    assert joined.n_frames == 10
    # Coordinates come through unscaled: Ångström in, Ångström out.
    np.testing.assert_allclose(joined.xyz[:4], _read(str(fn1)).xyz, atol=1e-4)
    assert "Joined trajectory saved" in model.log_html()


def test_save_joined_atoms_doubles_atom_count(tmp_path):
    from chisurf.plugins.traj.traj_join.view_model import JoinTrajectoriesViewModel

    fn1 = tmp_path / "a.dcd"
    fn2 = tmp_path / "b.dcd"
    target = tmp_path / "joined.dcd"
    topology = _tiny_trajectory(str(fn1), n_frames=5, n_atoms=3)
    _tiny_trajectory(str(fn2), n_frames=5, n_atoms=3)

    model = JoinTrajectoriesViewModel()
    model.set_trajectory_1(str(fn1))
    model.set_trajectory_2(str(fn2))
    model.set_topology(topology)
    model.join_mode = "atoms"
    model.save_joined(str(target))

    assert target.exists()
    joined = _read(str(target))
    # Atom-stack concatenates atoms on axis 1; frame count unchanged.
    assert joined.n_atoms == 6
    assert joined.n_frames == 5


def test_save_joined_reverse_flag_orders_frames(tmp_path):
    from chisurf.plugins.traj.traj_join.view_model import JoinTrajectoriesViewModel

    fn1 = tmp_path / "a.dcd"
    fn2 = tmp_path / "b.dcd"
    plain = tmp_path / "plain.dcd"
    reversed_out = tmp_path / "rev.dcd"
    topology = _tiny_trajectory(str(fn1), n_frames=4, n_atoms=3)
    _tiny_trajectory(str(fn2), n_frames=4, n_atoms=3)

    base = JoinTrajectoriesViewModel()
    base.set_trajectory_1(str(fn1))
    base.set_trajectory_2(str(fn2))
    base.set_topology(topology)
    base.join_mode = "time"
    base.save_joined(str(plain))

    rev = JoinTrajectoriesViewModel()
    rev.set_trajectory_1(str(fn1))
    rev.set_trajectory_2(str(fn2))
    rev.set_topology(topology)
    rev.join_mode = "time"
    rev.reverse_traj_1 = True
    rev.save_joined(str(reversed_out))

    plain_xyz = _read(str(plain)).xyz
    rev_xyz = _read(str(reversed_out)).xyz
    # Reversing trajectory 1 flips the order of its first four (chunk) frames.
    np.testing.assert_allclose(rev_xyz[:4], plain_xyz[:4][::-1])


def test_view_spec_loads():
    from chisurf.plugins.traj.traj_join.view_model import JoinTrajectoriesViewModel

    spec = JoinTrajectoriesViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)
