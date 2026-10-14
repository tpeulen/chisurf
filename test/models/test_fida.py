"""Headless tests for the FIDA photon-counting-histogram core.

Cover the generating-function inversion (normalisation, the Poisson limit,
super-Poissonian broadening, brightness/number scaling, species additivity) and
the multinomial residuals.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.stats import poisson

from chisurf.core.models.pch import fida


def _moments(p):
    k = np.arange(p.size)
    mean = float((k * p).sum())
    var = float(((k - mean) ** 2 * p).sum())
    return mean, var


def test_normalised():
    p = fida.fida_pch(40, [(2.0, 3.0)])
    assert abs(p.sum() - 1.0) < 1e-6
    assert np.all(p >= 0)


def test_background_only_is_poisson():
    """No species, only background -> a pure Poisson histogram."""
    lam = 3.5
    p = fida.fida_pch(30, species=[], background=lam)
    ref = poisson.pmf(np.arange(31), lam)
    np.testing.assert_allclose(p, ref, atol=1e-5)


def test_super_poissonian():
    """A bright species broadens the histogram beyond Poisson (var > mean)."""
    p = fida.fida_pch(60, [(3.0, 2.0)])
    mean, var = _moments(p)
    assert var > mean * 1.05  # Mandel Q > 0


def test_mean_scales_with_brightness_and_number():
    """Mean count = N q <x> + bg; doubling N doubles the (bg-free) mean."""
    x, w = fida.dvdx_gaussian()
    x_mean = float((w * x).sum() * (x[1] - x[0]))
    p1 = fida.fida_pch(80, [(2.0, 2.0)])
    p2 = fida.fida_pch(80, [(2.0, 4.0)])
    m1, _ = _moments(p1)
    m2, _ = _moments(p2)
    assert abs(m1 - 2.0 * 2.0 * x_mean) < 0.05
    assert abs(m2 - 2.0 * m1) < 0.05


def test_species_additivity_of_mean():
    """Independent species: mean of the mixture = sum of per-species means."""
    single_a, _ = _moments(fida.fida_pch(80, [(2.0, 1.5)]))
    single_b, _ = _moments(fida.fida_pch(80, [(4.0, 0.5)]))
    both, _ = _moments(fida.fida_pch(80, [(2.0, 1.5), (4.0, 0.5)]))
    assert abs(both - (single_a + single_b)) < 0.05


def test_brighter_species_has_larger_mandel_q():
    """Higher brightness at fixed mean count -> more super-Poissonian."""
    # Match mean count (N*q) so only brightness differs.
    dim, _ = _moments(fida.fida_pch(80, [(1.0, 4.0)]))
    bright, _ = _moments(fida.fida_pch(80, [(4.0, 1.0)]))
    _, var_dim = _moments(fida.fida_pch(80, [(1.0, 4.0)]))
    _, var_bright = _moments(fida.fida_pch(80, [(4.0, 1.0)]))
    q_dim = var_dim / dim - 1.0
    q_bright = var_bright / bright - 1.0
    assert q_bright > q_dim


def test_fit_fida_recovers_brightness_and_number():
    """FPCHFidaFit-style fit recovers the (q, N) that generated the histogram."""
    q_true, n_true = 3.0, 2.0
    p = fida.fida_pch(60, [(q_true, n_true)])
    counts = 500_000 * p  # noise-free "measurement"
    res = fida.fit_fida(counts, species_guess=[(1.5, 1.0)])
    q_fit, n_fit = res["species"][0]
    assert abs(q_fit - q_true) < 0.15
    assert abs(n_fit - n_true) < 0.15
    assert res["chi2r"] < 1e-3  # exact model -> ~0 residuals


def test_residuals_zero_at_truth():
    p = fida.fida_pch(40, [(2.5, 2.0)])
    counts = 10_000 * p  # "data" == model exactly
    r = fida.fida_residuals(p, counts, n_bins=10_000)
    # Residuals vanish where the model has appreciable probability (empty tail
    # bins carry a negligible ~1/sqrt(n) offset from the p-floor and are ignored).
    assert np.max(np.abs(r[p > 1e-4])) < 1e-3


# -- profile and oversample take effect -----------------------------------------------------


def test_fida_profile_sets_the_mean_count():
    """<k> = sum_i N_i q_i \\int x w(x) dx + bg, so the profile changes the mean as theory says."""
    from chisurf.core.models.pch.fida import dvdx_gaussian, fida_pch

    q, n, k_max = 2.0, 0.5, 60
    x = np.linspace(0.9, 1.0, 64)
    narrow = (x, np.full_like(x, 1.0 / (x.size * (x[1] - x[0]))))
    k = np.arange(k_max + 1)
    for profile in (dvdx_gaussian(), narrow):
        px, pw = profile
        expected = n * q * float(np.sum(px * pw) * (px[1] - px[0]))
        p = fida_pch(k_max, [(q, n)], profile=profile)
        assert float(np.sum(k * p)) == pytest.approx(expected, rel=1e-6)
    # And the two profiles really give different histograms.
    assert not np.allclose(fida_pch(k_max, [(q, n)], profile=narrow), fida_pch(k_max, [(q, n)]))


def test_fida_oversample_controls_tail_aliasing():
    """Background only: P(k) is Poisson(bg). A short FFT folds the tail beyond k_max back onto
    low k (circular aliasing); oversampling removes it."""
    from math import factorial

    from chisurf.core.models.pch.fida import fida_pch

    bg, k_max = 6.0, 8
    exact = np.array([np.exp(-bg) * bg**k / factorial(k) for k in range(k_max + 1)])
    exact /= exact.sum()
    aliased = fida_pch(k_max, [(1.0, 0.0)], background=bg, oversample=1)
    converged = fida_pch(k_max, [(1.0, 0.0)], background=bg, oversample=16)
    assert np.max(np.abs(converged - exact)) < 1e-9
    assert np.max(np.abs(aliased - exact)) > 1e-3
