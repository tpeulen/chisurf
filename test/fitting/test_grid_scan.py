"""The coarse grid scan that finds a basin before the local fit descends."""

import numpy as np
import pytest

from chisurf.core.fitting.grid_scan import (
    ScanAborted,
    grid_scan,
    scan_axis,
)
from chisurf.core.fitting.parameter import FittingParameter


def _param(value, lb=None, ub=None):
    p = FittingParameter(name="p", value=value)
    if lb is not None:
        p.lb, p.ub, p.bounds_on = lb, ub, True
    return p


def test_axis_stays_inside_armed_bounds():
    axis = scan_axis(_param(2.0, 1.0, 5.0), points=5)
    assert axis.min() >= 1.0 and axis.max() <= 5.0
    assert 2.0 in axis  # the start is always tried


def test_axis_without_bounds_is_geometric_around_the_value():
    axis = scan_axis(_param(2.0), points=5)
    assert axis.min() == pytest.approx(0.5)  # value / 4
    assert axis.max() == pytest.approx(8.0)  # value * 4
    assert 2.0 in axis


def test_axis_of_a_zero_valued_parameter_is_finite():
    axis = scan_axis(_param(0.0), points=5)
    assert np.isfinite(axis).all() and 0.0 in axis


def test_the_scan_finds_the_other_well():
    """The point of it: the start is in the shallow well, the answer is not."""

    def cost(values):
        x = float(values[0])
        return float(min((x - 1.0) ** 2 + 0.5, 0.2 * (x - 6.0) ** 2))

    p = _param(1.0, 0.0, 10.0)
    result = grid_scan([p], cost, points=21, apply_best=True)

    assert result and result.improved
    assert p.value == pytest.approx(6.0, abs=0.6)


def test_a_scan_that_cannot_improve_leaves_everything_alone():
    p = _param(3.0, 0.0, 10.0)
    result = grid_scan([p], lambda v: float((v[0] - 3.0) ** 2), points=11, apply_best=True)

    assert not result.improved
    assert p.value == pytest.approx(3.0)


def test_values_are_restored_unless_asked_for():
    p = _param(1.0, 0.0, 10.0)
    result = grid_scan([p], lambda v: float((v[0] - 8.0) ** 2), points=11)

    assert result.values[0] == pytest.approx(8.0, abs=0.6)
    assert p.value == pytest.approx(1.0)  # not applied
    assert result.apply() and p.value == pytest.approx(8.0, abs=0.6)


def test_a_point_that_cannot_be_evaluated_is_skipped():
    def cost(values):
        if values[0] > 5.0:
            raise RuntimeError("model does not exist there")
        return float((values[0] - 4.0) ** 2)

    p = _param(1.0, 0.0, 10.0)
    result = grid_scan([p], cost, points=11, apply_best=True)

    assert p.value == pytest.approx(4.0, abs=0.6)
    assert result.evaluations < 11


def test_the_budget_bounds_the_work():
    calls = []
    params = [_param(1.0, 0.0, 2.0), _param(1.0, 0.0, 2.0), _param(1.0, 0.0, 2.0)]
    grid_scan(params, lambda v: calls.append(v) or 1.0, budget=64)

    assert len(calls) <= 100  # 4 points per axis, not 64 per axis


def test_too_many_parameters_is_no_scan():
    params = [_param(1.0, 0.0, 2.0) for _ in range(5)]
    result = grid_scan(params, lambda v: 1.0)

    assert not result and result.evaluations == 0


def test_the_cost_can_stop_the_scan():
    def cost(values):
        raise ScanAborted("cancelled")

    with pytest.raises(ScanAborted):
        grid_scan([_param(1.0, 0.0, 2.0)], cost)


def test_a_fit_can_scan_its_own_parameters():
    """``Fit.grid_scan`` moves a fit out of the wrong basin before it runs."""
    import chisurf.core.fitting.fit as fit_mod
    from chisurf.core.data import DataCurve
    from chisurf.core.models.parse import ParseModel

    x = np.linspace(0.0, 1.0, 60)
    truth = 3.0
    y = np.sin(2.0 * np.pi * truth * x)
    data = DataCurve(x=x.copy(), y=y.copy())
    data.ey = np.ones_like(y)

    fit = fit_mod.Fit(model_class=ParseModel, data=data)
    fit.model.func = "sin(2*3.141592653589793*f*x)"
    fit.fit_range = (0, len(x) - 1)
    frequency = fit.model.parameters_all_dict["f"]
    frequency.lb, frequency.ub, frequency.bounds_on = 0.5, 6.0, True
    frequency.value = 0.7  # a wrong period: the local fit cannot get out

    fit.run()
    local_only = float(frequency.value)

    frequency.value = 0.7
    result = fit.grid_scan(points=25)
    fit.run()

    assert result and result.improved
    assert abs(frequency.value - truth) < abs(local_only - truth)
    assert frequency.value == pytest.approx(truth, abs=0.05)
