"""Shared recipe for the classic TCSPC fits other tests build on.

The Qt editor tests that lived here went with the Qt editors; ``_fit`` is imported by
other tests as the way to make a convolved decay fit of a BFF family.
"""

from __future__ import annotations

import numpy as np

import chisurf as cs
import chisurf.core.fitting.fit as fit_mod
from chisurf.core.data import DataCurve
from chisurf.core.fluorescence.tcspc.irf import synthetic_irf
from chisurf.core.models.description import for_family


def _fit(family: str):
    x = np.arange(512) * 0.05
    irf = synthetic_irf(x, center_ns=2.0, fwhm_ns=0.2, norm=True) * 1e4
    y = 1e4 * np.exp(-x / 3.0) + 10.0
    fit = fit_mod.FitGroup(
        data=cs.core.data.DataCurveGroup([DataCurve(x=x, y=y, ey=np.sqrt(y), name="decay")]),
        model_class=for_family(family),
    )
    model = fit.grouped_fits[0].model
    model.set_dataset("response", DataCurve(x=x, y=irf, name="irf"))
    model.problem
    return fit, model
