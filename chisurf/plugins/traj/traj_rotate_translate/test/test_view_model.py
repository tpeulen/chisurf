"""Headless (Qt-free) tests for the Rotate/Translate-Trajectory view-model."""

import numpy as np
import pytest


def _read(path):
    """Read a written trajectory back, without needing a topology."""
    from chisurf.core.fio.trajectory import read_dcd, read_time_axis
    from chisurf.core.structure import trajectory_data as md

    xyz, _, _ = read_dcd(path)
    return md.Trajectory(xyz / 10.0, time=read_time_axis(path)[:len(xyz)])


def _tiny_trajectory(path: str, n_frames: int = 4, spacing: float = 1.0) -> str:
    """Write a minimal *n_frames* three-atom trajectory to *path* (.dcd).

    Parameters
    ----------
    path : str
        Destination ``.dcd`` path.
    n_frames : int
        Number of frames to write.
    times : numpy.ndarray, optional
        Frame times. Defaults to mdtraj's own ``0, 1, 2, …``; pass an explicit
        array to tell a carried-through time axis apart from a write counter.
    """
    from chisurf.core.structure import trajectory_data as md

    topology = md.Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    for name in ("N", "CA", "C"):
        topology.add_atom(name, md.element.carbon, residue)
    rng = np.random.default_rng(0)
    xyz = rng.random((n_frames, 3, 3)).astype(np.float32)
    trajectory = md.Trajectory(xyz=xyz, topology=topology)
    from chisurf.core.fio.trajectory import write_dcd
    write_dcd(path, xyz * 10.0, delta=spacing)
    pdb = str(path).replace('.dcd', '.pdb')
    trajectory[0].save_pdb(pdb)
    return pdb


def test_log_starts_ready():
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    assert "Ready" in RotateTranslateViewModel().log_html()


def test_defaults_are_identity():
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    model = RotateTranslateViewModel()
    np.testing.assert_array_equal(model.rotation_matrix, np.eye(3, dtype=np.float32))
    np.testing.assert_array_equal(model.translation_vector, np.zeros(3, dtype=np.float32))
    assert model.stride == 1


def test_matrix_vector_stride_roundtrip():
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    model = RotateTranslateViewModel()
    rot = np.arange(9, dtype=np.float32).reshape(3, 3)
    model.rotation_matrix = rot
    model.translation_vector = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    model.stride = 7
    np.testing.assert_array_equal(model.rotation_matrix, rot)
    np.testing.assert_array_equal(model.translation_vector, np.array([1.0, 2.0, 3.0]))
    assert model.stride == 7


def test_set_trajectory_notifies():
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    model = RotateTranslateViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory("/data/traj.dcd")
    assert model.trajectory_filename == "/data/traj.dcd"
    assert "loaded" in events
    assert "/data/traj.dcd" in model.log_html()


def test_save_without_trajectory_is_noop(tmp_path):
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    model = RotateTranslateViewModel()
    target = tmp_path / "out.dcd"
    model.save_rotated_translated(str(target))
    assert "No trajectory selected" in model.log_html()
    assert not target.exists()


def test_save_writes_all_frames(tmp_path):
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    source = tmp_path / "traj.dcd"
    target = tmp_path / "out.dcd"
    topology = _tiny_trajectory(str(source), n_frames=4)

    model = RotateTranslateViewModel()
    model.set_trajectory(str(source))
    model.set_topology(topology)
    model.rotation_matrix = np.eye(3, dtype=np.float32)
    model.translation_vector = np.array([10.0, 0.0, 0.0], dtype=np.float32)
    model.save_rotated_translated(str(target))

    assert target.exists()
    out = _read(str(target))
    assert out.n_frames == 4
    assert out.n_atoms == 3
    assert "Rotated/translated trajectory saved" in model.log_html()


def test_save_applies_translation_divided_by_ten(tmp_path):
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    source = tmp_path / "traj.dcd"
    target = tmp_path / "out.dcd"
    topology = _tiny_trajectory(str(source), n_frames=2)

    src = _read(str(source))
    model = RotateTranslateViewModel()
    model.set_trajectory(str(source))
    model.set_topology(topology)
    # identity rotation, translate x by an entered 10 -> +1.0 nm after /10.0
    model.translation_vector = np.array([10.0, 0.0, 0.0], dtype=np.float32)
    model.save_rotated_translated(str(target))

    out = _read(str(target))
    np.testing.assert_allclose(out.xyz[:, :, 0], src.xyz[:, :, 0] + 1.0, atol=1e-4)
    np.testing.assert_allclose(out.xyz[:, :, 1:], src.xyz[:, :, 1:], atol=1e-4)


def test_save_respects_stride(tmp_path):
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    source = tmp_path / "traj.dcd"
    target = tmp_path / "out.dcd"
    topology = _tiny_trajectory(str(source), n_frames=6)

    model = RotateTranslateViewModel()
    model.set_trajectory(str(source))
    model.set_topology(topology)
    model.stride = 2
    model.save_rotated_translated(str(target))

    assert _read(str(target)).n_frames == 3


def test_save_keeps_the_source_time_axis(tmp_path):
    """A rigid-body transform changes coordinates, not time (RF-708).

    The tool used to write ``0, 1, 2, …`` from the chunk write index, so a
    strided output claimed unit frame spacing — and the sibling FRET tab
    exports ``RDA(t)`` against exactly that axis.
    """
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    source = tmp_path / "traj.dcd"
    target = tmp_path / "out.dcd"
    topology = _tiny_trajectory(str(source), n_frames=6, spacing=10.0)

    model = RotateTranslateViewModel()
    model.set_trajectory(str(source))
    model.set_topology(topology)
    model.stride = 2
    model.save_rotated_translated(str(target))

    np.testing.assert_allclose(_read(str(target)).time, [0.0, 20.0, 40.0])


def test_view_spec_loads():
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    spec = RotateTranslateViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)
