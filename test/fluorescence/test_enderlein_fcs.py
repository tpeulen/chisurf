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
    assert np.argmax(on_axis) == len(z) // 2  # brightest at focus
    # Lateral Gaussian: intensity drops off-axis.
    center = en.mdf(0.0, 0.0, 0.25, 0.25, optics)
    off = en.mdf(0.5, 0.0, 0.25, 0.25, optics)
    assert off < center


def test_effective_volume_positive_and_scales():
    v_small = en.effective_volume(0.2, 0.2)
    v_large = en.effective_volume(0.4, 0.4)
    assert v_small > 0 and v_large > 0
    assert v_large > v_small  # wider spot -> larger volume


def test_gdiff_normalised_starts_at_one_and_decays():
    tau = np.logspace(-6, 0, 40)  # 1 µs .. 1 s
    g = en.g_diff(tau, w0=0.25, R0=0.25, diffusion=300.0, normalize=True)
    assert abs(g[0] - 1.0) < 0.05  # g(0+) ~ 1
    assert np.all(np.diff(g) <= 1e-9)  # monotonically decreasing
    assert g[-1] < 0.1  # decorrelated at long lag


def test_gdiff_faster_diffusion_shorter_decay():
    tau = np.logspace(-6, 0, 60)
    g_slow = en.g_diff(tau, 0.25, 0.25, diffusion=50.0)
    g_fast = en.g_diff(tau, 0.25, 0.25, diffusion=500.0)
    half_slow = tau[np.argmin(np.abs(g_slow - 0.5))]
    half_fast = tau[np.argmin(np.abs(g_fast - 0.5))]
    assert half_fast < half_slow  # faster D -> shorter tauD


def test_acf_amplitude_is_one_over_n_plus_offset():
    tau = np.logspace(-6, 0, 30)
    N, offset = 4.0, 0.7
    g = en.acf(tau, n_molecules=N, diffusion=300.0, w0=0.25, R0=0.25, offset=offset)
    assert abs((g[0] - offset) - 1.0 / N) < 0.05  # G(0) = offset + 1/N


def test_two_focus_cross_correlation():
    """A finite inter-focus separation suppresses G(0) and shifts the peak to
    a finite lag (the two-focus cross-correlation signature).
    """
    tau = np.logspace(-6, 0, 80)
    en.g_diff(tau, 0.25, 0.25, diffusion=300.0, separation=0.0)
    cross = en.g_diff(tau, 0.25, 0.25, diffusion=300.0, separation=0.5)  # 0.5 µm apart
    assert cross[0] < 0.5  # cross-corr is suppressed at tau->0
    assert np.argmax(cross) > 0  # and peaks at a finite lag
    # Larger separation suppresses the short-lag amplitude further.
    cross_far = en.g_diff(tau, 0.25, 0.25, diffusion=300.0, separation=0.8)
    assert cross_far[0] < cross[0]


def test_g0_matches_inverse_n_veff():
    """Unnormalised g_diff(0) equals 1/V_eff (absolute-concentration relation)."""
    w0 = R0 = 0.25
    veff = en.effective_volume(w0, R0)
    g0 = en.g_diff(np.array([0.0]), w0, R0, diffusion=300.0, normalize=False)[0]
    np.testing.assert_allclose(g0, 1.0 / veff, rtol=1e-3)


def test_the_engine_matches_an_independent_numpy_transcription():
    """The math of the deleted numpy body, pinned against the engine.

    ``g_diff``/``effective_volume`` forward to ``IMP.bff`` since 2026-09-02
    (board T-20260902-11; forward models live in bff). This transcription is
    the reference the engine must keep agreeing with -- the same role the
    Coates transcription plays for tttrlib's pile-up kernel.
    """
    optics = en.Optics()
    a = optics.pinhole_radius
    w0, R0, D = 0.25, 0.30, 400.0
    n_grid, span, n_herm = 121, 30.0, 40
    tau = np.logspace(-6, -1, 21)

    z_r = (
        np.pi
        * max(w0 * w0, R0 * R0)
        * optics.refractive_index
        / min(optics.excitation_wavelength, optics.emission_wavelength)
    )
    z = np.linspace(-span * z_r, span * z_r, n_grid)

    def w_of(zz):
        q = optics.excitation_wavelength * zz / (np.pi * w0 * w0 * optics.refractive_index)
        return w0 * np.sqrt(1.0 + q * q)

    def kappa_of(zz):
        q = optics.emission_wavelength * zz / (np.pi * R0 * R0 * optics.refractive_index)
        R2 = R0 * R0 * (1.0 + q * q)
        return 1.0 - np.exp(-2.0 * a * a / R2)

    kappa = kappa_of(z)
    w2 = w_of(z) ** 2
    xi, hq = np.polynomial.hermite.hermgauss(n_herm)

    def raw(t, sep2=0.0):
        t = max(t, 1e-18)
        s = 4.0 * D * t
        zp = z[:, None] + np.sqrt(s) * xi[None, :]
        w_sum = w2[:, None] + w_of(zp) ** 2
        g_lat = 1.0 / (4.0 + w_sum / (2.0 * D * t))
        if sep2 > 0.0:
            g_lat = g_lat * np.exp(-sep2 / (4.0 * D * t + 0.5 * w_sum))
        inner = np.sum(hq[None, :] * kappa_of(zp) * g_lat, axis=1)
        return float(np.trapezoid(kappa * inner, z) / s)

    num0 = raw(1e-15)
    want = np.array([raw(t) for t in tau]) / num0
    got = en.g_diff(
        tau, w0, R0, D, optics=optics, n_grid=n_grid, span=span, n_herm=n_herm, normalize=True
    )
    np.testing.assert_allclose(got, want, rtol=1e-12)

    # Two-focus cross-correlation starts below one and keeps the same shape
    # contract; the effective volume follows the Fretica formula.
    got2 = en.g_diff(
        tau,
        w0,
        R0,
        D,
        optics=optics,
        n_grid=n_grid,
        span=span,
        n_herm=n_herm,
        normalize=True,
        separation=0.4,
    )
    want2 = np.array([raw(t, 0.16) for t in tau]) / num0
    np.testing.assert_allclose(got2, want2, rtol=1e-12)

    zf = np.linspace(-60.0 * z_r, 60.0 * z_r, 4001)
    kf, wf2 = kappa_of(zf), w_of(zf) ** 2
    veff = np.pi * np.trapezoid(kf, zf) ** 2 / np.trapezoid(kf * kf / wf2, zf)
    assert en.effective_volume(w0, R0, optics) == pytest.approx(veff, rel=1e-12)
