"""Headless (Qt-free) tests for the Rotate/Translate-Trajectory view-model."""

import numpy as np
import pytest


def _tiny_trajectory(path: str, n_frames: int = 4) -> None:
    """Write a minimal *n_frames* three-atom trajectory to *path* (.h5)."""
    md = pytest.importorskip("mdtraj")
    topology = md.Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    for name in ("N", "CA", "C"):
        topology.add_atom(name, md.element.carbon, residue)
    rng = np.random.default_rng(0)
    xyz = rng.random((n_frames, 3, 3)).astype(np.float32)
    md.Trajectory(xyz=xyz, topology=topology).save(path)


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
    model.set_trajectory("/data/traj.h5")
    assert model.trajectory_filename == "/data/traj.h5"
    assert "loaded" in events
    assert "/data/traj.h5" in model.log_html()


def test_save_without_trajectory_is_noop(tmp_path):
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    model = RotateTranslateViewModel()
    target = tmp_path / "out.h5"
    model.save_rotated_translated(str(target))
    assert "No trajectory selected" in model.log_html()
    assert not target.exists()


def test_save_writes_all_frames(tmp_path):
    md = pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    source = tmp_path / "traj.h5"
    target = tmp_path / "out.h5"
    _tiny_trajectory(str(source), n_frames=4)

    model = RotateTranslateViewModel()
    model.set_trajectory(str(source))
    model.rotation_matrix = np.eye(3, dtype=np.float32)
    model.translation_vector = np.array([10.0, 0.0, 0.0], dtype=np.float32)
    model.save_rotated_translated(str(target))

    assert target.exists()
    out = md.load(str(target))
    assert out.n_frames == 4
    assert out.n_atoms == 3
    assert "Rotated/translated trajectory saved" in model.log_html()


def test_save_applies_translation_divided_by_ten(tmp_path):
    md = pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    source = tmp_path / "traj.h5"
    target = tmp_path / "out.h5"
    _tiny_trajectory(str(source), n_frames=2)

    src = md.load(str(source))
    model = RotateTranslateViewModel()
    model.set_trajectory(str(source))
    # identity rotation, translate x by an entered 10 -> +1.0 nm after /10.0
    model.translation_vector = np.array([10.0, 0.0, 0.0], dtype=np.float32)
    model.save_rotated_translated(str(target))

    out = md.load(str(target))
    np.testing.assert_allclose(out.xyz[:, :, 0], src.xyz[:, :, 0] + 1.0, atol=1e-4)
    np.testing.assert_allclose(out.xyz[:, :, 1:], src.xyz[:, :, 1:], atol=1e-4)


def test_save_respects_stride(tmp_path):
    md = pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    source = tmp_path / "traj.h5"
    target = tmp_path / "out.h5"
    _tiny_trajectory(str(source), n_frames=6)

    model = RotateTranslateViewModel()
    model.set_trajectory(str(source))
    model.stride = 2
    model.save_rotated_translated(str(target))

    assert md.load(str(target)).n_frames == 3


def test_view_spec_loads():
    from chisurf.plugins.traj.traj_rotate_translate.view_model import RotateTranslateViewModel

    spec = RotateTranslateViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)
