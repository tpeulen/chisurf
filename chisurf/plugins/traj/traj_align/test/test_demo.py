"""The demo affordance of the Align-Trajectory tool: the example in, an aligned DCD out."""

import numpy as np

from chisurf.plugins.traj.demo_data import demo_folder, example_paths
from chisurf.plugins.traj.traj_align.app import make_app
from chisurf.plugins.traj.traj_align.demo import OUTPUT, make_demo
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui


def test_make_demo_references_the_shipped_example():
    """The demo runs on the in-repo NMSim example, read where it is."""
    demo = make_demo()
    dcd, pdb = example_paths()
    assert demo["trajectory"] == dcd and dcd.stat().st_size > 0
    assert demo["topology"] == pdb and pdb.stat().st_size > 0


def test_load_example_aligns_the_example_trajectory():
    """The affordance fills both rows, runs the action and writes every frame aligned."""
    from chisurf.core.structure import trajectory_data as md

    app = make_app()
    ui = Ui(app)
    assert ui.shown("Load example")
    app.load_example()
    ui.settle()
    out = demo_folder("traj_align") / OUTPUT
    assert out.is_file() and out.stat().st_size > 0
    dcd, pdb = example_paths()
    aligned = md.load(str(out), top=str(pdb))
    reference = md.load(str(dcd), top=str(pdb))
    assert aligned.n_frames == reference.n_frames
    np.testing.assert_allclose(aligned.xyz[0], reference.xyz[0], atol=1e-2)
    assert any("Aligned trajectory saved" in line for line in app.model.log_text())
