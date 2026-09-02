"""Guardrail: `Mfd2DModel.update_model` no-ops loudly without a burst payload.

Constructing a fit before its MFD data is attached is a legal state (see
`Mfd2DModel.seed_from_data`'s own docstring) -- the curve simply stays at
`ModelCurve`'s zeroed placeholder. What must not happen is that placeholder
reading as "computed and correct" to anything watching, which is exactly the
"silent pass" the census
(`imp.bff/test/minimizer/census_models.py`, closed under PRD-121) was built to
catch: a decay-shaped fixture with no MFD payload used to construct the model
and let `update_model()` return with nothing said. It now warns, naming the
missing payload, every time it no-ops.
"""

from __future__ import annotations

from chisurf.core.fitting.fit import Fit
from chisurf.core.models.mfd import Mfd2DModel


def test_update_model_warns_when_no_burst_payload_is_attached(caplog):
    """No MFD data on the fit -> a named warning, curve left untouched."""
    fit = Fit(model_class=Mfd2DModel)  # no data => Fit's dummy ramp, no .mfd
    model = fit.model
    before = model.y.copy()

    with caplog.at_level("WARNING"):
        model.update_model()

    assert (model.y == before).all(), "a refused update must not silently change the curve"
    messages = [r.getMessage() for r in caplog.records]
    assert any("Mfd2DModel" in m and "payload" in m for m in messages), messages


def test_the_no_op_curve_is_flat(caplog):
    """The census's third column: a no-op leaves a degenerate (all-zero) curve."""
    import numpy as np

    fit = Fit(model_class=Mfd2DModel)
    model = fit.model

    with caplog.at_level("WARNING"):
        model.update_model()

    assert np.all(np.isfinite(model.y))
    assert np.ptp(model.y) == 0.0, "an un-fitted model must read as degenerate, not 'built'"
