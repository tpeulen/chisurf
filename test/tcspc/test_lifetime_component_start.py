"""Lifetime components must start apart, and inside their declared bounds.

Two defects the classic lifetime group had, pinned on the described model
(BFF's ``tcspc_lifetime``) that replaced it:

* every component started at the same value, so a two-exponential model began
  as **two identical exponentials** -- a start whose two Jacobian columns are
  the same vector, leaving the optimiser nothing to separate them with;
* lifetime bounds declared and never switched on, so the optimiser could walk
  past the excitation period, where the decay is a constant.
"""

import numpy as np
import pytest

pytest.importorskip("IMP.bff")

import chisurf.core.data
import chisurf.core.fitting.fit as fitting
from chisurf.core.models.description import for_family

DT, PERIOD = 0.05, 12.5


def _lifetimes(n: int):
    x = np.arange(256) * DT
    fit = fitting.Fit(
        model_class=for_family("tcspc_lifetime"),
        data=chisurf.core.data.DataCurve(x=x, y=np.round(1000.0 * np.exp(-x / 3.0)) + 5.0),
    )
    model = fit.model
    model.set_scalar("generated_response", 1.0)
    model.set_scalar("period", PERIOD)
    model.set_scalar("max_components", float(n))
    model.structure = f"lifetime.components.{n}"
    used = set(model.structure_parameter_ids())
    return [
        p
        for p in model.parameters_all
        if p.canonical_id.startswith("lifetime.tau.") and p.canonical_id in used
    ]


def test_components_do_not_start_on_top_of_each_other():
    values = [p.value for p in _lifetimes(4)]
    assert len(set(values)) == len(values), values


def test_the_starts_stay_inside_the_bounds():
    for parameter in _lifetimes(8):
        lower, upper = parameter.bounds
        assert lower <= parameter.value <= upper


def test_the_lifetime_bounds_are_positive_and_end_at_the_period():
    for parameter in _lifetimes(2):
        lower, upper = parameter.bounds
        assert lower > 0.0, "a lifetime is positive"
        assert upper == pytest.approx(PERIOD), "a lifetime past the period is a constant, not a fit"
