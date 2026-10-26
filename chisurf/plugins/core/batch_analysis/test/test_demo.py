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
    # wait() polls while it joins: the worker hands each run's picture to the polling thread and
    # waits for it (a bare join left every run waiting out the capture timeout, 60 s each).
    model.wait(timeout=60.0)
    assert not model.running and model.message == "Batch complete", model.message
    assert {row["Run"] for row in model._result_rows} == {str(i + 1) for i in range(N_DATASETS)}
    path = make_demo()
    assert path.is_file() and path.stat().st_size > 0
