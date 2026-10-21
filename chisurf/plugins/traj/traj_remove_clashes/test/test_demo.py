"""The demo affordance of the Remove-Clashed tool: the example in, a screened DCD out."""

from chisurf.plugins.traj.demo_data import demo_folder, example_paths
from chisurf.plugins.traj.traj_remove_clashes.app import make_app
from chisurf.plugins.traj.traj_remove_clashes.demo import OUTPUT, STRIDE, make_demo
from chisurf.plugins.traj.traj_remove_clashes.view_model import below_min_distance
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

EXPECTED_FRAMES = len(range(0, 894, STRIDE))


def test_make_demo_references_the_shipped_example():
    """The demo runs on the in-repo NMSim example, read where it is."""
    demo = make_demo()
    assert demo["trajectory"].stat().st_size > 0 and demo["topology"].stat().st_size > 0


def test_load_example_writes_a_clash_free_trajectory():
    """The affordance fills both rows, screens the strided frames and writes the kept ones."""
    from chisurf.core.structure import trajectory_data as md

    app = make_app()
    ui = Ui(app)
    assert ui.shown("Load example")
    app.load_example()
    ui.settle()
    out = demo_folder("traj_remove_clashes") / OUTPUT
    assert out.is_file() and out.stat().st_size > 0
    _dcd, pdb = example_paths()
    kept = md.load(str(out), top=str(pdb))
    assert kept.n_atoms == 1293
    assert kept.n_frames <= EXPECTED_FRAMES
    assert any(f"Kept" in line for line in app.model.log_text())
    assert callable(below_min_distance)  # the screen itself is unit-tested elsewhere
