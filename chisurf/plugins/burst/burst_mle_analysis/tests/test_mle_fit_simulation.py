"""Simulation self-test of the Fit23 lifetime engine the burst-MLE wizard uses.

Generates a decay from tttrlib's own forward model (`DecayFit23.modelf`) at a
known lifetime, Poisson-samples it, and fits it back. This pins that the fit
MACHINERY is correct and well-conditioned — so when a real-data fit is poor, it
is the IRF/background quality (the auto-extracted IRF is decay-shaped, hence the
"use a measured IRF" warning), not the fitter. No GUI, no data files.
"""

from __future__ import annotations

import numpy as np
import pytest

import tttrlib


def _simulate(tau_true, n=128, dt=0.05, period=32.0, counts=30000, seed=1):
    rng = np.random.RandomState(seed)
    t = np.arange(n)
    irf_half = np.exp(-0.5 * ((t - 10) / 1.2) ** 2)
    irf_half /= irf_half.sum()
    irf = np.concatenate([irf_half, irf_half])            # clean, narrow IRF
    bg = np.ones(2 * n) / (2 * n)                          # flat background
    corrections = np.array([period, 1.0, 0.0, 0.0, n - 1])
    model = np.zeros(2 * n)
    tttrlib.DecayFit23.modelf(
        np.array([tau_true, 0.0, 0.0, 1.0]), irf, bg, dt, corrections, model
    )
    data = rng.poisson(model / model.sum() * counts).astype(float)
    return data, irf, bg, dt, period


@pytest.mark.parametrize("tau_true", [1.5, 2.0, 3.5, 4.0])
def test_fit23_recovers_known_lifetime(tau_true):
    data, irf, bg, dt, period = _simulate(tau_true)
    fitter = tttrlib.Fit23(
        dt=dt, g_factor=1.0, l1=0.0, l2=0.0, period=period,
        irf=irf, background=bg, soft_bifl_scatter_flag=False,
    )
    res = fitter(
        data=data,
        initial_values=np.array([1.0, 0.0, 0.0, 1.0]),  # deliberately wrong start
        fixed=np.array([0, 1, 1, 1], dtype=np.int16),
    )
    recovered = float(res["x"][0])
    two_istar = float(res["twoIstar"])
    assert recovered == pytest.approx(tau_true, rel=0.05), (
        f"tau {recovered} not within 5% of {tau_true}"
    )
    # A clean IRF/background should give an excellent fit (2I* near 1).
    assert two_istar < 1.5, f"2I* {two_istar} too high for a clean simulation"


def test_fit23_is_well_conditioned_across_starts():
    # The minimiser must converge to the same lifetime from very different starts.
    data, irf, bg, dt, period = _simulate(3.0)
    fitter = tttrlib.Fit23(
        dt=dt, g_factor=1.0, l1=0.0, l2=0.0, period=period,
        irf=irf, background=bg, soft_bifl_scatter_flag=False,
    )
    taus = []
    for start in (0.5, 2.0, 6.0):
        res = fitter(
            data=data,
            initial_values=np.array([start, 0.0, 0.0, 1.0]),
            fixed=np.array([0, 1, 1, 1], dtype=np.int16),
        )
        taus.append(float(res["x"][0]))
    assert max(taus) - min(taus) < 0.1, f"start-dependent fit: {taus}"
