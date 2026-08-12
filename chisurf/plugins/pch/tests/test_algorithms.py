import numpy as np

from chisurf.plugins.pch.api.algorithms import (
    compute_p1,
    convolve_pch,
    pch_mixture,
    pch_open_system,
    pch_single_species,
)


def test_compute_p1_basic():
    k_vals = np.arange(60, dtype=float)
    brightness = 5.0
    x_vals = np.linspace(0, 5, 500)
    dx = x_vals[1] - x_vals[0]
    p1 = compute_p1(k_vals, brightness, x_vals, dx)
    assert len(p1) == 60
    assert np.isclose(p1.sum(), 1.0, atol=1e-6)
    assert p1[0] <= 1


def test_pch_single_species():
    k_vals = np.arange(60, dtype=float)
    p = pch_single_species(k_vals, 3.0)
    assert len(p) == 60
    assert np.isclose(p.sum(), 1.0, atol=1e-6)


def test_convolve_pch():
    p1 = np.array([0.5, 0.3, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=float)
    result = convolve_pch(p1, 2, 10)
    assert len(result) == 10
    assert np.isclose(result.sum(), 1.0, atol=1e-6)


def test_convolve_n0():
    p1 = np.array([0.5, 0.3, 0.2, 0.0, 0.0], dtype=float)
    result = convolve_pch(p1, 0, 5)
    assert result[0] == 1.0
    assert result[1:].sum() == 0.0


def test_pch_open_system():
    k_vals = np.arange(60, dtype=float)
    p = pch_open_system(k_vals, 5.0, 2.0)
    assert len(p) == 60
    assert np.isclose(p.sum(), 1.0, atol=5e-3)


def test_pch_mixture():
    k_vals = np.arange(60, dtype=float)
    p = pch_mixture(k_vals, [3.0, 8.0], [2.0, 1.0])
    assert len(p) == 60
    assert np.isclose(p.sum(), 1.0, atol=5e-3)


def test_the_detection_volume_is_the_three_dimensional_gaussian():
    # Var/<k> - 1 == eps * gamma_2 for a compound-Poisson PCH, and gamma_2 is a
    # pure shape factor of the detection volume: 2**-1.5 for the 3-D Gaussian
    # that docs/concepts/pch_fida.md documents, 2**-0.5 if the radial volume
    # element x**2 is dropped and the integral degenerates to a 1-D Gaussian.
    # The identity is free of the eps/N normalisation convention, so it pins the
    # profile and nothing else.
    k_vals = np.arange(200, dtype=float)
    for brightness in (0.5, 1.0, 2.0):
        for avg_n in (0.5, 1.0):
            p = pch_open_system(k_vals, brightness, avg_n)
            mean = float((k_vals * p).sum())
            var = float((k_vals**2 * p).sum()) - mean**2
            gamma_2 = (var / mean - 1.0) / brightness
            assert np.isclose(gamma_2, 2.0**-1.5, rtol=1e-6)


def test_p1_stays_finite_and_non_zero_on_a_long_photon_count_axis():
    # lam**k / k! overflowed a double on both ends: k! passes DBL_MAX at k = 171,
    # so p1[k] was exactly 0 from there on at any brightness, and further out the
    # numerator overflowed too and inf/inf gave NaN, which p1[0] = 1 - p1[1:].sum()
    # then smeared over the whole array and handed to the optimiser.  A 300-long
    # k axis is ordinary at 1 ms binning.
    p1 = pch_single_species(np.arange(400, dtype=float), 100.0)
    assert np.isfinite(p1).all()
    assert p1[200] > 0.0
    assert (pch_single_species(np.arange(300, dtype=float), 10.0)[171:] > 0.0).any()


def test_the_log_space_poisson_term_reproduces_the_plain_ratio():
    # Below the overflow the closed form lam**k / k! * exp(-lam) is exact, so it
    # pins the log-space evaluation against an arithmetic slip.
    x_vals = np.linspace(0, 5, 500)
    dx = x_vals[1] - x_vals[0]
    k_vals = np.arange(150, dtype=float)
    brightness = 4.0
    p1 = compute_p1(k_vals, brightness, x_vals, dx)
    lam = brightness * np.exp(-2.0 * x_vals**2)
    for k in (1, 5, 20, 60, 149):
        fact = 1.0
        for j in range(1, k + 1):
            fact *= j
        ref = float((x_vals**2 * lam**k / fact * np.exp(-lam)).sum()) * dx
        assert np.isclose(p1[k], ref, rtol=1e-9, atol=0.0), k


def test_the_fitted_model_is_finite_where_the_optimiser_can_walk():
    # eps is bounded only from below in _fit_handler, so the optimiser reaches
    # large brightness on its own; a NaN there aborts the fit with "Residuals are
    # not finite in the initial point".
    k_vals = np.arange(300, dtype=float)
    for brightness in (5.0, 40.0, 100.0):
        assert np.isfinite(pch_mixture(k_vals, [brightness], [2.0])).all(), brightness


def test_brightness_matches_the_independent_three_dimensional_gaussian_route():
    # The FIDA generating function in chisurf.core.models.pch is a second, fully
    # independent 3DG implementation. Fitting a histogram it generates must give
    # back its brightness; before the volume element was restored this route
    # recovered ~0.3-0.4x the truth and could not reproduce the shape at all.
    from chisurf.core.models.pch.fida import fida_pch
    from chisurf.plugins.pch.backend.services import _fit_handler

    k_max = 60
    n_bins = 5_000_000
    k_vals = np.arange(k_max + 1, dtype=float)
    for q in (2.0, 5.0):
        p_true = fida_pch(k_max, [(q, 1.0)])
        result = _fit_handler(
            k_vals=k_vals.tolist(),
            p_exp=p_true.tolist(),
            hist_counts=np.round(p_true * n_bins).astype(int).tolist(),
            total_bins=n_bins,
            n_components=1,
            initial_epsilons=[1.0],
            initial_Ns=[1.0],
            fit_low=0,
            fit_high=k_max,
        )
        assert result["ok"] is True
        assert np.isclose(result["result"]["epsilons"][0], q, rtol=0.05)
