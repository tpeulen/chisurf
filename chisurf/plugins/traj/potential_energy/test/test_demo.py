"""The demo affordance of the Potential-Energy tool: the example in, an energy CSV out."""

from chisurf.plugins.traj.demo_data import demo_folder
from chisurf.plugins.traj.potential_energy.app import make_app
from chisurf.plugins.traj.potential_energy.demo import OUTPUT, STRIDE, make_demo
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

EXPECTED_FRAMES = len(range(0, 894, STRIDE))


def test_make_demo_references_the_shipped_example():
    """The demo runs on the in-repo NMSim example, read where it is."""
    demo = make_demo()
    assert demo["trajectory"].stat().st_size > 0 and demo["topology"].stat().st_size > 0


def test_load_example_scores_the_example_trajectory():
    """The affordance adds a potential, strides the scan and writes one row per frame."""
    app = make_app()
    ui = Ui(app)
    assert ui.shown("Load example")
    app.load_example()
    ui.settle()
    out = demo_folder("potential_energy") / OUTPUT
    assert out.is_file() and out.stat().st_size > 0
    lines = out.read_text().strip().splitlines()
    assert len(lines) == EXPECTED_FRAMES + 1  # the header, then one row per scored frame
    assert "H-Bond" in lines[0]
    assert ui.shown(f"Processed {EXPECTED_FRAMES} frame(s).")
    assert any("Added potential 'H-Bond'" in line for line in app.model.log_text())
