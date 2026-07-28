"""Headless (Qt-free) tests for the Align-Trajectory view-model."""

import numpy as np
import pytest


def _tiny_trajectory(path: str, n_frames: int = 5) -> None:
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
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    assert "Ready" in AlignTrajectoryViewModel().log_html()


def test_atom_indices_parses_csv():
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    model = AlignTrajectoryViewModel()
    model.atom_selection = "0, 2, 5"
    np.testing.assert_array_equal(model.atom_indices(), np.array([0, 2, 5], dtype=np.int32))


def test_atom_indices_empty_is_none():
    """An empty selection must be ``None`` — mdtraj's "all atoms", not "no atoms"."""
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    model = AlignTrajectoryViewModel()
    assert model.atom_indices() is None
    model.atom_selection = "   "
    assert model.atom_indices() is None


def test_atom_indices_rejects_non_numeric():
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    model = AlignTrajectoryViewModel()
    model.atom_selection = "CA"
    with pytest.raises(ValueError, match="atom ids"):
        model.atom_indices()


def test_set_trajectory_notifies():
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    model = AlignTrajectoryViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory("/data/traj.h5")
    assert model.trajectory_filename == "/data/traj.h5"
    assert "loaded" in events


def test_save_aligned_without_trajectory_is_noop(tmp_path):
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    model = AlignTrajectoryViewModel()
    target = tmp_path / "out.h5"
    model.save_aligned(str(target))
    assert "No trajectory selected" in model.log_html()
    assert not target.exists()


def test_save_aligned_writes_all_frames(tmp_path):
    md = pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    source = tmp_path / "traj.h5"
    target = tmp_path / "aligned.h5"
    _tiny_trajectory(str(source), n_frames=5)

    model = AlignTrajectoryViewModel()
    model.set_trajectory(str(source))
    model.atom_selection = "0, 1, 2"
    model.save_aligned(str(target))

    assert target.exists()
    aligned = md.load(str(target))
    assert aligned.n_frames == 5
    assert aligned.n_atoms == 3
    assert "Aligned trajectory saved" in model.log_html()


def test_save_aligned_respects_stride(tmp_path):
    md = pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    source = tmp_path / "traj.h5"
    target = tmp_path / "aligned.h5"
    _tiny_trajectory(str(source), n_frames=6)

    model = AlignTrajectoryViewModel()
    model.set_trajectory(str(source))
    model.stride = 2
    model.save_aligned(str(target))

    assert md.load(str(target)).n_frames == 3


def test_save_aligned_with_empty_selection_is_finite(tmp_path):
    """The default (empty) selection must superpose on all atoms, not on none.

    Handing ``superpose`` an empty index array leaves the Theobald solver
    unconverged and writes a trajectory of pure ``NaN`` while still reporting
    success (RF-706).
    """
    md = pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    source = tmp_path / "traj.h5"
    target = tmp_path / "aligned.h5"
    _tiny_trajectory(str(source), n_frames=5)

    model = AlignTrajectoryViewModel()
    model.set_trajectory(str(source))
    model.save_aligned(str(target))

    aligned = md.load(str(target))
    assert aligned.n_frames == 5
    assert np.isfinite(aligned.xyz).all()


def test_save_aligned_rejects_malformed_selection(tmp_path):
    """A non-numeric selection is reported in the log, not written out."""
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    source = tmp_path / "traj.h5"
    target = tmp_path / "aligned.h5"
    _tiny_trajectory(str(source), n_frames=3)

    model = AlignTrajectoryViewModel()
    model.set_trajectory(str(source))
    model.atom_selection = "CA, CB"
    model.save_aligned(str(target))

    assert "atom ids" in model.log_html()
    assert "Aligned trajectory saved" not in model.log_html()
    assert not target.exists()


def test_view_spec_loads():
    from chisurf.plugins.traj.traj_align.view_model import AlignTrajectoryViewModel

    spec = AlignTrajectoryViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)
