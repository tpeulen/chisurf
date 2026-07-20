"""Tests for the general decay-mixture fitter."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.decay import synthetic_decay
from chisurf.core.fluorescence.decay_fit import (
    fit_component_amplitudes,
    fit_lifetime_components,
)

DT = 0.032
N = 512


def test_recovers_two_lifetimes():
    # A known 60/40 bi-exponential (1.2 ns / 4.0 ns).
    truth = (
        0.6 * synthetic_decay(N, [1.2], bin_width=DT, normalize=True)
        + 0.4 * synthetic_decay(N, [4.0], bin_width=DT, normalize=True)
    )
    res = fit_lifetime_components(truth, bin_width=DT, n_components=2, tau_bounds=(0.2, 8.0))
    taus = np.sort(res["lifetimes"])
    assert taus[0] == pytest.approx(1.2, rel=0.08)
    assert taus[1] == pytest.approx(4.0, rel=0.08)
    # amplitude ratio recovered (amplitudes are lifetime-sorted)
    amps = res["amplitudes"] / res["amplitudes"].sum()
    assert amps[0] == pytest.approx(0.6, abs=0.05)
    assert res["chi2_reduced"] < 1e-6           # noiseless → near-perfect fit


def test_reconstruction_matches_target():
    truth = synthetic_decay(N, [2.5], bin_width=DT, normalize=True)
    res = fit_lifetime_components(truth, bin_width=DT, n_components=1, tau_bounds=(0.5, 6.0))
    assert np.allclose(res["reconstruction"], truth, atol=1e-4)
    assert res["lifetime_spectrum"].size == 2   # [amp, tau]


def test_with_irf():
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    t = np.arange(N) * DT
    irf = synthetic_irf(t, center_ns=0.5, fwhm_ns=0.3)
    truth = synthetic_decay(N, [3.0], bin_width=DT, irf=irf, normalize=True)
    res = fit_lifetime_components(truth, bin_width=DT, n_components=1, irf=irf,
                                  tau_bounds=(0.5, 6.0))
    assert np.sort(res["lifetimes"])[0] == pytest.approx(3.0, rel=0.05)


def test_poisson_noise_is_robust():
    truth = 100_000.0 * (
        0.7 * synthetic_decay(N, [1.0], bin_width=DT, normalize=True)
        + 0.3 * synthetic_decay(N, [4.5], bin_width=DT, normalize=True)
    )
    rng = np.random.default_rng(1)
    noisy = rng.poisson(np.maximum(truth, 0)).astype(float)
    res = fit_lifetime_components(noisy, bin_width=DT, n_components=2, tau_bounds=(0.2, 8.0))
    taus = np.sort(res["lifetimes"])
    assert taus[0] == pytest.approx(1.0, rel=0.15)
    assert taus[1] == pytest.approx(4.5, rel=0.15)


def test_fit_component_amplitudes_linear_unmix():
    fast = synthetic_decay(N, [1.0], bin_width=DT, normalize=True)
    slow = synthetic_decay(N, [4.0], bin_width=DT, normalize=True)
    target = 0.75 * fast + 0.25 * slow
    res = fit_component_amplitudes(target, [fast, slow])
    frac = res["amplitudes"] / res["amplitudes"].sum()
    assert frac[0] == pytest.approx(0.75, abs=1e-3)
    assert res["amplitudes"].min() >= 0.0       # non-negative


def test_fits_irf_fwhm():
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    t = np.arange(N) * DT
    true_fwhm = 0.4
    irf = synthetic_irf(t, center_ns=0.8, fwhm_ns=true_fwhm)
    truth = 100_000.0 * synthetic_decay(N, [2.5], bin_width=DT, irf=irf, normalize=True)
    # Fit lifetimes AND the (unknown) IRF width jointly.
    res = fit_lifetime_components(truth, bin_width=DT, n_components=1,
                                  fit_irf=True, irf_fwhm0=0.2, tau_bounds=(0.5, 6.0))
    assert res["irf_fwhm"] == pytest.approx(true_fwhm, rel=0.2)
    assert np.sort(res["lifetimes"])[0] == pytest.approx(2.5, rel=0.1)
