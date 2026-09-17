"""Simulation self-test of the Fit23 lifetime engine the burst-MLE wizard uses.

Generates a decay from tttrlib's own forward model at a known lifetime,
Poisson-samples it, and fits it back. This pins that the fit MACHINERY is correct
and well-conditioned — so when a real-data fit is poor, it is the IRF/background
quality (the auto-extracted IRF is decay-shaped, hence the "use a measured IRF"
warning), not the fitter. No GUI, no data files.

The forward model comes from ``DecayFit2.model_curve``, which is the curve
*independent of any data*. ``evaluate`` cannot be used to generate it: the model
profiles its amplitude against the observed counts, so with no data yet it
returns zeros.
"""

from __future__ import annotations

import numpy as np
import pytest
import tttrlib

from chisurf.core.fluorescence.mle.fit2x import (
    Fit2x,
    Fit2xModel,
    Fit2xSettings,
)


def _fitter(irf, bg, dt, period):
    """The estimator under test, built through the same seam chisurf uses."""
    return Fit2x(
        Fit2xSettings(
            dt=dt,
            period=period,
            irf=irf,
            background=bg,
            g_factor=1.0,
            l1=0.0,
            l2=0.0,
            soft_bifl_scatter=False,
        ),
        model=Fit2xModel.FIT23,
    )


def _simulate(tau_true, n=128, dt=0.05, period=32.0, counts=30000, seed=1):
    rng = np.random.RandomState(seed)
    t = np.arange(n)
    irf_half = np.exp(-0.5 * ((t - 10) / 1.2) ** 2)
    irf_half /= irf_half.sum()
    irf = np.concatenate([irf_half, irf_half])  # clean, narrow IRF
    bg = np.ones(2 * n) / (2 * n)  # flat background
    setup = tttrlib.setup_vector(
        "fit23",
        dt=dt,
        period=period,
        g_factor=1.0,
        l1=0.0,
        l2=0.0,
        convolution_stop=n - 1,
        soft_bifl_scatter_flag=False,
    )
    fit = tttrlib.DecayFit2("fit23", setup, irf.tolist())
    problem = tttrlib.DecayFitProblem(2, n, dt)
    problem.irf = tttrlib.VectorDouble(irf.tolist())
    problem.background = tttrlib.VectorDouble(bg.tolist())
    model = np.asarray(fit.model_curve([tau_true, 0.0, 0.0, 1.0], problem))
    data = rng.poisson(model / model.sum() * counts).astype(float)
    return data, irf, bg, dt, period


@pytest.mark.parametrize("tau_true", [1.5, 2.0, 3.5, 4.0])
def test_fit23_recovers_known_lifetime(tau_true):
    data, irf, bg, dt, period = _simulate(tau_true)
    res = _fitter(irf, bg, dt, period).fit(
        data,
        initial_values=[1.0, 0.0, 0.0, 1.0],  # deliberately wrong start
        fixed=[0, 1, 1, 1],
    )
    recovered = float(res.x[0])
    two_istar = float(res.twoIstar)
    assert recovered == pytest.approx(tau_true, rel=0.05), (
        f"tau {recovered} not within 5% of {tau_true}"
    )
    # A clean IRF/background should give an excellent fit (2I* near 1).
    assert two_istar < 1.5, f"2I* {two_istar} too high for a clean simulation"


def test_fit23_is_well_conditioned_across_starts():
    # The minimiser must converge to the same lifetime from very different starts.
    data, irf, bg, dt, period = _simulate(3.0)
    fitter = _fitter(irf, bg, dt, period)
    taus = []
    for start in (0.5, 2.0, 6.0):
        res = fitter.fit(
            data,
            initial_values=[start, 0.0, 0.0, 1.0],
            fixed=[0, 1, 1, 1],
        )
        taus.append(float(res.x[0]))
    assert max(taus) - min(taus) < 0.1, f"start-dependent fit: {taus}"
