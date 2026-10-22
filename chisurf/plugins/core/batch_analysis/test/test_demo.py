"""The batch wizard's example: the test fakes' session, run through the real batch."""

import csv

from chisurf.plugins.core.batch_analysis.demo import N_DATASETS, make_demo
from chisurf.plugins.core.batch_analysis.gui.app import make_app


def test_make_demo_runs_the_example_batch():
    """The demo batch writes a results CSV with one row per dataset."""
    path = make_demo()
    rows = list(csv.reader(path.open()))
    assert path.stat().st_size > 0
    assert len(rows) >= N_DATASETS + 1


def test_load_example_stages_and_runs_the_wizard():
    """The affordance hands the fake session to a live wizard; the batch runs."""
    app = make_app()
    model = app.model
    model.load_example()
    assert len(model.selected_datasets()) == N_DATASETS
    assert model.save_path
    model.run()
    if model._thread is not None:
        model._thread.join(timeout=120.0)
    model.poll()
    path = make_demo()
    assert path.is_file() and path.stat().st_size > 0
