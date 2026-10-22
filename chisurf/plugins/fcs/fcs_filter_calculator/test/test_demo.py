"""The filtered-FCS calculator's example: the shipped population, recomputed."""

import json

from chisurf.plugins.fcs.fcs_filter_calculator.demo import TRUTH, demo_folder, make_demo
from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app


def test_make_demo_states_the_truth():
    """The sidecar records the lifetimes the example population was built from."""
    path = make_demo()
    assert json.loads(path.read_text()) == TRUTH


def test_load_example_recomputes_the_filters():
    """The affordance re-runs the shipped example population through the model."""
    app = create_app()
    app.load_example()
    results = app.model.results()
    assert results
    assert app.model.message
    assert demo_folder() / "filter_demo.json" == make_demo()
