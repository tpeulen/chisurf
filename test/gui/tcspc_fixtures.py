"""Simulated TCSPC fits the project, plot and editor tests build on.

Not a test module on purpose: these builders used to live in two ``test_*`` files
whose Qt tests had gone, so the files looked like empty scripts and were deleted,
taking the fixtures every importer needed with them.
"""

from __future__ import annotations

import numpy as np

import chisurf as cs
import chisurf.core.fitting.fit as fit_mod
from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.fluorescence.decay import synthetic_decay
from chisurf.core.fluorescence.tcspc.irf import synthetic_irf
from chisurf.core.models.description import for_family
from chisurf.core.models.description import tcspc_lifetime as LifetimeModel


def _simulated_fit() -> FitGroup:
    """Return a two-curve global lifetime fit built from simulated TCSPC decays."""
    dt = 0.048
    time = np.arange(256, dtype=float) * dt
    irf = synthetic_irf(time, center_ns=1.5, fwhm_ns=0.18, norm=True)
    expected = 75_000.0 * (
        0.35 * synthetic_decay(256, [0.9], bin_width=dt, irf=irf, normalize=True)
        + 0.65 * synthetic_decay(256, [3.4], bin_width=dt, irf=irf, normalize=True)
    )
    counts_a = np.random.default_rng(7).poisson(expected).astype(float)
    counts_b = np.random.default_rng(8).poisson(expected * 0.72).astype(float)
    data_a = DataCurve(
        x=time,
        y=counts_a,
        ey=np.sqrt(np.maximum(counts_a, 1.0)),
        name="simulated-tcspc-a",
    )
    data_b = DataCurve(
        x=time,
        y=counts_b,
        ey=np.sqrt(np.maximum(counts_b, 1.0)),
        name="simulated-tcspc-b",
    )
    group = FitGroup(
        data=DataCurveGroup([data_a, data_b], name="simulated-tcspc-global"),
        model_class=LifetimeModel,
    )
    group.fit_range = (18, 230)
    for local_fit in group.grouped_fits:
        model = local_fit.model
        model.set_dataset("response", DataCurve(x=time, y=irf * 1e4, name="simulated-irf"))
        model.structure = "lifetime.components.2"
        values = {p.canonical_id: p for p in model.parameters_all}
        for canonical, value in (
            ("lifetime.tau.0", 1.1),
            ("lifetime.tau.1", 3.1),
            ("lifetime.amplitude.0", 0.4),
            ("lifetime.amplitude.1", 0.6),
        ):
            values[canonical].value = value
    group.update()
    return group


def _fit(family: str):
    """Return ``(fit, model)``: a convolved single-decay fit of the BFF *family*."""
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
