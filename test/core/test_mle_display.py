"""The display rules that only matter when something has gone wrong.

Every rule in :mod:`chisurf.core.fluorescence.mle.display` exists because the
obvious version produces a panel that looks fine on a good fit and becomes
unreadable on a bad one — which is precisely when someone is looking at it. So
these tests are mostly about bad fits: a diverged model, a background-dominated
decay, one catastrophic residual channel, an empty window.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fluorescence.mle.display import (
    decay_curves,
    decay_ylim,
    overlay_scaled,
    residual_ylim,
    vv_vh_window,
    weighted_residuals,
)


def _stack(vv, vh):
    return np.hstack([np.asarray(vv, dtype=float), np.asarray(vh, dtype=float)])


def test_each_half_gets_its_own_window():
    """The two channels do not share a fit window, and slicing as one is wrong."""
    stack = _stack(np.arange(10), 100 + np.arange(10))

    out = vv_vh_window(stack, vv=(2, 5), vh=(7, 9))

    np.testing.assert_array_equal(out, [2, 3, 4, 107, 108])


def test_a_window_past_the_end_is_clamped_rather_than_wrapping():
    stack = _stack(np.arange(6), 100 + np.arange(6))

    out = vv_vh_window(stack, vv=(4, 99), vh=(0, 2))

    np.testing.assert_array_equal(out, [4, 5, 100, 101])


def test_an_overlay_is_area_matched_not_peak_matched():
    """One hot bin must not decide the scaling of the whole curve."""
    data = np.full(100, 10.0)
    curve = np.full(100, 1.0)
    curve[50] = 1000.0                    # the hot bin

    scaled = overlay_scaled(curve, data)

    assert scaled.sum() == pytest.approx(data.sum())
    # Peak matching would have divided by 1000 and buried the curve.
    assert scaled[0] > 0.5


def test_an_empty_overlay_is_returned_unchanged_rather_than_nan():
    curve = np.zeros(10)

    np.testing.assert_array_equal(overlay_scaled(curve, np.ones(10)), curve)


def test_residuals_are_zero_where_there_are_no_counts():
    """No photons means no uncertainty to divide by, not an infinity."""
    data = np.array([0.0, 4.0, 0.0, 9.0])
    model = np.array([1.0, 2.0, 5.0, 3.0])

    residuals = weighted_residuals(data, model)

    assert residuals[0] == 0.0 and residuals[2] == 0.0
    assert residuals[1] == pytest.approx((4 - 2) / 2.0)
    assert residuals[3] == pytest.approx((9 - 3) / 3.0)
    assert np.isfinite(residuals).all()


def test_the_decay_range_follows_the_data_not_everything_drawn():
    """A runaway model must not take the log axis with it."""
    data = np.array([1.0, 10.0, 100.0])

    lo, hi = decay_ylim(data)

    assert lo == pytest.approx(0.5)
    assert hi == pytest.approx(300.0)


def test_the_decay_range_is_in_counts_not_log10():
    """A log axis converts for itself, so pre-logging the range logs it twice.

    That is not hypothetical — it is what the burst tool did, and it put the
    decay off the top of its own panel while the axis showed a few counts.
    """
    data = np.array([6.0, 2000.0])

    lo, hi = decay_ylim(data)

    assert hi > 1000.0, "a range in log10 would be about 3.8"
    assert 1.0 < lo < 10.0


def test_an_empty_decay_falls_back_rather_than_raising():
    assert decay_ylim(np.zeros(5)) == (0.1, 1.0e5)
    assert decay_ylim(np.array([np.nan, -3.0])) == (0.1, 1.0e5)


def test_one_catastrophic_residual_does_not_set_the_scale():
    """The percentile, not the maximum — otherwise every other residual flattens."""
    residuals = np.concatenate([np.random.default_rng(0).normal(0, 1, 999), [5000.0]])

    lo, hi = residual_ylim(residuals)

    assert hi < 50.0
    assert lo == -hi


def test_a_good_fit_is_not_magnified_until_its_noise_looks_like_structure():
    residuals = np.random.default_rng(1).normal(0.0, 0.2, 500)

    _lo, hi = residual_ylim(residuals)

    assert hi == 5.0        # the floor, not the data's own tiny spread


def test_a_diverged_model_is_clipped_and_says_so():
    """The panel stays readable and the divergence is reported, not hidden."""
    data = _stack(np.full(50, 100.0), np.full(50, 100.0))
    model = _stack(np.full(50, 1e7), np.full(50, 1e7))

    curves = decay_curves(data, model)

    assert curves.diverged
    assert curves.model.max() <= 100.0 * 10.0
    # And the fitted values themselves are none of this function's business:
    # only what is drawn was clipped.
    assert model.max() == 1e7


def test_a_sane_model_is_not_clipped_and_is_not_called_diverged():
    data = _stack(np.full(20, 100.0), np.full(20, 100.0))
    model = _stack(np.full(20, 95.0), np.full(20, 98.0))

    curves = decay_curves(data, model)

    assert not curves.diverged
    np.testing.assert_allclose(curves.model, vv_vh_window(model))


def test_a_tail_fit_draws_no_irf():
    """A tail fit does not deconvolve, so an IRF overlay would be a false claim."""
    data = _stack(np.full(20, 50.0), np.full(20, 50.0))
    model = data * 0.9
    irf = _stack(np.arange(20.0), np.arange(20.0))

    with_irf = decay_curves(data, model, irf=irf, deconvolved=True)
    tail = decay_curves(data, model, irf=irf, deconvolved=False)

    assert with_irf.irf is not None
    assert tail.irf is None


def test_residuals_are_computed_before_the_window_not_after():
    """Windowing first would pair a data channel with the wrong model channel."""
    n = 20
    data = _stack(np.arange(1.0, n + 1), np.arange(1.0, n + 1))
    model = _stack(np.arange(1.0, n + 1), np.arange(1.0, n + 1))
    model[5] = 0.0                       # one bad channel inside the VV window

    curves = decay_curves(data, model, vv=(4, 8), vh=(0, 2))

    # Channel 5 sits at offset 1 of the VV window and must be the non-zero one.
    assert curves.residuals[1] != 0.0
    assert np.count_nonzero(curves.residuals) == 1


def test_the_curves_carry_ready_made_ranges():
    data = _stack(np.full(10, 20.0), np.full(10, 20.0))
    curves = decay_curves(data, data * 0.95)

    assert curves.decay_ylim == decay_ylim(curves.data)
    assert curves.residual_ylim == residual_ylim(curves.residuals)
    assert curves.channels.size == curves.data.size


def test_the_fit_can_report_divergence_the_amplitude_does_not_show():
    """A parameter pinned at its bound is a fact; a big amplitude is a symptom."""
    data = _stack(np.full(20, 100.0), np.full(20, 100.0))
    model = data * 0.98                     # looks perfectly healthy

    inferred = decay_curves(data, model)
    told = decay_curves(data, model, diverged=True)

    assert not inferred.diverged
    assert told.diverged
    # And being told does not change what is drawn — only what is said.
    np.testing.assert_allclose(told.model, inferred.model)
