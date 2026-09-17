"""Equation models as views on BFF, in as many dimensions as the data has.

The references were recorded from the classic ParseFCSModel, ParsePCFModel,
ParseStoppedFlowModel, ImageCorrelationModel and IcsGaussian2DModel before
they were deleted (``data/parsed_reference.json``): every catalogue entry at
its initial values, and the image-correlation carpets with every optional term
switched on. The views must reproduce them from the catalogues alone.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pytest

bff = pytest.importorskip("IMP.bff")

import chisurf.core.data
import chisurf.core.fitting.fit as F
from chisurf.core.experiments.ics.data import carpet_coordinates
from chisurf.core.models.fcs.parse import ParseFCSModel
from chisurf.core.models.ics.ics import ImageCorrelationModel
from chisurf.core.models.pcf.parse import ParsePCFModel
from chisurf.core.models.stopped_flow.parse import ParseStoppedFlowModel

REFERENCE = json.loads(
    (pathlib.Path(__file__).parent / "data" / "parsed_reference.json").read_text()
)
CLASSES = {"fcs": ParseFCSModel, "pcf": ParsePCFModel, "stopped_flow": ParseStoppedFlowModel}


def _set(problem, values):
    for name, value in values.items():
        port = problem.get_parameter(name)
        held = port.fixed
        port.fixed = False
        port.value = value
        port.fixed = held


def _curve_fit(cls, x, y, ey=None):
    data = chisurf.core.data.DataCurve(x=x, y=y, ey=np.ones_like(y) if ey is None else ey)
    fit = F.Fit(model_class=cls, data=data)
    fit.xmin, fit.xmax = 0, x.size
    return fit


@pytest.mark.parametrize("label", sorted(CLASSES))
def test_every_catalogue_entry_reproduces_the_classic_curve(label):
    reference = REFERENCE["curves"][label]
    x = np.asarray(reference["x"])
    fit = _curve_fit(CLASSES[label], x, np.ones_like(x))
    model = fit.model
    problem = model.problem
    assert problem is not None, model.missing
    for key, entry in reference["entries"].items():
        model.structure = key
        _set(problem, entry["values"])
        model.update()
        np.testing.assert_allclose(model.y, entry["y"], rtol=1e-9, atol=1e-12, err_msg=key)


def _carpet_fit(record, y=None):
    meta = {k: (np.asarray(v) if isinstance(v, list) else v) for k, v in record["meta"].items()}
    y = np.asarray(record["y"]) if y is None else y
    frames = int(np.atleast_1d(meta.get("frame_lags", [0])).size)
    data = chisurf.core.data.DataCurve(
        x=np.arange(y.size, dtype=float), y=y, ey=np.full(y.size, 1e-3)
    )
    data.meta_data["ics"] = meta
    data.meta_data["coordinates"] = carpet_coordinates(meta)
    data.meta_data["grid"] = {
        "ndim": 3,
        "shape": (frames,) + np.asarray(meta["pixel_shift"]).shape,
        "order": "C",
    }
    data.meta_data["parameter_defaults"] = {"pxl_size": 40.0}
    fit = F.Fit(model_class=ImageCorrelationModel, data=data)
    fit.xmin, fit.xmax = 0, y.size
    return fit


@pytest.mark.parametrize(
    "record, entry",
    [
        ("image_correlation_3d", "Image correlation (3D)"),
        ("image_correlation_2d", "Image correlation (2D membrane)"),
        ("gaussian_2d", "2D Gaussian (2 sigma + angle)"),
    ],
)
def test_the_carpet_equations_reproduce_the_classic_carpets(record, entry):
    reference = REFERENCE["ics"][record]
    fit = _carpet_fit(reference)
    model = fit.model
    problem = model.problem
    assert problem is not None, model.missing
    model.structure = entry
    _set(problem, reference["values"])
    model.update()
    np.testing.assert_allclose(model.y, reference["y"], rtol=1e-9, atol=1e-12)


def test_the_carpet_pixel_size_comes_from_the_data_and_is_held():
    fit = _carpet_fit(REFERENCE["ics"]["image_correlation_3d"])
    problem = fit.model.problem
    assert problem.get_parameter("pxl_size").value == 40.0
    assert problem.get_parameter_locked("pxl_size")


def test_a_rics_fit_recovers_transport_from_the_carpet():
    reference = REFERENCE["ics"]["image_correlation_3d"]
    fit = _carpet_fit(reference)
    model = fit.model
    problem = model.problem
    model.structure = "Image correlation (3D)"
    truth = {"N": 4.0, "D": 1.5, "offset": 0.01}
    _set(problem, truth)
    model.update()
    clean = np.array(model.y)
    fit = _carpet_fit(reference, y=clean)
    model = fit.model
    problem = model.problem
    model.structure = "Image correlation (3D)"
    _set(problem, {"N": 2.0, "D": 1.0, "offset": 0.005})
    fit.run()
    assert problem.get_parameter("N").value == pytest.approx(4.0, rel=1e-3)
    assert problem.get_parameter("D").value == pytest.approx(1.5, rel=1e-3)


def test_search_over_a_catalogue_picks_the_equation_that_made_the_data():
    x = np.geomspace(1e-4, 10.0, 96)
    fit = _curve_fit(ParseFCSModel, x, np.ones_like(x))
    model = fit.model
    problem = model.problem
    keys = list(problem.get_structure_keys())
    model.structure = keys[0]
    _set(
        problem, {k: v for k, v in REFERENCE["curves"]["fcs"]["entries"][keys[0]]["values"].items()}
    )
    model.update()
    y = np.array(model.y)

    fit = _curve_fit(ParseFCSModel, x, y, ey=np.full(x.size, 1e-3))
    from chisurf.core.fitting.mcts.dispatcher import prepare_model_search

    prepared = prepare_model_search(fit)
    assert prepared.supported, prepared.reasons
    root = prepared.problem.get_initial_state()
    assert root.get_structure_key() == keys[0]
    # Every other catalogue entry is one move away and scores worse on BIC.
    for action in prepared.problem.get_actions(root):
        if action.get_terminal():
            continue
        other = prepared.problem.evaluate(root, action)
        assert other.get_reward() <= root.get_reward() + 1e-9, action.get_key()


def test_a_typed_equation_keeps_the_ports_it_shares():
    x = np.geomspace(1e-4, 10.0, 48)
    fit = _curve_fit(ParseFCSModel, x, np.ones_like(x))
    model = fit.model
    uid = model.problem.get_parameter("N").uid
    model.set_equation("b + 1/abs(N)*(1+x/td)**(-gamma)")
    problem = model.problem
    assert problem.get_parameter("N").uid == uid
    assert "gamma" in list(problem.get_parameter_ids())
    model.structure = "custom"
    assert "gamma" in [p.canonical_id for p in model.parameters_all]
