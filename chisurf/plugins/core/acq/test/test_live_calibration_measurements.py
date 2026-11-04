"""Calibration measurement maths on synthetic data with known truth.

Every estimator here is documented with its formula and its assumptions: the IRF
full width at half maximum, a log-linear tail-fit lifetime, the buffer background
rate, the polarisation factor G from a fast-rotating reference, the PIE gamma
from a single doubly-labelled sample (Müller et al. 2005, DOI
10.1529/biophysj.105.064766; nomenclature of the correction factors alpha, delta,
beta, gamma follows Hellenkamp et al. 2018, DOI 10.1038/s41592-018-0085-0) and
the multi-point power-diode fit. No accept/reject thresholds live here.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.core.acq.live.calibration import measurements as m


# -- the water IRF ------------------------------------------------------------------------------

def _gaussian_hist(sigma_ns, bin_ns, n_bins=2000, peak=10000.0, mu_ns=20.0):
    t = (np.arange(n_bins) + 0.5) * bin_ns
    return peak * np.exp(-0.5 * ((t - mu_ns) / sigma_ns) ** 2)


def test_irf_fwhm_recovers_a_gaussian_width():
    bin_ns, sigma_ns = 0.02, 0.15
    value, detail = m.irf_fwhm_ns(_gaussian_hist(sigma_ns, bin_ns), bin_ns)
    assert value == pytest.approx(2.3548 * sigma_ns, rel=0.02)
    assert "ns" in detail


def test_irf_fwhm_scales_with_the_micro_time_resolution():
    hist = _gaussian_hist(0.15, 0.02)
    fine, _ = m.irf_fwhm_ns(hist, 0.02)
    coarse, _ = m.irf_fwhm_ns(hist, 0.04)
    assert coarse == pytest.approx(2 * fine, rel=1e-6)


def test_irf_fwhm_refuses_an_empty_histogram_or_a_peak_at_the_edge():
    value, detail = m.irf_fwhm_ns(np.zeros(100), 0.02)
    assert value is None and detail
    value, detail = m.irf_fwhm_ns(np.array([0.0, 0.0, 10.0]), 0.02)
    assert value is None and "edge" in detail.lower()
    value, detail = m.irf_fwhm_ns(np.array([10.0, 0.0, 0.0]), 0.02)
    assert value is None and "edge" in detail.lower()


# -- the tail-fit lifetime ----------------------------------------------------------------------

def test_tail_lifetime_recovers_a_noise_free_single_exponential():
    bin_ns, tau_ns = 0.02, 3.0
    t = (np.arange(3000) + 0.5) * bin_ns
    hist = 20000.0 * np.exp(-t / tau_ns)
    value, detail = m.tail_lifetime_ns(hist, bin_ns, start_ns=10.0, stop_ns=100.0)
    assert value == pytest.approx(tau_ns, rel=1e-6)
    assert "tail" in detail.lower() or "log" in detail.lower()


def test_tail_lifetime_stays_close_to_truth_on_counting_noise():
    bin_ns, tau_ns = 0.02, 3.0
    t = (np.arange(3000) + 0.5) * bin_ns
    rng = np.random.default_rng(11)
    hist = rng.poisson(20000.0 * np.exp(-t / tau_ns)).astype(float)
    value, _detail = m.tail_lifetime_ns(hist, bin_ns, start_ns=10.0, stop_ns=100.0)
    assert value == pytest.approx(tau_ns, rel=0.05)


def test_tail_lifetime_refuses_a_window_without_enough_counts():
    bin_ns = 0.02
    hist = np.zeros(1000)
    value, detail = m.tail_lifetime_ns(hist, bin_ns, start_ns=1.0, stop_ns=10.0)
    assert value is None and detail


def test_tail_lifetime_refuses_an_empty_or_inverted_window():
    hist = np.ones(1000)
    assert m.tail_lifetime_ns(hist, 0.02, start_ns=10.0, stop_ns=10.0)[0] is None
    assert m.tail_lifetime_ns(hist, 0.02, start_ns=20.0, stop_ns=10.0)[0] is None


# -- the buffer background ------------------------------------------------------------------------

def test_background_rate_khz_is_photons_over_time():
    value, _ = m.background_rate_khz(photons=60000, acquisition_time_s=60.0)
    assert value == pytest.approx(1.0)


def test_background_rate_refuses_nonpositive_time():
    value, detail = m.background_rate_khz(photons=100, acquisition_time_s=0.0)
    assert value is None and detail


# -- the polarisation factor ---------------------------------------------------------------------

def test_g_factor_of_a_fast_rotating_reference_is_the_intensity_ratio():
    value, _ = m.g_factor(i_par=1800.0, i_perp=1000.0, r_assumed=0.0)
    assert value == pytest.approx(1.8)


def test_g_factor_inverts_the_anisotropy_model_at_nonzero_anisotropy():
    # intensities of a sample with true G = 1.8 and true anisotropy r = 0.1, from
    # r = (I_par - G I_perp) / (I_par + 2 G I_perp) with I_perp = 1000:
    value, _ = m.g_factor(i_par=2400.0, i_perp=1000.0, r_assumed=0.1)
    assert value == pytest.approx(1.8)


def test_g_factor_refuses_nonpositive_perpendicular_counts():
    value, detail = m.g_factor(i_par=100.0, i_perp=0.0, r_assumed=0.0)
    assert value is None and detail


@pytest.mark.parametrize("parallel, perpendicular, anisotropy", [
    (-1, 1, 0), (0, 1, 0), (1, -1, 0), (1, 1, -0.5),
    (1, 1, -0.6), (1, 1, 1), (1, 1, float('nan')),
    (1e308, 1e-308, 0),
])
def test_g_factor_rejects_invalid_reference_inputs(parallel, perpendicular, anisotropy):
    value, detail = m.g_factor(i_par=parallel, i_perp=perpendicular, r_assumed=anisotropy)
    assert value is None and detail


def test_apparent_anisotropy_reports_the_uncorrected_value():
    value, _ = m.apparent_anisotropy(i_par=2400.0, i_perp=1000.0)
    assert value == pytest.approx((2400.0 - 1000.0) / (2400.0 + 2 * 1000.0))


# -- PIE gamma from one doubly-labelled sample ----------------------------------------------------

def _pie_forward(e, gamma, beta, alpha, delta, f_aa=10000.0):
    """Truth-to-raw forward model of the three PIE streams of one 1:1 molecule.

    F_AD = E F_AA (sensitized emission scales with the acceptor brightness that
    F_AA measures directly), F_DD = F_AA (1 - E) / gamma, and the raw acceptor
    channel under donor excitation additionally carries donor leakage (alpha) and
    direct acceptor excitation by the donor laser (delta); the raw acceptor
    channel under acceptor excitation is beta * F_AA (excitation normalisation).
    """
    f_dd = f_aa * (1.0 - e) / gamma
    f_ad = f_aa * e
    i_ad_raw = f_ad + alpha * f_dd + delta * (beta * f_aa)
    return f_dd, i_ad_raw, beta * f_aa


def test_pie_gamma_recovers_the_truth_of_the_forward_model():
    e_true, gamma_true, beta, alpha, delta = 0.5, 0.8, 1.25, 0.03, 0.05
    i_dd, i_ad_raw, i_aa = _pie_forward(e_true, gamma_true, beta, alpha, delta)
    out, detail = m.pie_gamma(
        i_dd=i_dd, i_ad_raw=i_ad_raw, i_aa=i_aa, alpha=alpha, delta=delta, beta=beta
    )
    assert out is not None
    assert out["fret_efficiency"] == pytest.approx(e_true, rel=1e-9)
    assert out["gamma"] == pytest.approx(gamma_true, rel=1e-9)
    assert out["f_ad"] == pytest.approx(i_aa / beta * e_true, rel=1e-9)
    assert out["f_aa_corrected"] == pytest.approx(i_aa / beta, rel=1e-9)
    assert detail


def test_pie_gamma_second_truth_point():
    e_true, gamma_true, beta, alpha, delta = 0.25, 1.1, 0.9, 0.02, 0.07
    i_dd, i_ad_raw, i_aa = _pie_forward(e_true, gamma_true, beta, alpha, delta)
    out, _ = m.pie_gamma(
        i_dd=i_dd, i_ad_raw=i_ad_raw, i_aa=i_aa, alpha=alpha, delta=delta, beta=beta
    )
    assert out["fret_efficiency"] == pytest.approx(e_true, rel=1e-9)
    assert out["gamma"] == pytest.approx(gamma_true, rel=1e-9)


def test_pie_gamma_names_the_missing_or_degenerate_input():
    i_dd, i_ad_raw, i_aa = _pie_forward(0.5, 0.8, 1.25, 0.03, 0.05)
    for kwargs, needle in [
        (dict(i_ad_raw=i_ad_raw, i_aa=i_aa, alpha=0.03, delta=0.05, beta=1.25), "i_dd"),
        (dict(i_dd=i_dd, i_ad_raw=i_ad_raw, i_aa=i_aa, delta=0.05, beta=1.25), "alpha"),
        (dict(i_dd=i_dd, i_ad_raw=i_ad_raw, i_aa=i_aa, alpha=0.03, beta=1.25), "delta"),
        (dict(i_dd=i_dd, i_ad_raw=i_ad_raw, i_aa=i_aa, alpha=0.03, delta=0.05), "beta"),
        (dict(i_dd=i_dd, i_ad_raw=i_ad_raw, i_aa=i_aa, alpha=0.03, delta=0.05, beta=0.0), "beta"),
        (dict(i_dd=0.0, i_ad_raw=i_ad_raw, i_aa=i_aa, alpha=0.03, delta=0.05, beta=1.25), "i_dd"),
        (dict(i_dd=i_dd, i_ad_raw=i_ad_raw, i_aa=0.0, alpha=0.03, delta=0.05, beta=1.25), "i_aa"),
    ]:
        out, detail = m.pie_gamma(**kwargs)
        assert out is None
        assert needle in detail, detail


# The power-diode fit/interpolation/expiry is owned and tested by
# chisurf.plugins.core.acq.live.power_calibration (see its own tests and
# test_live_calibration_lasers.py for the delegation); no duplicate here.
