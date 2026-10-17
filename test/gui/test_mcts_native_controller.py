"""Contracts for strict BFF-native model search dispatch, through the server service.

The Qt fit controller that used to dispatch the search is gone; ``fit_model_search`` and
``fit_model_search_available`` in ``chisurf.server.services.fits`` are the one entry point now.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from chisurf.core.fitting.mcts.native import NativeSearchPreparation, NativeSearchReason
from chisurf.server.services import fits as fits_service


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


class _AskingResult(_Result):
    def get_outcome(self):
        return "request_information"

    def get_missing_observables(self):
        return ["decay_aa"]


@pytest.fixture
def fit(monkeypatch):
    """A stand-in fit the service resolves; the search machinery is what is under test."""
    stub = SimpleNamespace(name="global fit", unique_identifier="fit-1")
    monkeypatch.setattr(fits_service, "_resolve_fit", lambda *_a, **_k: (stub, 0))
    return stub


def _prepared(monkeypatch, prepared):
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.dispatcher.prepare_model_search",
        lambda _fit, **_kw: prepared,
    )


def test_unsupported_fit_reports_reason_without_running_or_mutating(monkeypatch, fit):
    _prepared(
        monkeypatch,
        NativeSearchPreparation(
            "test.unsupported",
            reasons=(NativeSearchReason("no_native_graph", "model uses a Python node"),),
        ),
    )
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.execution.run_native_search",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("search ran")),
    )

    result = fits_service.fit_model_search(None, 0)

    assert result["ok"] is False
    assert "no_native_graph: model uses a Python node" in str(result)


def test_native_winner_is_applied_once(monkeypatch, fit):
    applied = []
    problem = object()
    binding = SimpleNamespace(
        apply_state=lambda received, state: applied.append((received, state.get_structure_key()))
    )
    _prepared(monkeypatch, NativeSearchPreparation("test.native", problem=problem, binding=binding))
    searches = []

    def run_native(received_problem, settings, **_kw):
        searches.append(received_problem)
        return _Result()

    monkeypatch.setattr("chisurf.core.fitting.mcts.execution.run_native_search", run_native)

    result = fits_service.fit_model_search(None, 0)

    assert searches == [problem]
    assert applied == [(problem, "selected-structure")]
    assert result["ok"] is True and result["outcome"] == "selected"
    assert result["structure"] == "selected-structure"
    assert result["reward"] == 12.5 and result["improvement"] == 4.25


def test_cancelled_native_search_never_applies(monkeypatch, fit):
    applied, restored = [], []
    problem = object()
    binding = SimpleNamespace(
        apply_state=lambda *_a: applied.append(True),
        restore=lambda p: restored.append(p),
    )
    _prepared(monkeypatch, NativeSearchPreparation("test.native", problem=problem, binding=binding))
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.execution.run_native_search",
        lambda *_a, **_k: _Result(cancelled=True),
    )

    result = fits_service.fit_model_search(None, 0)

    assert applied == []
    assert result["outcome"] == "cancelled"
    assert restored == [problem]


def test_a_search_asking_for_a_measurement_keeps_the_users_model(monkeypatch, fit):
    applied, restored = [], []
    problem = object()
    binding = SimpleNamespace(
        apply_state=lambda *_a: applied.append(True),
        restore=lambda p: restored.append(p),
    )
    _prepared(monkeypatch, NativeSearchPreparation("test.native", problem=problem, binding=binding))
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.execution.run_native_search",
        lambda *_a, **_k: _AskingResult(),
    )

    result = fits_service.fit_model_search(None, 0)

    assert applied == [] and restored == [problem]
    assert result["outcome"] == "request_information" and result["missing"] == ["decay_aa"]


def test_search_fit_settings_reaches_the_preparation(monkeypatch, fit):
    asked = []
    prepared = NativeSearchPreparation(
        "test.native", problem=object(), binding=SimpleNamespace(apply_state=lambda *_a: None)
    )

    def prepare(_fit, *, search_fit_settings=False):
        asked.append(search_fit_settings)
        return prepared

    monkeypatch.setattr("chisurf.core.fitting.mcts.dispatcher.prepare_model_search", prepare)
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.execution.run_native_search",
        lambda *_a, **_k: _Result(),
    )

    fits_service.fit_model_search(None, 0, search_fit_settings=True)

    assert asked == [True]


@pytest.mark.parametrize("available", [True, False])
def test_the_search_is_offered_only_when_bff_can_search(monkeypatch, fit, available):
    monkeypatch.setattr(
        "chisurf.core.fitting.mcts.dispatcher.model_search_available", lambda _fit: available
    )
    assert fits_service.fit_model_search_available(None, 0)["available"] is available


def test_a_real_parse_fit_is_searched_through_bff(monkeypatch):
    """The service reaches BFF for a non-TCSPC model family."""
    import chisurf
    from chisurf.core.data import DataCurve
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.parse import ParseModel

    x = np.linspace(0.0, 5.0, 64)
    y = 1.5 + 2.25 * x
    real = Fit(data=DataCurve(x=x, y=y, ey=np.ones_like(y)), model_class=ParseModel)
    real.fit_range = (0, len(x))
    real.model.func = "offset+slope*x"
    real.model.find_parameters()
    real.model.parameters_all_dict["offset"].value = 0.0
    real.model.parameters_all_dict["slope"].value = 1.0
    monkeypatch.setattr(fits_service, "_resolve_fit", lambda *_a, **_k: (real, 0))
    monkeypatch.setitem(
        chisurf.core.settings.cs_settings["optimization"],
        "mcts",
        {"n_simulations": 12, "seed": 3},
    )

    result = fits_service.fit_model_search(None, 0)

    assert result["ok"] is True, result
    assert real.model.parameter_dict["offset"].value == pytest.approx(1.5)
    assert real.model.parameter_dict["slope"].value == pytest.approx(2.25)
