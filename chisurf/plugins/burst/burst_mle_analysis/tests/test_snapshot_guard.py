"""The edit guard a job's copy arms is released however the job ends."""

from __future__ import annotations

import time

import pytest

from chisurf.emtk import job_gate
from chisurf.emtk.jobs import SnapshotJob
from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel


def _finish(job: SnapshotJob, timeout: float = 10.0) -> None:
    end = time.monotonic() + timeout
    while job.busy and time.monotonic() < end:
        job.poll()
        time.sleep(0.01)
    assert not job.busy


@pytest.fixture()
def gate():
    job_gate.reset()
    job_gate.arm()
    yield
    job_gate.release()
    job_gate.disarm()
    job_gate.reset()


def test_a_job_stopped_while_held_leaves_the_model_editable(gate):
    """Stop before the worker computed: no snapshot merges back, the guard must still drop."""
    model = MleViewModel()
    job = SnapshotJob(model)
    assert job.start("run_batch")
    assert not model.enabled("load_example")  # locked while the job is open
    model.stop()  # the snapshot shares the Stop flag
    _finish(job)
    assert model.enabled("load_example")
    model.split_by_state = not model.split_by_state  # no "wait for the running job"


def test_a_job_that_refuses_its_input_leaves_the_model_editable():
    """``run_batch`` without bursts raises after releasing its own copy; the source unlocks too."""
    model = MleViewModel()
    job = SnapshotJob(model)
    assert job.start("run_batch")
    _finish(job)
    assert "burst files" in job.error
    assert model.enabled("load_example")
    model.split_by_state = True
