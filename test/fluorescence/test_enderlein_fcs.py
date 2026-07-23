"""Headless tests for the Enderlein Gauss--Lorentz MDF FCS core.

Cover the molecule-detection function, the effective volume, and the diffusion
autocorrelation shape/normalisation and physical scaling.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.fcs import enderlein as en


def test_mdf_peaks_at_origin_and_decays():
    optics = en.Optics()
    z = np.linspace(-2.0, 2.0, 51)
    on_axis = en.mdf(np.zeros_like(z), z, w0=0.25, R0=0.25, optics=optics)
    assert np.argmax(on_axis) == len(z) // 2          # brightest at focus
    # Lateral Gaussian: intensity drops off-axis.
    center = en.mdf(0.0, 0.0, 0.25, 0.25, optics)
    off = en.mdf(0.5, 0.0, 0.25, 0.25, optics)
    assert off < center


def test_effective_volume_positive_and_scales():
    v_small = en.effective_volume(0.2, 0.2)
    v_large = en.effective_volume(0.4, 0.4)
    assert v_small > 0 and v_large > 0
    assert v_large > v_small                          # wider spot -> larger volume


def test_gdiff_normalised_starts_at_one_and_decays():
    tau = np.logspace(-6, 0, 40)   # 1 µs .. 1 s
    g = en.g_diff(tau, w0=0.25, R0=0.25, diffusion=300.0, normalize=True)
    assert abs(g[0] - 1.0) < 0.05                      # g(0+) ~ 1
    assert np.all(np.diff(g) <= 1e-9)                  # monotonically decreasing
    assert g[-1] < 0.1                                 # decorrelated at long lag


def test_gdiff_faster_diffusion_shorter_decay():
    tau = np.logspace(-6, 0, 60)
    g_slow = en.g_diff(tau, 0.25, 0.25, diffusion=50.0)
    g_fast = en.g_diff(tau, 0.25, 0.25, diffusion=500.0)
    half_slow = tau[np.argmin(np.abs(g_slow - 0.5))]
    half_fast = tau[np.argmin(np.abs(g_fast - 0.5))]
    assert half_fast < half_slow                       # faster D -> shorter tauD


def test_acf_amplitude_is_one_over_n_plus_offset():
    tau = np.logspace(-6, 0, 30)
    N, offset = 4.0, 0.7
    g = en.acf(tau, n_molecules=N, diffusion=300.0, w0=0.25, R0=0.25, offset=offset)
    assert abs((g[0] - offset) - 1.0 / N) < 0.05       # G(0) = offset + 1/N


def test_two_focus_cross_correlation():
    """A finite inter-focus separation suppresses G(0) and shifts the peak to
    a finite lag (the two-focus cross-correlation signature)."""
    tau = np.logspace(-6, 0, 80)
    auto = en.g_diff(tau, 0.25, 0.25, diffusion=300.0, separation=0.0)
    cross = en.g_diff(tau, 0.25, 0.25, diffusion=300.0, separation=0.5)  # 0.5 µm apart
    assert cross[0] < 0.5                      # cross-corr is suppressed at tau->0
    assert np.argmax(cross) > 0                # and peaks at a finite lag
    # Larger separation suppresses the short-lag amplitude further.
    cross_far = en.g_diff(tau, 0.25, 0.25, diffusion=300.0, separation=0.8)
    assert cross_far[0] < cross[0]


def test_g0_matches_inverse_n_veff():
    """Unnormalised g_diff(0) equals 1/V_eff (absolute-concentration relation)."""
    w0 = R0 = 0.25
    veff = en.effective_volume(w0, R0)
    g0 = en.g_diff(np.array([0.0]), w0, R0, diffusion=300.0, normalize=False)[0]
    np.testing.assert_allclose(g0, 1.0 / veff, rtol=1e-3)
