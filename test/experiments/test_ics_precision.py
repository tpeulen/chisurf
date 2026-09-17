"""Predicting how precisely a raster scan can measure D (RICSPE port).

The tool answers a question you want answered *before* the microscope time is
spent: at this scan speed, with this sample, how well will D come out? These
tests check the machinery, and then the two physics claims that make it worth
having — precision improves as 1/sqrt(frames), and there is an optimal dwell
time that moves with the diffusion coefficient.

Parameters are kept small so the suite stays fast; the covariance is O(n_lags^4)
with an inner sum over the image.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from chisurf.core.experiments.ics.precision import (
    RicsPrecision,
    UnrealisableScan,
    _pair_counts,
    correlation_covariance,
    correlation_grid,
    gamma_factors,
    nearest_spd,
    rics_precision,
    triple_correlation,
)

#: A small but not degenerate acquisition, used by most tests.
FAST = dict(
    pixel_size=0.05,
    nx=32,
    ny=32,
    n_lags=3,
    n_repeats=25,
    n_particles=50.0,
    brightness=1e5,
    seed=1,
)


# --- pieces ----------------------------------------------------------------
def test_gamma_factors_of_the_two_geometries():
    """The 3-D Gaussian and the 2-D membrane have different shape factors."""
    g3d = gamma_factors(two_d=False)
    g2d = gamma_factors(two_d=True)
    assert g3d[0] == pytest.approx(1.0 / (2.0 * math.sqrt(2.0)))
    assert g2d[0] == pytest.approx(0.5)
    # each is a decreasing sequence: higher orders weigh the profile more
    for g in (g3d, g2d):
        assert all(b < a for a, b in zip(g, g[1:]))


def test_pair_counts_is_the_triangular_weighting():
    """N pixels give n - |d| pairs at separation d."""
    counts = _pair_counts(4)
    np.testing.assert_allclose(counts, [1, 2, 3, 4, 3, 2, 1])
    assert counts.sum() == 4**2


def test_correlation_grid_peaks_at_zero_lag_and_decays():
    """The correlation is largest at zero lag and falls away on both axes."""
    xi, psi = np.meshgrid(np.arange(6.0), np.arange(6.0))
    g = correlation_grid(xi, psi, 10.0, 0.25, 5.0, 4e-6, 2e-3, 0.05)
    assert g[0, 0] == pytest.approx(1.0)
    assert np.all(np.diff(g[0]) < 0), "must decay along the fast axis"
    assert np.all(np.diff(g[:, 0]) < 0), "must decay along the slow axis"


def test_triple_correlation_is_finite_and_positive():
    """The three-point term feeding the shot-noise variance stays usable."""
    for lag in ((0, 0), (1, 0), (0, 1), (3, 2)):
        v = triple_correlation(lag, (0, 0), lag, 10.0, 0.25, 5.0, 4e-6, 2e-3, 0.05)
        assert np.isfinite(v) and v > 0


def test_nearest_spd_makes_a_matrix_usable_for_sampling():
    """A symmetric matrix with a negative eigenvalue becomes positive definite."""
    a = np.array([[1.0, 2.0], [2.0, 1.0]])  # eigenvalues 3 and -1
    assert min(np.linalg.eigvalsh(a)) < 0
    spd = nearest_spd(a)
    np.testing.assert_allclose(spd, spd.T)
    assert min(np.linalg.eigvalsh(spd)) > 0
    np.linalg.cholesky(spd)  # must not raise


def test_covariance_is_symmetric_and_correlates_lags():
    """Correlation estimates at different lags share pixels, so they covary."""
    gamma = gamma_factors()
    cov = correlation_covariance(
        3, 24, 24, 10.0, 0.05, 0.25, 5.0, 4e-6, 2e-3, 0.05, 1.0, 0.1, gamma
    )
    np.testing.assert_allclose(cov, cov.T, rtol=1e-12)
    off = cov[1:, 1:][~np.eye(cov.shape[0] - 1, dtype=bool)]
    assert np.any(np.abs(off) > 0), "the off-diagonal terms must not vanish"


# --- the predictions -------------------------------------------------------
def test_precision_improves_as_one_over_root_frames():
    """Averaging N frames divides the covariance by N, so the error goes as 1/sqrt(N)."""
    common = dict(pixel_time=8e-6, line_time=1e-3, **FAST)
    few = rics_precision(10.0, n_images=25, **common)
    many = rics_precision(10.0, n_images=100, **common)

    assert many.relative_error < few.relative_error
    assert many.relative_error == pytest.approx(few.relative_error / 2.0, rel=0.35)


def test_more_photons_measure_better():
    """A brighter sample gives a more precise diffusion coefficient."""
    common = dict(
        pixel_time=8e-6,
        line_time=1e-3,
        n_images=50,
        **{k: v for k, v in FAST.items() if k != "brightness"},
    )
    dim = rics_precision(10.0, brightness=3e4, **common)
    bright = rics_precision(10.0, brightness=3e5, **common)
    assert bright.relative_error < dim.relative_error


def test_a_hopeless_acquisition_is_reported_as_hopeless():
    """One dim frame cannot measure D, and the estimate says so rather than lying."""
    poor = rics_precision(
        10.0,
        pixel_time=8e-6,
        line_time=1e-3,
        n_images=1,
        **{**FAST, "brightness": 1e4, "n_particles": 5.0},
    )
    assert poor.relative_error > 0.5


def test_there_is_an_optimal_dwell_time():
    """Too fast carries no diffusion information; too slow has decorrelated.

    The interior minimum is the whole point of the tool: it says which scan
    speed to use, and the answer is not "as fast as possible".
    """
    errors = {}
    for dwell in (1e-6, 4e-6, 16e-6, 64e-6):
        line = max(dwell * FAST["nx"] * 1.2, 1e-3)
        errors[dwell] = rics_precision(
            10.0, pixel_time=dwell, line_time=line, n_images=100, **FAST
        ).relative_error

    best = min(errors, key=errors.get)
    assert best not in (min(errors), max(errors)), (
        f"the optimum should be interior, got {best} from {errors}"
    )


def test_a_slow_sample_gains_far_more_from_a_long_dwell():
    """How much a short dwell costs you depends on how fast the sample moves.

    A slowly diffusing molecule has barely moved between neighbouring pixels at
    a short dwell, so the correlation carries almost no information about D and
    the penalty is severe. A fast one has already moved, so scanning fast costs
    it comparatively little.

    Stated as a *ratio* between two fixed dwells rather than as the position of
    the minimum: the error estimate is itself a Monte-Carlo quantity, and on a
    flat stretch of the curve an argmin flips between neighbouring points from
    noise alone.
    """
    short, long = 4e-6, 128e-6

    def penalty(d):
        errors = []
        for dwell in (short, long):
            line = max(dwell * FAST["nx"] * 1.2, 1e-3)
            errors.append(
                rics_precision(
                    d,
                    pixel_time=dwell,
                    line_time=line,
                    n_images=100,
                    **{**FAST, "n_repeats": 60},
                ).relative_error
            )
        return errors[0] / errors[1]

    slow_sample = penalty(2.0)
    fast_sample = penalty(50.0)

    assert slow_sample > 3.0, "a slow sample should be badly hurt by a short dwell"
    assert fast_sample < 2.5, "a fast sample should mind much less"
    assert slow_sample > 2 * fast_sample


def test_an_impossible_scan_timing_is_rejected():
    """A line cannot be shorter than the pixels it contains."""
    with pytest.raises(UnrealisableScan, match="cannot fit"):
        rics_precision(10.0, pixel_time=1e-3, line_time=1e-4, **FAST)


def test_a_lag_the_image_cannot_hold_is_rejected():
    """More lags than the image has pixels is a setting, not a division by zero.

    Every entry is divided by the number of pixel pairs that realise its lag,
    and the triple-product term counts the positions where the pair fits twice
    over, so both vanish once the lag approaches the image size. The estimator
    used to run into that as ``ZeroDivisionError`` from four loops down, and
    the fitted range is a spin box: ``nx`` starts at 8 while ``n_lags`` goes up
    to 15, so the two can be set against each other from the panel.

    The failure has to stay a plain ``ValueError`` and *not* an
    ``UnrealisableScan``: no acquisition satisfies it, so a caller sweeping
    acquisitions must be told rather than skip every point in silence.
    """
    with pytest.raises(ValueError, match="too large for a 8x8 image") as raised:
        rics_precision(
            10.0,
            pixel_time=4e-6,
            line_time=2e-3,
            pixel_size=0.05,
            nx=8,
            ny=8,
            n_lags=8,
            n_repeats=5,
        )
    assert not issubclass(raised.type, UnrealisableScan)

    # The same guard on the covariance itself, which is public and divides by
    # the pair counts directly.
    with pytest.raises(ValueError, match=r"at most n_lags=2"):
        correlation_covariance(
            6,
            6,
            6,
            10.0,
            0.05,
            0.25,
            5.0,
            4e-6,
            2e-3,
            0.05,
            1.0,
            0.1,
            gamma_factors(),
        )

    # The largest lag the guard allows still predicts.
    assert (
        rics_precision(
            10.0,
            pixel_time=4e-6,
            line_time=2e-3,
            pixel_size=0.05,
            nx=8,
            ny=8,
            n_lags=3,
            n_repeats=5,
        ).relative_error
        > 0.0
    )


def test_a_focus_that_is_not_elongated_is_an_ordinary_acquisition():
    """A spherical or squat focus must predict, not raise.

    The dwell-time brightness correction is written with a ``sqrt(1 - beta)``
    that vanishes at ``w_z == w_r`` and turns imaginary below it, but neither is
    a real singularity: the factor cancels, so the prediction is continuous
    across the aspect ratio. Taking the expression at face value used to give a
    ``ZeroDivisionError`` at ``w_z == w_r`` and a ``math domain error`` below.
    """
    common = dict(pixel_time=8e-6, line_time=1e-3, n_images=50, w_r=0.25, **FAST)

    errors = [rics_precision(10.0, w_z=w_z, **common).relative_error for w_z in (0.2, 0.25, 0.3)]
    assert all(np.isfinite(e) and e > 0 for e in errors)

    # continuity through the spherical case: approaching it from the elongated
    # side must land on the value taken there.
    near = rics_precision(10.0, w_z=0.25 * (1 + 1e-6), **common).relative_error
    assert near == pytest.approx(errors[1], rel=1e-6)


def test_two_d_geometry_runs():
    """The membrane geometry uses different shape factors and still predicts."""
    r = rics_precision(1.0, pixel_time=8e-6, line_time=1e-3, n_images=100, two_d=True, **FAST)
    assert np.isfinite(r.relative_error) and r.relative_error > 0


def test_result_reports_bias_separately_from_spread():
    """Bias and noise are different failures: averaging fixes only one."""
    r = rics_precision(10.0, pixel_time=8e-6, line_time=1e-3, n_images=100, **FAST)
    assert r.fitted.size == FAST["n_repeats"]
    assert np.isfinite(r.bias)
    assert r.relative_error == pytest.approx(math.sqrt(r.msre), rel=1e-12)

    hand_made = RicsPrecision(0.1, 0.01, 10.0, 1e-6, 1e-3)
    assert math.isnan(hand_made.bias), "no fitted values means no bias to report"


def test_prediction_serialises():
    """JSON-friendly for a CLI or an RPC call."""
    import json

    r = rics_precision(10.0, pixel_time=8e-6, line_time=1e-3, n_images=50, **FAST)
    restored = json.loads(json.dumps(r.to_dict()))
    assert restored["n_images"] == 50
    assert restored["relative_error"] > 0


def test_the_prediction_is_reproducible():
    """A fixed seed gives a fixed answer, so a reported number can be checked."""
    common = dict(pixel_time=8e-6, line_time=1e-3, n_images=50, **FAST)
    assert rics_precision(10.0, **common).relative_error == pytest.approx(
        rics_precision(10.0, **common).relative_error, rel=1e-12
    )
