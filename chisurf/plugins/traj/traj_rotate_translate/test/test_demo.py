"""The demo affordance of the Rotate/Translate tool: the example in, a moved DCD out."""

from chisurf.plugins.traj.demo_data import demo_folder, example_paths
from chisurf.plugins.traj.traj_rotate_translate.app import make_app
from chisurf.plugins.traj.traj_rotate_translate.demo import OUTPUT, make_demo
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui


def test_make_demo_references_the_shipped_example():
    """The demo runs on the in-repo NMSim example, read where it is."""
    demo = make_demo()
    assert demo["trajectory"].stat().st_size > 0 and demo["topology"].stat().st_size > 0


def test_load_example_writes_the_transformed_trajectory():
    """The affordance fills both rows and applies the current transform (the identity)."""
    from chisurf.core.structure import trajectory_data as md

    app = make_app()
    ui = Ui(app)
    assert ui.shown("Load example")
    app.load_example()
    ui.settle()
    out = demo_folder("traj_rotate_translate") / OUTPUT
    assert out.is_file() and out.stat().st_size > 0
    _dcd, pdb = example_paths()
    moved = md.load(str(out), top=str(pdb))
    assert moved.n_frames == 894 and moved.n_atoms == 1293
    assert any("Rotated/translated trajectory saved" in line for line in app.model.log_text())
