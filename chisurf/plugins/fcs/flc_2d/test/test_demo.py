"""The 2D-FLCS tool's example: its own simulated stream, analysed end to end."""

import json

from chisurf.plugins.fcs.flc_2d.demo import demo_folder, make_demo
from chisurf.plugins.fcs.flc_2d.gui.app import make_app


def test_make_demo_states_the_simulator_parameters():
    """The sidecar records the kinetics the simulated stream is built from."""
    path = make_demo()
    payload = json.loads(path.read_text())
    assert payload["sim"]["k12"] > 0 and payload["sim"]["k21"] > 0


def test_load_example_simulates_and_runs():
    """The affordance simulates the stream and runs the analysis on the worker."""
    app = make_app()
    app.load_example()
    model = app.model
    assert model.tttr is not None
    assert model.spectrum2d is not None
    assert demo_folder() / "flc_2d_demo.json" == make_demo()
