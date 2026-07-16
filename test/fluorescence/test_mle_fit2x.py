"""Tests for the shared tttrlib fit2x maximum-likelihood harness.

See :mod:`chisurf.core.fluorescence.mle.fit2x`.
"""
import utils
import pathlib

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import numpy as np
import pytest

from chisurf.core.fluorescence.mle import (
    Fit2x,
    Fit2xModel,
    Fit2xSettings,
    assemble_vv_vh,
)
from chisurf.core.fluorescence.mle.fit2x import HAVE_TTTRLIB, PARAMETER_NAMES


def test_assemble_vv_vh_stacks_channels():
    p = np.arange(4.0)
    s = np.arange(4.0) + 10.0
    j = assemble_vv_vh(p, s)
    assert j.shape == (8,)
    assert np.allclose(j[:4], p)
    assert np.allclose(j[4:], s)


def test_assemble_vv_vh_length_mismatch_raises():
    with pytest.raises(ValueError):
        assemble_vv_vh(np.zeros(4), np.zeros(5))


def test_settings_validates_irf_and_defaults_background():
    irf = assemble_vv_vh(np.zeros(8), np.zeros(8))
    s = Fit2xSettings(dt=0.032, period=32.0, irf=irf)
    assert s.n_channels == 8
    assert s.background.shape == irf.shape
    assert np.all(s.background == 0.0)
    with pytest.raises(ValueError):  # odd-length (non-VV/VH) IRF
        Fit2xSettings(dt=0.032, period=32.0, irf=np.zeros(7))


def test_parameter_name_tables():
    assert PARAMETER_NAMES[Fit2xModel.FIT23] == ("tau", "gamma", "r0", "rho")
    assert PARAMETER_NAMES[Fit2xModel.FIT24][0] == "tau1"
    assert PARAMETER_NAMES[Fit2xModel.FIT25][-1] == "gamma"


def _simulate_anisotropy_decay(n, dt, tau, rho, r0, n_photons, seed):
    t = np.arange(n) * dt
    intensity = np.exp(-t / tau)
    anis = r0 * np.exp(-t / rho)
    par = intensity * (1.0 + 2.0 * anis)
    per = intensity * (1.0 - anis)
    irf_1 = np.exp(-0.5 * ((np.arange(n) - 5) / 1.0) ** 2)
    par_c = np.convolve(par, irf_1)[:n]
    per_c = np.convolve(per, irf_1)[:n]
    vv_vh = assemble_vv_vh(par_c, per_c)
    vv_vh *= n_photons / vv_vh.sum()
    data = np.random.default_rng(seed).poisson(vv_vh).astype(float)
    irf = assemble_vv_vh(irf_1 / irf_1.sum(), irf_1 / irf_1.sum())
    return data, irf


@pytest.mark.skipif(not HAVE_TTTRLIB, reason="tttrlib not available")
def test_fit23_recovers_lifetime():
    n, dt = 256, 0.032
    data, irf = _simulate_anisotropy_decay(
        n, dt, tau=3.2, rho=1.5, r0=0.38, n_photons=30000, seed=1
    )
    settings = Fit2xSettings(dt=dt, period=32.0, irf=irf, g_factor=1.0)
    fitter = Fit2x(settings, model=Fit2xModel.FIT23)
    assert fitter.n_channels == n
    assert fitter.parameter_names == ("tau", "gamma", "r0", "rho")

    res = fitter.fit(
        data,
        initial_values=[2.0, 0.0, 0.38, 1.0],
        fixed=[0, 1, 1, 0],
        include_model=True,
    )
    # Lifetime recovered within tolerance; goodness-of-fit near 1 per d.o.f.
    assert abs(res.tau - 3.2) < 0.4
    assert res.twoIstar < 5.0
    assert res.model_curve is not None and res.model_curve.shape == (2 * n,)
    d = res.as_dict()
    assert set(d) == {"tau", "gamma", "r0", "rho"}
    assert np.isfinite(res.r_scatter)


@pytest.mark.skipif(not HAVE_TTTRLIB, reason="tttrlib not available")
def test_fitter_is_reusable_across_calls():
    n, dt = 256, 0.032
    data, irf = _simulate_anisotropy_decay(
        n, dt, tau=2.0, rho=1.0, r0=0.38, n_photons=20000, seed=2
    )
    settings = Fit2xSettings(dt=dt, period=32.0, irf=irf)
    fitter = Fit2x(settings, model=Fit2xModel.FIT23)
    r1 = fitter.fit(data, initial_values=[1.5, 0.0, 0.38, 1.0], fixed=[0, 1, 1, 0])
    r2 = fitter.fit(data, initial_values=[3.0, 0.0, 0.38, 1.0], fixed=[0, 1, 1, 0])
    # Same fitter object, consistent estimate regardless of the start value.
    assert abs(r1.tau - r2.tau) < 0.2
