"""Native-surface tests for the Trajectory→FRET tool."""

import pathlib
import time

import numpy as np
from emtk.testing import Driver

from chisurf.core.structure.trajectory_data import Trajectory
from chisurf.plugins.traj.fret_trajectory.app import FretTrajectoryApp, make_app


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


def test_native_surface_creation():
    """The shipped factory constructs its declared native form and scientific model."""
    app = make_app()
    try:
        assert isinstance(app, FretTrajectoryApp)
        assert app.model.view_spec().sections
        assert app.form.custom["fret_atom_pairs"]
    finally:
        app.close()


def test_surface_settings_are_the_scientific_model_values():
    """Native settings retain the original timing, radius, lifetime and stride values."""
    app = make_app()
    try:
        model = app.model
        model.trajectory_file = "/data/example.h5"
        model.t_step, model.forster_radius, model.tau0, model.stride = 0.25, 55.0, 3.5, 3
        assert model.trajectory_file == "/data/example.h5"
        assert (model.t_step, model.forster_radius, model.tau0, model.stride) == (
            0.25,
            55.0,
            3.5,
            3,
        )
    finally:
        app.close()


def test_form_renders_with_live_log_and_dipole_choices(tmp_path):
    """Real atom names, the Process control and the initial log remain reachable."""
    source = tmp_path / "traj.dcd"
    topology = _fret_trajectory(source)
    app = make_app()
    try:
        app.model.set_topology(topology)
        app.model.set_trajectory(str(source))
        driver = Driver(app, (800, 700))
        painter = driver.frame(2)
        assert {"Donor", "Acceptor", "Chain", "Residue", "Atom", "Log"}.issubset(painter.strings)
        assert driver.rect("process")
        assert app.atom_index().name(0) == "N"
        assert app.model.log_text()[0].endswith("Ready")
    finally:
        app.close()


def test_gui_interaction_process(tmp_path):
    """Click the native Process action and write the same five-frame transfer table."""
    n_frames = 5
    source = tmp_path / "traj.dcd"
    output = tmp_path / "transfer.csv"
    topology = _fret_trajectory(source, n_frames=n_frames)

    app = make_app()
    try:
        app.model.set_topology(topology)
        app.model.set_trajectory(str(source))
        app.model.donor, app.model.acceptor = (0, 1), (2, 3)
        driver = Driver(app, (800, 700))
        driver.click("process")
        assert app.dialog is not None
        app.dialog.draw = lambda: [str(output)]
        driver.frame(1)
        deadline = time.monotonic() + 10
        while app.running:
            assert time.monotonic() < deadline, "processing did not finish"
            driver.frame(1)
            time.sleep(0.01)
        result = np.loadtxt(output, skiprows=1)
        assert result.shape == (n_frames, 6)
        assert np.all(np.isfinite(result))
        assert any("Finished" in line for line in app.model.log_text())
    finally:
        app.close()
