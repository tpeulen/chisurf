"""The demo affordance of the Save-Topology tool: the example in, a named-atom PDB out."""

from chisurf.plugins.traj.demo_data import demo_folder, example_paths
from chisurf.plugins.traj.traj_save_topology.app import make_app
from chisurf.plugins.traj.traj_save_topology.demo import OUTPUT, make_demo
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui


def test_make_demo_references_the_shipped_example():
    """The demo runs on the in-repo NMSim example, read where it is."""
    demo = make_demo()
    dcd, pdb = example_paths()
    assert demo["trajectory"] == dcd and demo["topology"] == pdb


def test_load_example_writes_the_topology():
    """The affordance fills both rows and writes the DCD's topology as a PDB."""
    from chisurf.core.structure import trajectory_data as md

    app = make_app()
    ui = Ui(app)
    assert ui.shown("Load example")
    app.load_example()
    ui.settle()
    out = demo_folder("traj_save_topology") / OUTPUT
    assert out.is_file() and out.stat().st_size > 0
    topology = md.load(str(out))
    assert topology.n_atoms == 1293
    assert any("Topology saved" in line for line in app.model.log_text())
