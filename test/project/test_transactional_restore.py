"""Transactional project restoration at the macro boundary."""

from __future__ import annotations

import copy

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.data import DataCurve
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.project import capture_session
from chisurf.macros.core_fit import load_project_payload
from test.project.test_server_project_snapshot import SnapshotLinearModel


def _live_science():
    """Real live science: restore fingerprints what a transition may discard."""
    curve = DataCurve(x=np.arange(4.0), y=np.array([2.0, 5.0, 8.0, 11.0]), name="live")
    fit = FitGroup(data=[curve], model_class=SnapshotLinearModel)
    return curve, fit


class _MutatingBrokenHistory:
    def __init__(self) -> None:
        self._events = [{"action_type": "old"}]
        self._checkpoints = {0: "old-checkpoint"}

    def list_events(self):
        return list(self._events)

    def load_events(self, events, replace=True):
        self._events = list(events)
        self._checkpoints.clear()
        raise RuntimeError("history listener rejected restore")


def test_history_failure_rolls_back_science_history_and_selection(monkeypatch):
    old_dataset, old_fit = _live_science()
    monkeypatch.setattr(cs, "imported_datasets", [old_dataset])
    monkeypatch.setattr(cs, "fits", [old_fit])
    monkeypatch.setattr(cs, "current_fit", old_fit, raising=False)
    monkeypatch.setattr(cs, "current_fit_idx", 0, raising=False)
    history = _MutatingBrokenHistory()
    monkeypatch.setattr(cs, "history", history, raising=False)
    old_history_state = copy.deepcopy(history.__dict__)

    project = capture_session([], [], name="candidate")
    project.extra = {"history_events": [{"action_type": "new"}]}

    with pytest.raises(RuntimeError, match="history listener rejected restore"):
        load_project_payload(project)

    assert cs.imported_datasets == [old_dataset]
    assert cs.fits == [old_fit]
    assert cs.current_fit is old_fit
    assert cs.current_fit_idx == 0
    assert history.__dict__ == old_history_state


def test_invalid_saved_selection_fails_before_replacing_live_state(monkeypatch):
    old_dataset, old_fit = _live_science()
    monkeypatch.setattr(cs, "imported_datasets", [old_dataset])
    monkeypatch.setattr(cs, "fits", [old_fit])
    project = capture_session([], [], name="candidate")
    project.ui_state["current_fit_index"] = 1

    with pytest.raises(ValueError, match="current_fit_index"):
        load_project_payload(project)

    assert cs.imported_datasets == [old_dataset]
    assert cs.fits == [old_fit]
