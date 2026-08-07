"""``thin_for_plot`` decimates a huge trace without hiding what it looks like.

The property under test throughout: a value at or under the budget passes
through untouched, and a value well over budget comes back short but with
its extrema (bursts, dips) still present -- not aliased away by a plain
stride, and not silently truncated to a prefix.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fio.decimate import thin_for_plot


def test_under_budget_passes_through_unchanged():
    x = np.arange(100)
    y = np.sin(x / 5.0)

    x_out, y_out = thin_for_plot(x, y, max_points=1_000)

    np.testing.assert_array_equal(x_out, x)
    np.testing.assert_array_equal(y_out, y)


def test_exactly_at_budget_passes_through_unchanged():
    x = np.arange(1_000)
    y = x.astype(float)

    x_out, y_out = thin_for_plot(x, y, max_points=1_000)

    np.testing.assert_array_equal(x_out, x)
    np.testing.assert_array_equal(y_out, y)


def test_over_budget_is_shortened():
    x = np.arange(10_000_000)
    y = np.random.default_rng(0).normal(size=x.size)

    x_out, y_out = thin_for_plot(x, y, max_points=100_000)

    assert len(x_out) == len(y_out)
    assert len(x_out) <= 200_000
    assert len(x_out) < len(x)


def test_a_spike_survives_thinning():
    """A single-sample burst must not be averaged/strided away."""
    n = 2_000_000
    y = np.zeros(n)
    spike_index = 777_777
    y[spike_index] = 1000.0
    x = np.arange(n)

    _, y_out = thin_for_plot(x, y, max_points=10_000)

    assert y_out.max() == 1000.0


def test_a_dip_survives_thinning():
    """A single-sample dip (the min extreme) must also survive."""
    n = 2_000_000
    y = np.zeros(n)
    y[500_000] = -1000.0
    x = np.arange(n)

    _, y_out = thin_for_plot(x, y, max_points=10_000)

    assert y_out.min() == -1000.0


def test_output_order_is_non_decreasing_in_x():
    """Bins are emitted left to right, in original relative order.

    So the thinned trace never runs backwards.
    """
    x = np.arange(500_000)
    y = np.random.default_rng(1).normal(size=x.size)

    x_out, _ = thin_for_plot(x, y, max_points=1_000)

    assert np.all(np.diff(x_out) >= 0)


def test_a_constant_bin_is_not_duplicated():
    """Min == max within a bin must not double-emit the same point."""
    x = np.arange(20)
    y = np.zeros(20)

    x_out, y_out = thin_for_plot(x, y, max_points=4)

    assert len(x_out) == len(set(x_out.tolist()))


def test_single_array_form_returns_values_only():
    y = np.random.default_rng(2).normal(size=5_000_000)

    result = thin_for_plot(y, max_points=1_000)

    assert isinstance(result, np.ndarray)
    assert len(result) <= 2_000


def test_empty_input_is_returned_unchanged():
    x = np.array([])
    y = np.array([])

    x_out, y_out = thin_for_plot(x, y, max_points=10)

    assert len(x_out) == 0
    assert len(y_out) == 0


def test_non_positive_budget_is_a_no_op():
    """A caller that passes max_points<=0 gets the input back, not a crash."""
    x = np.arange(1000)
    y = x.astype(float)

    x_out, y_out = thin_for_plot(x, y, max_points=0)

    np.testing.assert_array_equal(x_out, x)
    np.testing.assert_array_equal(y_out, y)


# -- the budget belongs to the plot, not to one call ---------------------------


def test_one_curve_never_exceeds_its_budget():
    """The docstring used to promise ``2 * max_points``; it is ``max_points``."""
    x = np.arange(1_000_000)
    y = np.sin(x / 1000.0)

    x_out, _ = thin_for_plot(x, y, max_points=10_000)

    assert len(x_out) <= 10_000


def test_the_budget_splits_across_the_curves_sharing_a_plot():
    """A panel drawing two layers per file must not spend the budget per curve.

    This is the whole failure: every individual ``thin_for_plot`` call looked
    correctly bounded while the plot drew several times what it was configured
    for -- 1.5 M points became 3.3 M across a two-layer, four-diagnostic panel.
    """
    from chisurf.core.fio.decimate import per_curve_budget

    total, n_files, n_layers = 1_500_000, 10, 2
    budget = per_curve_budget(total, n_files * n_layers)

    x = np.arange(3_000_000)
    drawn = sum(
        len(thin_for_plot(x, x.astype(float), max_points=budget)[0])
        for _ in range(n_files * n_layers)
    )
    assert drawn <= total


def test_the_split_never_decimates_a_curve_to_nothing():
    """A floor, because a curve thinned to five points is not a plot."""
    from chisurf.core.fio.decimate import MIN_CURVE_POINTS, per_curve_budget

    assert per_curve_budget(1000, 500) == MIN_CURVE_POINTS
    assert per_curve_budget(1_500_000, 0) == 1_500_000
