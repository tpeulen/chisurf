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


def test_periodic_convolution_fits_wraparound_decay():
    """A periodic (laser-period) decay is only fit well when the fit is periodic too."""
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    period = N * DT
    t = np.arange(N) * DT
    irf = synthetic_irf(t, center_ns=0.6, fwhm_ns=0.25)
    truth = (60_000.0 * synthetic_decay(N, [1.2], bin_width=DT, irf=irf,
                                        normalize=True, period=period)
             + 40_000.0 * synthetic_decay(N, [4.0], bin_width=DT, irf=irf,
                                           normalize=True, period=period))
    common = dict(bin_width=DT, n_components=2, fit_irf=True, irf_fwhm0=0.2,
                  tau_bounds=(0.2, 8.0), irf_center_bounds=(0.0, 5.0))
    aperiodic = fit_lifetime_components(truth, **common)
    periodic = fit_lifetime_components(truth, period=period, **common)
    assert periodic["chi2_reduced"] < aperiodic["chi2_reduced"]
    assert np.sort(periodic["lifetimes"]) == pytest.approx([1.2, 4.0], rel=0.05)


def test_fits_scatter_and_background_fractions():
    """Including scatter + background in the fit recovers their fractions and
    improves the fit versus lifetimes-only on a decay that carries both."""
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    t = np.arange(N) * DT
    irf = synthetic_irf(t, center_ns=0.8, fwhm_ns=0.3)
    life = synthetic_decay(N, [3.0], bin_width=DT, irf=irf, normalize=True)
    scatter = irf / irf.sum()
    background = np.ones(N) / N
    # 60% lifetime, 25% scatter, 15% flat background.
    truth = 100_000.0 * (0.60 * life + 0.25 * scatter + 0.15 * background)

    bare = fit_lifetime_components(truth, bin_width=DT, n_components=1, fit_irf=True,
                                   irf_fwhm0=0.2, tau_bounds=(0.5, 6.0))
    full = fit_lifetime_components(truth, bin_width=DT, n_components=1, fit_irf=True,
                                   irf_fwhm0=0.2, tau_bounds=(0.5, 6.0),
                                   include_scatter=True, include_background=True)
    # The nuisance-aware fit is at least as good and recovers plausible fractions.
    assert full["chi2_reduced"] <= bare["chi2_reduced"] + 1e-6
    assert full["scatter_fraction"] > 0.1
    assert full["background_fraction"] > 0.05
    assert np.sort(full["lifetimes"])[0] == pytest.approx(3.0, rel=0.25)


def test_fits_irf_width_shift_and_skew_jointly():
    """The joint IRF fit optimizes width, center/shift AND skew — not just width."""
    from chisurf.core.fluorescence.tcspc.irf import synthetic_irf

    t = np.arange(N) * DT
    true_fwhm, true_center, true_skew = 0.30, 0.90, 0.4
    irf = synthetic_irf(t, center_ns=true_center, fwhm_ns=true_fwhm, shape=true_skew)
    truth = (60_000.0 * synthetic_decay(N, [1.2], bin_width=DT, irf=irf, normalize=True)
             + 40_000.0 * synthetic_decay(N, [4.0], bin_width=DT, irf=irf, normalize=True))
    # Start away from the truth in every IRF parameter.
    res = fit_lifetime_components(
        truth, bin_width=DT, n_components=2, fit_irf=True,
        irf_fwhm0=0.2, irf_skew=0.0, tau_bounds=(0.2, 8.0),
        irf_center_bounds=(0.0, 5.0),
    )
    assert res["irf_fwhm"] == pytest.approx(true_fwhm, rel=0.15)
    assert res["irf_center"] == pytest.approx(true_center, abs=0.1)
    assert res["irf_skew"] == pytest.approx(true_skew, abs=0.15)
    assert np.sort(res["lifetimes"]) == pytest.approx([1.2, 4.0], rel=0.1)
