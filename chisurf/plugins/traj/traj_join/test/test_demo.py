"""The demo affordance of Join-Trajectories: the example twice in, twice its frames out."""

from chisurf.plugins.traj.demo_data import demo_folder, example_paths
from chisurf.plugins.traj.traj_join.app import make_app
from chisurf.plugins.traj.traj_join.demo import OUTPUT, make_demo
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

EXPECTED_FRAMES = 2 * 894  # the example joined with itself in "time" mode


def test_make_demo_references_the_shipped_example():
    """The demo runs on the in-repo NMSim example, read where it is."""
    demo = make_demo()
    assert demo["trajectory"].stat().st_size > 0 and demo["topology"].stat().st_size > 0


def test_load_example_joins_the_example_with_itself():
    """The affordance fills both trajectory rows (and the topology), then joins."""
    from chisurf.core.structure import trajectory_data as md

    app = make_app()
    ui = Ui(app)
    assert ui.shown("Load example")
    app.load_example()
    ui.settle()
    out = demo_folder("traj_join") / OUTPUT
    assert out.is_file() and out.stat().st_size > 0
    _dcd, pdb = example_paths()
    joined = md.load(str(out), top=str(pdb))
    assert joined.n_frames == EXPECTED_FRAMES
    assert joined.n_atoms == 1293
    assert any("Joined trajectory saved" in line for line in app.model.log_text())
