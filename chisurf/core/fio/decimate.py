"""Thin a huge array pair down to what a plot can actually draw.

A `.pto` container stacks a measurement's raw stream beside every result
computed from it (see :mod:`chisurf.core.fio.pto`), and several photon-level
plots (a time trace, a per-photon delta-time diagnostic) were sized for a
single vendor file, one at a time. Merging several files into one container,
or simply opening a long acquisition, hands the same plot millions of points
at once -- Qt has to lay out and repaint every one of them, which is where
the lag is, not in the data itself.

:func:`thin_for_plot` is the one place that decimation happens, so every
caller gets the same, tested behaviour rather than reinventing a stride or a
"just take the first N" cutoff (the second silently hides everything past
the cutoff, which is worse than slow -- it looks complete).
"""

from __future__ import annotations

import numpy as np

__all__ = ["thin_for_plot", "per_curve_budget"]

#: Points before decimation kicks in at all. A well-behaved binned plot
#: (a histogram, a correlation curve) never gets near this and is never
#: touched by the caller; a raw per-photon plot of a real measurement is
#: exactly what does.
DEFAULT_MAX_POINTS = 1_500_000


#: Smallest per-curve budget worth honouring. Below roughly this, thinning stops
#: being decimation and starts being a different plot.
MIN_CURVE_POINTS = 1000


def per_curve_budget(
    total: int, n_curves: int, *, minimum: int = MIN_CURVE_POINTS
) -> int:
    """Split a **per-plot** point budget across the curves sharing that plot.

    The budget is a property of the widget, not of a call to it: what makes a
    plot slow is the number of points Qt has to lay out and repaint in it,
    summed over everything drawn there. Passing the whole budget to each
    :func:`thin_for_plot` call is therefore not a budget at all -- a panel
    drawing an all-photon and a selected-photon layer per file, over four
    diagnostics, drew eight times the number it was configured for, and did it
    while every individual call looked correctly bounded.

    Parameters
    ----------
    total : int
        The configured budget for one plot (``data_loading.max_plot_points``).
    n_curves : int
        How many curves will be drawn into it -- files times layers, and any
        other multiplier the caller knows about. Values below 1 are treated as
        1.
    minimum : int
        Floor, so a plot with many curves still shows each of them as something
        other than a straight line. Going over budget here is the lesser evil:
        the alternative is a curve decimated to nothing.

    Returns
    -------
    int
        Points each curve may draw.
    """
    return max(minimum, total // max(1, int(n_curves)))


def thin_for_plot(x, y=None, *, max_points: int = DEFAULT_MAX_POINTS):
    """Return ``(x, y)`` thinned to about *max_points* samples, or fewer.

    Uses **min/max-per-bin** decimation, not a plain stride: splitting the
    input into ``max_points // 2`` bins and keeping each bin's minimum and
    maximum sample (in their original left-to-right order) is what makes a
    burst or a dip in a time-ordered trace survive thinning. A stride
    (every Nth sample) is only safe for a genuinely unordered point cloud
    (e.g. a 2-D phasor scatter) -- for a trace it aliases peaks away, which
    is worse than the slowness it was meant to fix: a decimated plot that
    silently omits the one feature someone was looking for.

    Parameters
    ----------
    x : array-like
        Sample positions (a photon index, a time axis, ...).
    y : array-like, optional
        Sample values. Omitted for a single 1-D series with no separate
        x-axis -- *x* is then treated as the values, thinned against an
        implicit ``0..len(x)`` index, and only the thinned values are
        returned (not a tuple).
    max_points : int
        Budget, not a hard visual cap: values already at or under this count
        pass through completely untouched (returned as plain ``numpy``
        arrays, but never copied into a *shorter* form). Defaults to
        :data:`DEFAULT_MAX_POINTS`.

    Returns
    -------
    tuple of numpy.ndarray, or numpy.ndarray
        ``(x_thinned, y_thinned)``, or just ``y_thinned`` when *y* was
        omitted. Never longer than *max_points* -- the input is split into
        ``max_points // 2`` bins and each contributes at most two samples --
        and exactly the input when it was already within budget.

        This bounds **one** curve. A plot holding several of them is bounded by
        splitting the budget first; see :func:`per_curve_budget`.
    """
    single = y is None
    x = np.asarray(x)
    y = x if single else np.asarray(y)

    n = len(x)
    if n <= max_points or max_points <= 0:
        return y if single else (x, y)

    n_bins = max(1, max_points // 2)
    bin_size = int(np.ceil(n / n_bins))
    n_bins = int(np.ceil(n / bin_size))
    pad = n_bins * bin_size - n
    if pad:
        x_padded = np.concatenate([x, np.full(pad, x[-1], dtype=x.dtype)])
        y_padded = np.concatenate([y, np.full(pad, y[-1], dtype=y.dtype)])
    else:
        x_padded, y_padded = x, y

    x_2d = x_padded.reshape(n_bins, bin_size)
    y_2d = y_padded.reshape(n_bins, bin_size)
    min_pos = np.argmin(y_2d, axis=1)
    max_pos = np.argmax(y_2d, axis=1)
    first_pos = np.minimum(min_pos, max_pos)
    second_pos = np.maximum(min_pos, max_pos)
    rows = np.arange(n_bins)

    xs = np.empty(2 * n_bins, dtype=x.dtype)
    ys = np.empty(2 * n_bins, dtype=y.dtype)
    xs[0::2] = x_2d[rows, first_pos]
    ys[0::2] = y_2d[rows, first_pos]
    xs[1::2] = x_2d[rows, second_pos]
    ys[1::2] = y_2d[rows, second_pos]

    # A bin whose min and max are the same sample (constant, or one real
    # value plus padding) would otherwise appear twice.
    same = first_pos == second_pos
    if np.any(same):
        keep = np.ones(2 * n_bins, dtype=bool)
        keep[1::2] = ~same
        xs, ys = xs[keep], ys[keep]

    return ys if single else (xs, ys)
