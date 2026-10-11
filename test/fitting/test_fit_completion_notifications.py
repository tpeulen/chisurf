"""Computed fit results still notify every scientific owner without recomputing."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import Fit, FitGroup
from chisurf.core.models.global_model.globalfit import GlobalFitModel
from chisurf.core.models.parse import ParseModel


def _curve(index: int = 0) -> DataCurve:
    """Return a deterministic curve with a deliberately non-unit chi-square."""
    x = np.linspace(0.0, 10.0, 40)
    y = 2 * x + index + np.random.default_rng(123 + index).normal(0, 0.4, x.size)
    return DataCurve(x=x, y=y, ey=np.full(x.size, 0.1), name=f"curve-{index}")


def _configure(fit: Fit) -> None:
    """Set the real equation and the complete data window."""
    fit.fit_range = (0, len(fit.data.y))
    fit.model.func = "a*x+b"
    fit.model.update()


@pytest.fixture
def events(monkeypatch):
    """Record the production shared-bus boundary without starting a server."""
    import chisurf.server.startup as startup

    recorded = []

    class Bus:
        """Collect actual completion publications."""

        def publish(self, topic, payload):
            """Remember the event exactly as subscribers receive it."""
            recorded.append((topic, payload))

    monkeypatch.setattr(startup, "get_shared_event_bus", lambda: Bus())
    return recorded


@pytest.mark.parametrize("grouped", [False, True])
@pytest.mark.parametrize("notify", [False, True])
def test_graph_result_notifies_without_a_second_model_evaluation(
    events, monkeypatch, grouped, notify
):
    """The real C++ graph writes back once even when display events are enabled."""
    import chisurf.core.fitting.minimizer as minimizer

    if grouped:
        fit = FitGroup(data=DataCurveGroup([_curve(0), _curve(1)]), model_class=ParseModel)
        members = fit.grouped_fits
    else:
        fit = Fit(data=_curve(), model_class=ParseModel)
        members = [fit]
    for member in members:
        _configure(member)
    model = fit._model if grouped else fit.model
    assert minimizer.graph_objective(fit, model) is not None
    counts = {id(member): 0 for member in members}
    for member in members:
        original = member.model.update

        def count_update(*args, _member=member, _original=original, **kwargs):
            """Count the production model computation rather than a mock fit."""
            counts[id(_member)] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(member.model, "update", count_update)
    kwargs = {"local_first": False} if grouped else {}
    fit.run(estimate_errors=False, record_result=False, finalize=False, notify=notify, **kwargs)
    assert list(counts.values()) == [1] * len(members)
    expected = {fit.unique_identifier, *(member.unique_identifier for member in members)}
    assert {payload["fit_uid"] for topic, payload in events if topic == "fit.updated"} == (
        expected if notify else set()
    )


def test_global_fit_update_notifies_exact_member_owners(events):
    """The editor's global model holds the same fits whose windows need repainting."""
    members = [Fit(data=_curve(i), model_class=ParseModel) for i in range(2)]
    for member in members:
        _configure(member)
    fit = Fit(data=_curve(), model_class=GlobalFitModel)
    for member in members:
        fit.model.append_fit(member)
    fit.update()
    assert {payload["fit_uid"] for topic, payload in events if topic == "fit.updated"} == {
        fit.unique_identifier,
        *(member.unique_identifier for member in members),
    }


def test_global_update_notifies_group_and_leaf_owners_once(events):
    """A global editor may reference groups whose leaf fits have their own observers."""
    member = FitGroup(data=DataCurveGroup([_curve()]), model_class=ParseModel)
    _configure(member.grouped_fits[0])
    fit = Fit(data=_curve(), model_class=GlobalFitModel)
    fit.model.append_fit(member)
    fit.update()
    uids = [payload["fit_uid"] for topic, payload in events if topic == "fit.updated"]
    assert set(uids) == {
        fit.unique_identifier,
        member.unique_identifier,
        member.grouped_fits[0].unique_identifier,
    }
    assert len(uids) == len(set(uids))
