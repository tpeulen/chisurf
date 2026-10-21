"""The demo affordance of the MD-Converter: the example in, a strided DCD out."""

from chisurf.plugins.traj.demo_data import demo_folder, example_paths
from chisurf.plugins.traj.traj_convert.app import make_app
from chisurf.plugins.traj.traj_convert.demo import OUTPUT, STRIDE, make_demo
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

EXPECTED_FRAMES = len(range(0, 894, STRIDE))


def test_make_demo_references_the_shipped_example():
    """The demo runs on the in-repo NMSim example, read where it is."""
    demo = make_demo()
    assert demo["trajectory"].stat().st_size > 0 and demo["topology"].stat().st_size > 0


def test_load_example_converts_the_example_trajectory():
    """The affordance fills topology, input and target-folder rows, then converts."""
    from chisurf.core.structure import trajectory_data as md

    app = make_app()
    ui = Ui(app)
    assert ui.shown("Load example")
    app.load_example()
    ui.settle()
    out = demo_folder("traj_convert") / OUTPUT
    assert out.is_file() and out.stat().st_size > 0
    _dcd, pdb = example_paths()
    converted = md.load(str(out), top=str(pdb))
    assert converted.n_frames == EXPECTED_FRAMES
    assert converted.n_atoms == 1293
    assert ui.shown("Conversion done!")
