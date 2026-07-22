"""Headless (Qt-free) tests for the Trajectory→FRET view-model."""

import numpy as np
import pytest


def _fret_trajectory(path: str, n_frames: int = 5) -> None:
    """Write a minimal *n_frames* trajectory with donor/acceptor atoms to *path* (.h5).

    The residue carries four labelled atoms so the donor dipole ``(0, 1)`` and the
    acceptor dipole ``(2, 3)`` reference real coordinates and produce a transfer.
    """
    md = pytest.importorskip("mdtraj")
    topology = md.Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    for name in ("N", "CA", "C", "O"):
        topology.add_atom(name, md.element.carbon, residue)
    rng = np.random.default_rng(0)
    xyz = rng.random((n_frames, 4, 3)).astype(np.float32)
    md.Trajectory(xyz=xyz, topology=topology).save(path)


def test_log_starts_ready():
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    assert "Ready" in FretTrajectoryViewModel().log_html()


def test_parameters_round_trip():
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    model = FretTrajectoryViewModel()
    model.trajectory_file = "/data/traj.h5"
    model.donor = (0, 1)
    model.acceptor = (2, 3)
    model.t_step = 0.5
    model.forster_radius = 60.0
    model.tau0 = 3.8
    model.stride = 2
    model.dipoles = False

    assert model.trajectory_file == "/data/traj.h5"
    assert tuple(model.donor) == (0, 1)
    assert tuple(model.acceptor) == (2, 3)
    assert model.t_step == 0.5
    assert model.forster_radius == 60.0
    assert model.tau0 == 3.8
    assert model.stride == 2
    assert model.dipoles is False


def test_set_trajectory_notifies_and_loads_topology(tmp_path):
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    source = tmp_path / "traj.h5"
    _fret_trajectory(str(source), n_frames=4)

    model = FretTrajectoryViewModel()
    events = []
    model.add_observer(events.append)
    model.set_trajectory(str(source))

    assert model.trajectory_file == str(source)
    assert "loaded" in events
    # The topology of the first frame was read into a structured coordinate array.
    assert model.pdb is not None
    assert len(model.pdb) == 4


def test_calc_without_trajectory_is_noop(tmp_path):
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    model = FretTrajectoryViewModel()
    out = model.calc(output_file=str(tmp_path / "out.csv"))
    assert out.shape[0] == 0
    assert "No trajectory selected" in model.log_html()


def test_calc_end_to_end(tmp_path):
    """Real end-to-end transfer computation on a built trajectory."""
    pytest.importorskip("mdtraj")
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    n_frames = 5
    source = tmp_path / "traj.h5"
    output = tmp_path / "transfer.csv"
    _fret_trajectory(str(source), n_frames=n_frames)

    model = FretTrajectoryViewModel()
    model.set_trajectory(str(source))
    model.donor = (0, 1)
    model.acceptor = (2, 3)
    model.dipoles = True

    result = model.calc(output_file=str(output))

    # The output file was written ...
    assert output.exists()
    # ... and a transfer array with one row per frame and finite values returned.
    assert result.shape == (n_frames, 6)
    assert np.all(np.isfinite(result))
    # column 2 is the RDA distance in Angstrom (positive)
    assert np.all(result[:, 2] > 0)
    assert "Finished" in model.log_html()


def test_view_spec_loads():
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    spec = FretTrajectoryViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)
