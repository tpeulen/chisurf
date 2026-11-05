"""The Burst Selection count-rate trace: bins as stairs, bursts as shaded spans.

Drawn for the range on screen: the model hands full-resolution bins and this cuts them to the
plot's x-limits before thinning, so zooming in shows the bins themselves rather than the
min/max of blocks thinned for the whole window (which drew every burst as a spike from zero).
The bursts of the table are shaded, so a burst reads as one span however its bins fluctuate.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from emtk import implot
from emtk.i18n import tr


def _span_outline(starts: np.ndarray, stops: np.ndarray, height: float):
    """``(xs, ys)`` of rectangles ``[start, stop] x [0, height]``, one after another along x."""
    xs = np.column_stack([starts, starts, stops, stops]).ravel()
    ys = np.tile([0.0, height, height, 0.0], starts.size)
    return xs, ys


def draw_count_rate(model: Any, state: dict) -> None:
    """Count-rate plot of *model* (all photons, burst photons, burst spans) in kHz.

    *state* is the caller's dict that survives frames: it remembers which curves the x-axis was
    last fitted to, so new data refits once and a zoom is then kept; an ``"x_range"`` entry
    ``(lo, hi)`` sets the x-axis once (a display-range control, a tour, a screenshot).
    """
    curves = model.trace_curves()
    if not implot.begin_plot(f"Count rate ({model.trace_bin_ms:g} ms bins)", (-1, -1)):
        return
    implot.setup_axes("Time in the window (s)", "Count rate (kHz)")  # count rates read in kHz
    t = [np.asarray(c[0], dtype=float) for c in curves.values() if len(c[0])]
    if t:
        x0 = min(float(a[0]) for a in t)
        x1 = max(float(a[-1]) for a in t) + float(model.trace_bin_ms) / 1e3
        key = id(curves)
        request = state.pop("x_range", None)  # a range asked for from outside, applied once
        if request is not None:
            state["trace_key"] = key
            lo, hi = float(request[0]), float(request[1])
            implot.setup_axis_limits(implot.AXIS_X1, lo, hi, implot.COND_ALWAYS)
        elif state.get("trace_key") != key:
            state["trace_key"] = key
            implot.setup_axis_limits(implot.AXIS_X1, x0, x1, implot.COND_ALWAYS)
            lo, hi = x0, x1
        else:
            limits = implot.get_plot_limits()
            lo, hi = float(limits.x_min), float(limits.x_max)
        shown = model.visible_trace_curves(lo, hi)
        starts, stops = model.burst_spans()
        visible = (stops >= lo) & (starts <= hi)
        for key_, name in (("all", tr("All photons")), ("selected", tr("Selected photons"))):
            if key_ in shown:
                x, y = shown[key_]
                implot.plot_stairs(name, x, np.asarray(y, dtype=float) / 1e3)
        if visible.any():  # last, so the traces keep the first colours; translucent over them
            top = max([float(np.max(y)) for _, y in shown.values() if len(y)] or [1.0]) / 1e3
            implot.plot_shaded(tr("Bursts"), *_span_outline(starts[visible], stops[visible], top),
                               fill_alpha=0.25)
    implot.end_plot()
