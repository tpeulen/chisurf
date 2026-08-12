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
from chisurf.core.fluorescence.mle.fit2x import HAVE_TTTRLIB, parameter_names_of


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


# The detector-setup parser is shared by every MLE consumer, not just the
# deprecated fit2x harness; its tests live in test_mle_setup.py.

def test_settings_area_normalises_the_background():
    # gamma is the background *fraction*, so the model needs a unit-area
    # background. A raw photon histogram (sum >> 1) otherwise makes gamma an
    # enormous multiplier and a free-gamma fit diverges to gamma≈1. The facade
    # normalises so every consumer (burst batch + imaging pixel/molecule fits)
    # is protected in one place.
    irf = assemble_vv_vh(np.zeros(8), np.zeros(8))
    raw_bg = assemble_vv_vh(np.arange(1.0, 9.0), np.arange(1.0, 9.0))  # sums to 72
    s = Fit2xSettings(dt=0.032, period=32.0, irf=irf, background=raw_bg)
    assert s.background.sum() == pytest.approx(1.0)
    # shape preserved, relative pattern preserved
    np.testing.assert_allclose(s.background, raw_bg / raw_bg.sum())
    # an already-normalised background is left effectively unchanged
    s2 = Fit2xSettings(dt=0.032, period=32.0, irf=irf, background=raw_bg / raw_bg.sum())
    assert s2.background.sum() == pytest.approx(1.0)


def test_parameter_name_tables():
    assert parameter_names_of(Fit2xModel.FIT23) == ("tau", "gamma", "r0", "rho")
    assert parameter_names_of(Fit2xModel.FIT24)[0] == "tau1"
    assert parameter_names_of(Fit2xModel.FIT25)[-1] == "gamma"


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
def test_fit_many_is_general_and_matches_scalar_fits():
    # fit_many now has a native batch kernel for fit23/24/25 (was fit23-only).
    # The batch result must match fitting each row on its own.
    n, dt = 128, 0.032
    data, irf = _simulate_anisotropy_decay(
        n, dt, tau=3.0, rho=1.2, r0=0.38, n_photons=25000, seed=7
    )
    rows = np.vstack([data, data, data])  # 3 identical rows → identical fits
    settings = Fit2xSettings(dt=dt, period=32.0, irf=irf, g_factor=1.0)

    # fit23: shape (n_rows, 4 params + 2I*)
    f23 = Fit2x(settings, model=Fit2xModel.FIT23)
    b23 = f23.fit_many(rows, [2.0, 0.0, 0.38, 1.0], fixed=[0, 1, 1, 0])
    assert b23.shape == (3, 5)
    scalar = f23.fit(data, initial_values=[2.0, 0.0, 0.38, 1.0], fixed=[0, 1, 1, 0])
    assert b23[0, 0] == pytest.approx(scalar.tau, rel=1e-6)
    assert np.allclose(b23[0], b23[1]) and np.allclose(b23[0], b23[2])

    # fit24: previously raised NotImplementedError; now runs the native batch
    # kernel and returns 5 params + 2I*. (Convergence quality depends on the
    # data being bi-exponential; here we only pin that the batch path works and
    # is row-consistent — parity with the scalar fit is covered in tttrlib.)
    f24 = Fit2x(settings, model=Fit2xModel.FIT24)
    b24 = f24.fit_many(rows, [1.0, 0.0, 3.0, 0.5, 0.0], fixed=[0, 1, 0, 0, 1])
    assert b24.shape == (3, 6)
    assert np.allclose(b24[0], b24[1], equal_nan=True)
    assert np.allclose(b24[0], b24[2], equal_nan=True)


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
