"""TCSPC decay equations as a view on BFF: equation -> Convolution -> instrument.

The references were recorded from the classic ParseDecayModel before it was
deleted (``data/parsed_decay_reference.json``): every catalogue entry under
four instrument settings -- plain; a fractional timeshift with scatter,
background and a fixed scale; autoscaling against the data; pile-up.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

bff = pytest.importorskip("IMP.bff")

import chisurf.core.curve
import chisurf.core.data
import chisurf.core.fitting.fit as F
from chisurf.core.models.tcspc.parse.tcspc_parse import ParseDecayModel

REFERENCE = json.loads((pathlib.Path(__file__).parent / "data" / "parsed_decay_reference.json").read_text())


def _view(y=None):
    x = np.asarray(REFERENCE["x"])
    y = np.asarray(REFERENCE["data"]) if y is None else y
    ey = np.asarray(REFERENCE["ey"])
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=ey)
    fit = F.Fit(model_class=ParseDecayModel, data=data)
    fit.xmin, fit.xmax = 0, x.size
    model = fit.model
    model.set_dataset("response", chisurf.core.curve.Curve(x=x, y=np.asarray(REFERENCE["irf"])))
    model.set_scalar("period", 1000.0 / REFERENCE["rep_rate"])
    return fit, model


def _set(problem, values):
    for name, value in values.items():
        port = problem.get_parameter(name)
        held = port.fixed
        port.fixed = False
        port.value = value
        port.fixed = held


@pytest.mark.parametrize("case", sorted(REFERENCE["cases"]))
def test_every_equation_under_every_instrument_setting_reproduces_the_classic_curve(case):
    record = REFERENCE["cases"][case]
    settings = record["settings"]
    fit, model = _view()
    model.set_scalar("autoscale", 1.0 if settings["autoscale"] else 0.0)
    model.set_scalar("pile_up", 1.0 if settings["pileup"] else 0.0)
    if settings["pileup"]:
        model.set_scalar("dead_time", record["dead_time"])
        model.set_scalar("measurement_time", record["measurement_time"])
    problem = model.problem
    assert problem is not None, model.missing
    model.structure = record["entry"]
    _set(problem, record["values"])
    _set(problem, {
        "instrument.timeshift": settings["ts"],
        "instrument.scatter": settings["sc"],
        "instrument.background": settings["bg"],
        "instrument.n0": settings["n0"],
    })
    model.update()
    np.testing.assert_allclose(model.y, record["y"], rtol=1e-9, atol=1e-9)
    if settings["autoscale"]:
        assert problem.get_parameter("instrument.n0").value == pytest.approx(record["n0_after"], rel=1e-9)


def test_a_fit_recovers_the_equation_that_made_the_decay():
    record = REFERENCE["cases"][next(k for k in sorted(REFERENCE["cases"]) if k.endswith("|shifted"))]
    fit, model = _view()
    problem = model.problem
    model.structure = record["entry"]
    truth = dict(record["values"])
    _set(problem, truth)
    _set(problem, {"instrument.background": 4.0, "instrument.n0": 2.5})
    model.update()
    clean = np.array(model.y)

    fit, model = _view(clean)
    problem = model.problem
    model.structure = record["entry"]
    start = {k: v * 1.2 for k, v in truth.items()}
    _set(problem, start)
    _set(problem, {"instrument.n0": 2.5})
    fit.run()
    for name, value in truth.items():
        if not problem.get_parameter(name).fixed:
            assert problem.get_parameter(name).value == pytest.approx(value, rel=1e-3), name
