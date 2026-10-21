"""The demo affordance of Trajectory→FRET: the example in, a transfer table out."""

import numpy as np

from chisurf.plugins.traj.demo_data import demo_folder, example_paths
from chisurf.plugins.traj.fret_trajectory.app import make_app
from chisurf.plugins.traj.fret_trajectory.demo import OUTPUT, make_demo
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

EXPECTED_FRAMES = 894


def test_make_demo_references_the_shipped_example():
    """The demo runs on the in-repo NMSim example, read where it is."""
    demo = make_demo()
    assert demo["trajectory"].stat().st_size > 0 and demo["topology"].stat().st_size > 0


def test_load_example_computes_the_transfer_table():
    """The affordance picks the CA pairs and writes one row per frame of the example."""
    app = make_app()
    ui = Ui(app)
    assert ui.shown("Load example")
    app.load_example()
    ui.settle()
    out = demo_folder("fret_trajectory") / OUTPUT
    assert out.is_file() and out.stat().st_size > 0
    table = np.loadtxt(out, skiprows=1)  # the engine writes a tab-separated table
    assert table.shape == (EXPECTED_FRAMES, 6)  # frame, time, RDA, kappa, kappa2, rate
    assert np.isfinite(table[:, 2]).all() and (table[:, 2] > 0).all()
    assert any("Finished" in line and "894 frames" in line for line in app.model.log_text())
    dcd, _pdb = example_paths()
    assert dcd.name in app.model.log_text()[-2]
