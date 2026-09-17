"""Parameter discovery on a group that has not been updated yet.

A model attaches its parameters after ``FittingParameterGroup.__init__`` returns,
so discovery cannot run in the constructor. It used to run only as a side effect
of ``Model.update`` and ``FitGroup.run``, which meant a fit that had been built
but not yet updated reported *no parameters at all* to every reader outside the
model — the RPC fit DTOs, and through them the parameter link menu, which showed
an empty "All parameters" submenu with nothing to click and no error anywhere.
"""

from __future__ import annotations

import numpy as np
import pytest

import chisurf.core.data as data
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.models.description import tcspc_lifetime as LifetimeModel


def _fit(n_curves: int = 1) -> FitGroup:
    """Build a TCSPC fit group over *n_curves* synthetic decays."""
    curves = []
    for i in range(n_curves):
        x = np.arange(1, 64, dtype=np.float64)
        y = 1000.0 * np.exp(-x / 10.0) + 1.0
        curves.append(data.DataCurve(x=x, y=y, ey=np.sqrt(y), name=f"decay-{i}"))
    return FitGroup(
        data=data.DataCurveGroup(curves, name="decays"),
        model_class=LifetimeModel,
    )


def test_fresh_model_reports_its_parameters():
    """A model exposes its parameters without an explicit update or fit run."""
    model = _fit().model
    assert len(model.parameters_all) > 0
    assert len(model.parameters_all_dict) == len(model.parameters_all)


def test_discovery_result_matches_an_explicit_walk():
    """Lazy discovery yields the same parameters an explicit walk does."""
    model = _fit().model
    lazy = [p.name for p in model.parameters_all]
    model.find_parameters()
    assert [p.name for p in model.parameters_all] == lazy


def test_group_without_parameters_stays_empty():
    """An empty group is a real answer and is not re-walked into something else."""
    group = FittingParameterGroup(name="empty")
    assert group.parameters_all == []
    assert group.parameters_all == []


def test_appended_parameter_is_visible():
    """``append_parameter`` works on a group that has never been walked."""
    group = FittingParameterGroup(name="late")
    group.append_parameter(FittingParameter(name="a", value=1.0))
    assert [p.name for p in group.parameters_all] == ["a"]


@pytest.mark.parametrize("n_curves", [1, 2])
def test_every_member_of_a_group_reports_parameters(n_curves):
    """Each curve of a fit group carries its own parameters, not just the selected one."""
    fit = _fit(n_curves)
    assert len(fit.grouped_fits) == n_curves
    for member in fit.grouped_fits:
        assert len(member.model.parameters_all) > 0
