"""Guardrail: `FidaModel` refuses a non-count axis instead of fitting it.

`FidaModel.update_model` used to compute on whatever axis its dataset carried
-- a TCSPC time axis, say -- by indexing the FIDA histogram with that axis
rounded to the nearest integer. The result was finite and non-constant, so it
looked like a real fit; it was numbered by an axis that has nothing to do
with photon counts. This is the census "silent pass" recorded in
``okf/references/graph-eligibility-verdicts.md`` and closed under PRD-121: the
model now refuses through the same ``0, 1, ... k_max`` check
``chisurf.core.models.pch.pch`` uses for the sibling multi-component model,
warns naming the problem, and leaves the curve flat rather than computing
nonsense.
"""

from __future__ import annotations

import numpy as np

import chisurf.core.data
import chisurf.core.fitting.fit as fit_module
from chisurf.core.models.pch.fida_model import FidaModel


def _make_fit(x, y):
    curve = chisurf.core.data.DataCurve(
        x=np.asarray(x, dtype=float), y=np.asarray(y, dtype=float),
        ey=np.ones_like(np.asarray(y, dtype=float)),
    )
    fit = fit_module.Fit(model_class=FidaModel, data=curve)
    fit.xmin, fit.xmax = 0, curve.y.size
    model = fit.model
    model._q[0].value = 2.0
    model._n[0].value = 2.0
    return fit, model


def test_fida_refuses_a_decay_shaped_axis(caplog):
    """A TCSPC time axis (not integer photon counts) is refused, not fitted."""
    x = np.arange(64) * 0.032  # ns, not photon counts
    fit, model = _make_fit(x, np.zeros_like(x))

    with caplog.at_level("WARNING"):
        model.update()

    assert model.y.size == x.size
    assert np.all(model.y == 0.0), "a refused axis must leave a flat curve, not a computed one"
    messages = [r.getMessage() for r in caplog.records]
    assert any("FIDA" in m for m in messages), messages


def test_fida_refuses_a_gapped_integer_axis(caplog):
    """Integers that skip a count (0, 2, 4, ...) are refused too."""
    k = np.arange(0, 40, 2, dtype=float)
    fit, model = _make_fit(k, np.zeros_like(k))

    with caplog.at_level("WARNING"):
        model.update()

    assert np.all(model.y == 0.0)
    assert any("FIDA" in r.getMessage() for r in caplog.records)


def test_fida_computes_on_a_real_count_axis():
    """The genuine article -- 0, 1, ... k_max -- is accepted and computed."""
    k = np.arange(40, dtype=float)
    fit, model = _make_fit(k, np.zeros_like(k))

    model.update()

    assert model.y.size == k.size
    assert np.all(np.isfinite(model.y))
    assert np.ptp(model.y) > 0.0, "a genuine PCH axis must not read as a degenerate curve"
