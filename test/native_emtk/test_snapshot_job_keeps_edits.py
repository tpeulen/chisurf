"""A finished background job never puts a field back to the value it had when the job started.

Every emtk tool computes on a copy of its model (:class:`chisurf.emtk.jobs.SnapshotJob`) and merges
the copy back when the job is done. A value typed into the form meanwhile used to be overwritten by
the merge -- the field "snapped back". The form's edits are recorded and written again after it.
"""

from __future__ import annotations

import threading

from emtk.view_form import FormState, _commit

from chisurf.emtk.jobs import SnapshotJob


class Model:
    def __init__(self):
        self.window_stop = 59
        self.result = None
        self.gate = threading.Event()

    def __copy__(self):
        twin = object.__new__(Model)
        twin.__dict__ = dict(self.__dict__)
        return twin

    def notify(self, event):
        pass

    def compute(self):
        self.gate.wait(5)
        self.result = "fitted"


def _finish(job):
    job.thread.join(5)
    assert job.poll()


def test_a_value_typed_while_the_job_runs_survives_the_merge():
    model = Model()
    job = SnapshotJob(model)
    job.start("compute")
    _commit(model, {"attr": "window_stop"}, 100, FormState())  # the user types meanwhile
    model.gate.set()
    _finish(job)
    assert model.result == "fitted"  # the job's work is merged
    assert model.window_stop == 100  # and the edit is not undone


def test_only_the_jobs_own_model_and_only_while_it_runs_are_recorded():
    model, other = Model(), Model()
    job = SnapshotJob(model)
    _commit(model, {"attr": "window_stop"}, 70, FormState())  # before: nothing to replay
    job.start("compute")
    _commit(other, {"attr": "window_stop"}, 1, FormState())
    assert job.edits == []
    model.gate.set()
    _finish(job)
    assert other.window_stop == 1 and model.window_stop == 70
    _commit(model, {"attr": "window_stop"}, 80, FormState())  # after: the listener is gone
    assert job.edits == []
