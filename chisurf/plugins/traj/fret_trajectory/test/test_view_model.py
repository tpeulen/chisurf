"""Headless (Qt-free) tests for the Trajectory→FRET view-model."""

import pathlib

import numpy as np
import pytest

from chisurf.core.structure.trajectory_data import Trajectory


def _fret_trajectory(path, n_frames: int = 5) -> str:
    """Write a minimal *n_frames* trajectory and return the topology beside it.

    The residue carries four labelled atoms so the donor dipole ``(0, 1)`` and
    the acceptor dipole ``(2, 3)`` reference real coordinates and produce a
    transfer.

    Two files, because a DCD holds coordinates and nothing else. The fixture
    used to be one ``.h5`` written by mdtraj and guarded with
    ``importorskip("mdtraj")`` -- which did not skip when mdtraj left, because
    the test environment still had the package installed while the tree no
    longer read what it wrote. Built on ChiSurf's own writers there is nothing
    left to skip on.
    """
    from chisurf.core.fio.trajectory import DCDWriter
    from chisurf.core.structure.topology import Topology, element

    path = pathlib.Path(path)
    topology = Topology()
    chain = topology.add_chain()
    residue = topology.add_residue("ALA", chain)
    for name in ("N", "CA", "C", "O"):
        topology.add_atom(name, element.carbon, residue)

    rng = np.random.default_rng(0)
    # Angstrom: DCD's unit, and the range the transfer calculation expects.
    xyz = (rng.random((n_frames, 4, 3)) * 10.0).astype(np.float32)
    with DCDWriter(str(path), n_atoms=4) as writer:
        for frame in xyz:
            writer.write(frame)

    topology_path = path.with_suffix(".pdb")
    Trajectory(xyz=xyz[:1], topology=topology).save_pdb(str(topology_path))
    return str(topology_path)


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
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    source = tmp_path / "traj.dcd"
    topology = _fret_trajectory(source, n_frames=4)

    model = FretTrajectoryViewModel()
    events = []
    model.add_observer(events.append)
    model.set_topology(topology)
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
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    n_frames = 5
    source = tmp_path / "traj.dcd"
    output = tmp_path / "transfer.csv"
    topology = _fret_trajectory(source, n_frames=n_frames)

    model = FretTrajectoryViewModel()
    model.set_topology(topology)
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


def test_calc_without_dipoles_uses_fixed_kappa2(tmp_path):
    """Un-ticking *Dipole (kappa2)* must fall back to the fixed kappa2, not to zero."""
    from chisurf.core.fluorescence.general import distance_to_fret_rate_constant
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    n_frames = 5
    source = tmp_path / "traj.dcd"
    topology = _fret_trajectory(source, n_frames=n_frames)

    model = FretTrajectoryViewModel()
    model.set_topology(topology)
    model.set_trajectory(str(source))
    model.donor = (0, 1)
    model.acceptor = (2, 3)
    model.dipoles = False

    result = model.calc(output_file=str(tmp_path / "transfer.csv"))

    assert result.shape == (n_frames, 6)
    # RDA is the donor-acceptor distance in the coordinates' own unit (Å); a
    # ×10 left from the nanometre days inflated it and every rate after it.
    from chisurf.core.fio.trajectory import read_dcd

    xyz, _, _ = read_dcd(str(source))
    np.testing.assert_allclose(
        result[:, 2], np.linalg.norm(xyz[:, 2] - xyz[:, 0], axis=1), rtol=1e-5)
    # kappa2 is the engine's isotropic constant, and kappa its square root ...
    np.testing.assert_allclose(result[:, 4], 2.0 / 3.0, rtol=1e-6)
    np.testing.assert_allclose(result[:, 3] ** 2, result[:, 4], rtol=1e-6)
    # ... so the rate is the one that constant implies, and never zero.
    assert np.all(result[:, 5] > 0)
    np.testing.assert_allclose(
        result[:, 5],
        distance_to_fret_rate_constant(
            result[:, 2], model.forster_radius, model.tau0, 2.0 / 3.0
        ),
        rtol=1e-6,
    )


def test_view_spec_loads():
    from chisurf.plugins.traj.fret_trajectory.view_model import FretTrajectoryViewModel

    spec = FretTrajectoryViewModel().view_spec()
    assert spec is not None
    assert getattr(spec, "sections", None)
