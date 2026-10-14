"""Shared simulated-TCSPC fit fixture used by the project and plot tests.

The Qt fitting-window round trip that lived here is retired with the Qt shell; the Qt-free
``_simulated_fit`` builder stays because project and plot tests import it.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.data import DataCurve, DataCurveGroup
from chisurf.core.fitting.fit import FitGroup
from chisurf.core.fluorescence.decay import synthetic_decay
from chisurf.core.fluorescence.tcspc.irf import synthetic_irf
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
