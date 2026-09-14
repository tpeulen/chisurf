"""GUI contracts for strict BFF-native model search dispatch."""

from __future__ import annotations

import inspect
from types import SimpleNamespace

import numpy as np
import pytest

from chisurf.core.fitting.mcts.native import (
    NativeSearchPreparation,
    NativeSearchReason,
)
from chisurf.gui.widgets.fitting.fit_controller import FittingControllerWidget


class _State:
    def get_structure_key(self):
        return "selected-structure"

    def get_reward(self):
        return 12.5


class _Result:
    def __init__(self, cancelled=False):
        self._cancelled = cancelled

    def get_cancelled(self):
        return self._cancelled

    def get_best_state(self):
        return _State()

    def get_acceptable(self):
        return True

    def get_improvement(self):
        return 4.25

    def get_number_of_simulations(self):
        return 19

    def get_number_of_states_evaluated(self):
        return 3


def _controller():
    controller = FittingControllerWidget.__new__(FittingControllerWidget)
    controller.fit = SimpleNamespace(name="global fit", unique_identifier="fit-1")
    controller._snapshots = iter(([{"value": 1.0}], [{"value": 2.0}]))
    controller._collect_parameter_snapshot = lambda: next(controller._snapshots)
    controller.history = []
    controller._record_history = lambda **entry: controller.history.append(entry)
    controller.refreshed = []
    controller._refresh_mcts_structure_ui = controller.refreshed.append
    return controller


def _run_inline(monkeypatch):
    def run_in_background(_parent, _text, worker, **kwargs):
        try:
            result = worker(SimpleNamespace(is_cancelled=False))
        except Exception as error:
            kwargs["on_error"](error)
        else:
            kwargs["on_result"](result)
        return SimpleNamespace()

    monkeypatch.setattr("chisurf.gui.task.run_in_background", run_in_background)


def test_unsupported_fit_reports_reason_without_running_or_mutating(monkeypatch):
    import chisurf as cs

    controller = _controller()
    warnings = []
    prepared = NativeSearchPreparation(
        "test.unsupported",
        reasons=(NativeSearchReason("no_native_graph", "model uses a Python node"),),
    )
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.dispatcher.prepare_model_search",
        lambda _fit: prepared,
    )
    monkeypatch.setattr(cs.logging, "warning", warnings.append)
    monkeypatch.setattr(
        "chisurf.gui.task.run_in_background",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search ran")),
    )

    controller.onRunMCTS()

    assert controller.history == []
    assert controller.refreshed == []
    assert warnings == [
        "BFF model search is unavailable for 'global fit': "
        "no_native_graph: model uses a Python node"
    ]


def test_gui_entry_point_has_no_legacy_search_engine_path():
    source = inspect.getsource(FittingControllerWidget.onRunMCTS)

    assert "MCTSFittingEngine" not in source
    assert "environment_from_fit" not in source
    assert "run_native_search" in source


def test_native_winner_is_applied_once_and_records_one_accepted_event(monkeypatch):
    controller = _controller()
    applied = []
    problem = object()
    binding = SimpleNamespace(
        apply_state=lambda received_problem, state: applied.append(
            (received_problem, state.get_structure_key())
        )
    )
    prepared = NativeSearchPreparation(
        "test.native", problem=problem, binding=binding
    )
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.dispatcher.prepare_model_search",
        lambda _fit: prepared,
    )
    searches = []

    def run_native(received_problem, settings, *, should_cancel):
        searches.append((received_problem, settings, should_cancel()))
        return _Result()

    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.execution.run_native_search", run_native
    )
    _run_inline(monkeypatch)

    controller.onRunMCTS()

    assert searches[0][0] is problem
    assert searches[0][2] is False
    assert applied == [(problem, "selected-structure")]
    assert controller.refreshed == [controller.fit]
    assert len(controller.history) == 1
    event = controller.history[0]
    assert event["action_type"] == "fit_run_finish"
    assert event["payload"]["operation"] == "bff_model_search"
    assert event["payload"]["capability_id"] == "test.native"
    assert event["payload"]["parameter_snapshot_before"] == [{"value": 1.0}]
    assert event["payload"]["parameter_snapshot_after"] == [{"value": 2.0}]


def test_cancelled_native_search_never_applies_or_records(monkeypatch):
    controller = _controller()
    applied = []
    prepared = NativeSearchPreparation(
        "test.native",
        problem=object(),
        binding=SimpleNamespace(apply_state=lambda *_args: applied.append(True)),
    )
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.dispatcher.prepare_model_search",
        lambda _fit: prepared,
    )
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.execution.run_native_search",
        lambda *_args, **_kwargs: _Result(cancelled=True),
    )
    _run_inline(monkeypatch)

    controller.onRunMCTS()

    assert applied == []
    assert controller.history == []
    assert controller.refreshed == []


def test_controller_runs_a_real_parse_fit_through_bff(monkeypatch):
    """The GUI entry point reaches BFF for a non-TCSPC model family."""
    import chisurf
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.parse import ParseModel

    x = np.linspace(0.0, 5.0, 64)
    y = 1.5 + 2.25 * x
    fit = Fit(
        data=DataCurve(x=x, y=y, ey=np.ones_like(y)),
        model_class=ParseModel,
    )
    fit.fit_range = (0, len(x))
    fit.model.func = "offset+slope*x"
    fit.model.find_parameters()
    fit.model.parameters_all_dict["offset"].value = 0.0
    fit.model.parameters_all_dict["slope"].value = 1.0

    controller = FittingControllerWidget.__new__(FittingControllerWidget)
    controller.fit = fit
    controller.history = []
    controller._record_history = lambda **entry: controller.history.append(entry)
    controller._refresh_mcts_structure_ui = lambda _fit: None
    _run_inline(monkeypatch)
    monkeypatch.setitem(
        chisurf.core.settings.cs_settings["optimization"],
        "mcts",
        {"n_simulations": 12, "seed": 3},
    )

    controller.onRunMCTS()

    assert fit.model.parameter_dict["offset"].value == pytest.approx(1.5)
    assert fit.model.parameter_dict["slope"].value == pytest.approx(2.25)
    assert len(controller.history) == 1
    assert controller.history[0]["payload"]["capability_id"] == (
        "chisurf.fixed-structure.v1"
    )
