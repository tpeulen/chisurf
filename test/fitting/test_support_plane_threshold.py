"""BUG-10: the support-plane threshold and crossing rules, pinned.

Two faults, measured on PDA3c against MCMC (widths off by 1.32/2.05/2.86 at
1500/2500/5000 bursts — a ratio that *grew* with n because the faults pushed
in opposite directions):

1. the F-test threshold form rescales by ``chi2r_min``, which is right for
   least squares (unknown noise scale) and wrong for a likelihood deviance
   (scale fixed) — a likelihood objective takes the likelihood-ratio level;
2. a scan whose curve merely *touched* the threshold at its last grid point
   reported that grid edge as a crossing.
"""

import numpy as np
import pytest
import scipy.stats

import chisurf.core.fitting as fitting
import chisurf.core.fitting.support_plane as sp
import chisurf.core.math.statistics as stats


def test_the_likelihood_threshold_is_the_likelihood_ratio_level():
    """Delta chi2 = 6.63 at 99% and one parameter, NOT rescaled by chi2r."""
    chi2r_min, nu = 2.3, 1000
    t = stats.chi2_threshold(chi2r_min, 1, nu, 0.99, objective="likelihood")
    assert t == pytest.approx(chi2r_min + 6.6349 / nu, rel=1e-3)
    # A chi2r far from one must not move the *excess* over the minimum.
    t2 = stats.chi2_threshold(1.0, 1, nu, 0.99, objective="likelihood")
    assert (t - chi2r_min) == pytest.approx(t2 - 1.0, rel=1e-12)


def test_the_least_squares_threshold_is_unchanged():
    """The F-test form stays exactly what it was — default behaviour."""
    chi2r_min, nu = 2.3, 1000
    want = chi2r_min * (1.0 + 1.0 / nu * scipy.stats.f.isf(0.01, 1, nu))
    assert stats.chi2_threshold(chi2r_min, 1, nu, 0.99) == pytest.approx(want)
    assert stats.chi2_threshold(chi2r_min, 1, nu, 0.99, objective="least_squares") == pytest.approx(
        want
    )


def test_objective_type_reads_the_noise_model_and_the_model_declaration():
    class _F:
        noise_model = "poisson"
        model = None

    assert fitting.objective_type(_F()) == "likelihood"

    class _M:
        objective_type = "likelihood"

    class _F2:
        noise_model = "default"
        model = _M()

    assert fitting.objective_type(_F2()) == "likelihood"

    class _F3:
        noise_model = "default"
        model = None

    assert fitting.objective_type(_F3()) == "least_squares"


def test_a_terminal_graze_is_not_a_crossing():
    """The curve touches the threshold at the scan's edge and never exceeds:
    the old code returned that grid edge as the interval; now it is None.
    """
    values = np.array([0.0, 1.0, 2.0, 3.0])
    chi2r = np.array([1.0, 1.2, 1.6, 2.0])  # ends exactly AT threshold 2.0
    assert sp._find_side_crossing(values, chi2r, 2.0, 0.0, +1) is None


def test_a_touch_followed_by_exceedance_is_a_crossing_at_the_touch():
    values = np.array([0.0, 1.0, 2.0, 3.0])
    chi2r = np.array([1.0, 1.5, 2.0, 2.5])  # touches at 2.0, then exceeds
    got = sp._find_side_crossing(values, chi2r, 2.0, 0.0, +1)
    assert got == pytest.approx(2.0)


def test_a_true_bracket_still_interpolates():
    values = np.array([0.0, 1.0, 2.0])
    chi2r = np.array([1.0, 1.5, 2.5])  # crosses 2.0 between 1 and 2
    got = sp._find_side_crossing(values, chi2r, 2.0, 0.0, +1)
    assert got == pytest.approx(1.5)


def test_the_scan_result_objective_reaches_the_interval_thresholds():
    """confidence_intervals_from_scan_result honours result['objective']."""
    nu = 500
    result = {
        "parameter_values": np.linspace(-1, 1, 41),
        "chi2r": 2.0 + 40.0 * np.linspace(-1, 1, 41) ** 2,
        "chi2r_min": 2.0,
        "v0": 0.0,
        "nu": nu,
        "n_extra_params": 1,
        "objective": "likelihood",
    }
    intervals = sp.confidence_intervals_from_scan_result(result, p_values=(0.99,))
    assert intervals, "the scan is well-formed"
    want = 2.0 + scipy.stats.chi2.isf(0.01, 1) / nu
    assert intervals[0]["threshold"] == pytest.approx(want, rel=1e-9)
    lo, hi = intervals[0]["crossings"]
    assert lo is not None and hi is not None
    assert lo == pytest.approx(-hi, rel=1e-6)
