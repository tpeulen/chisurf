"""The residual-strip rule: wres above the data, one x-axis, a symmetric range, a thick zero.

``chisurf.emtk.residual_plot`` is the one helper every fit plot draws its weighted residuals
with; these tests pin the rule it encodes (OKF ``subsystems/chiplot.md``, "Residual strips").
"""

from __future__ import annotations

import numpy as np
import pytest

emtk = pytest.importorskip("emtk")
from emtk import implot  # noqa: E402
from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.emtk.residual_plot import (  # noqa: E402
    WRES_FRACTION,
    ZERO_LINE_WIDTH,
    ResidualPlot,
    Residuals,
    symmetric_limit,
)


def _frames(draw, frames=3, size=(640, 480), io=None, storage=None):
    io = emtk.IO() if io is None else io
    storage = {} if storage is None else storage
    for _ in range(frames):
        with emtk.frame(RecordingPainter(), (0, 0, *size), io=io, storage=storage):
            emtk.begin("w")
            draw()
            emtk.end()
    return io, storage


def _decay():
    x = np.arange(400.0)
    y = 1000.0 * np.exp(-x / 40.0) + 3.0
    wres = np.random.default_rng(1).normal(size=x.size)
    wres[120] = -9.0  # one big negative deviation: the range must still be symmetric
    return x, y, wres


# -- the range ------------------------------------------------------------------------------ #
def test_symmetric_limit_takes_max_abs_with_headroom():
    assert symmetric_limit([0.5, -4.0, 2.0], pad=1.0) == pytest.approx(4.0)
    assert symmetric_limit(np.array([1.0, -2.0]), pad=1.1) == pytest.approx(2.2)


def test_symmetric_limit_ignores_nan_and_spans_every_trace():
    a = np.array([np.nan, 1.0, np.inf])
    b = np.array([-3.0, np.nan])
    assert symmetric_limit([a, b], pad=1.0) == pytest.approx(3.0)


def test_symmetric_limit_robust_percentile_and_minimum():
    values = np.r_[np.ones(999), 1000.0]
    assert symmetric_limit(values, percentile=99.0, pad=1.0) == pytest.approx(1.0)
    assert symmetric_limit(values, pad=1.0) == pytest.approx(1000.0)
    assert symmetric_limit([0.1, -0.2], minimum=3.0) == pytest.approx(3.0)


def test_symmetric_limit_of_nothing_is_a_usable_range():
    assert symmetric_limit([]) == 1.0
    assert symmetric_limit(np.full(5, np.nan)) == 1.0


# -- the drawing ---------------------------------------------------------------------------- #
def _draw_pair(plot, x, y, wres, seen, **kw):
    def data():
        implot.plot_line("Data", x, y)
        seen["data_limits"] = implot.get_plot_limits()
        seen["data_x_axis"] = implot._cur.current_plot.axes[implot.AXIS_X1]

    return lambda: plot.draw(data, [Residuals("w.res.", x, wres)], x_label="t", y_label="c", **kw)


def test_strip_sits_above_the_data_and_shares_its_x_axis():
    x, y, wres = _decay()
    plot, seen = ResidualPlot("decay"), {}
    _frames(_draw_pair(plot, x, y, wres, seen, log_y=True))
    strip, data = plot.rects["wres"], plot.rects["data"]
    assert strip[1] + strip[3] <= data[1], "the residual strip is drawn above the data"
    assert strip[0] == pytest.approx(data[0]) and strip[2] == pytest.approx(data[2])
    share = strip[3] / (strip[3] + data[3])
    assert 0.15 < share < 0.30, share
    assert WRES_FRACTION == pytest.approx(0.22)
    limits = seen["data_limits"]
    assert (limits.x_min, limits.x_max) == pytest.approx((x[0], x[-1]))
    assert plot.x_range == pytest.approx([x[0], x[-1]])


def test_zoom_in_one_plot_moves_the_other():
    x, y, wres = _decay()
    plot, seen = ResidualPlot("zoom"), {}
    io, storage = _frames(_draw_pair(plot, x, y, wres, seen))
    plot.x_range[0], plot.x_range[1] = 100.0, 200.0  # what a zoom in either plot writes
    _frames(_draw_pair(plot, x, y, wres, seen), frames=2, io=io, storage=storage)
    limits = seen["data_limits"]
    assert (limits.x_min, limits.x_max) == pytest.approx((100.0, 200.0))
    assert plot.x_range == pytest.approx([100.0, 200.0]), "the same data keeps the zoom"


def test_new_data_refits_x():
    x, y, wres = _decay()
    plot, seen = ResidualPlot("refit"), {}
    io, storage = _frames(_draw_pair(plot, x, y, wres, seen, key=1))
    plot.x_range[:] = [10.0, 20.0]
    x2 = x * 2.0
    _frames(_draw_pair(plot, x2, y, wres, seen, key=2), frames=2, io=io, storage=storage)
    assert plot.x_range == pytest.approx([x2[0], x2[-1]])


def test_strip_range_is_symmetric_and_x_tick_labels_only_under_the_data(monkeypatch):
    x, y, wres = _decay()
    plot, seen = ResidualPlot("sym"), {}
    limits, axes = [], []
    real_limits, real_axes = implot.setup_axis_limits, implot.setup_axes

    def record_limits(axis, lo, hi, cond=implot.COND_ONCE):
        limits.append((axis, lo, hi, cond))
        return real_limits(axis, lo, hi, cond)

    def record_axes(x_label=None, y_label=None, x_flags=0, y_flags=0):
        axes.append((y_label, x_flags))
        return real_axes(x_label, y_label, x_flags, y_flags)

    monkeypatch.setattr(implot, "setup_axis_limits", record_limits)
    monkeypatch.setattr(implot, "setup_axes", record_axes)
    _frames(_draw_pair(plot, x, y, wres, seen), frames=1)
    (axis, lo, hi, cond), = [entry for entry in limits if entry[0] == implot.AXIS_Y1]
    assert lo == pytest.approx(-hi) and hi >= 9.0, (lo, hi)
    assert cond == implot.COND_ALWAYS, "the strip never auto-fits to one side"
    (strip_label, strip_flags), (data_label, data_flags) = axes
    assert strip_label is None and data_label == "c"  # "w.res." is written inside the strip
    assert strip_flags & implot.AXIS_FLAGS_NO_TICK_LABELS
    assert not data_flags & implot.AXIS_FLAGS_NO_TICK_LABELS
    assert not seen["data_x_axis"].flags & implot.AXIS_FLAGS_NO_TICK_LABELS


def test_zero_line_is_drawn_thick(monkeypatch):
    x, y, wres = _decay()
    plot, seen = ResidualPlot("zero"), {}
    styles, lines = [], []
    real_style, real_inf = implot.set_next_line_style, implot.plot_inf_lines

    def style(colour=None, weight=-1.0, dash=None):
        styles.append(weight)
        return real_style(colour, weight, dash)

    def inf(label, values, *a, **k):
        lines.append((label, list(np.ravel(values)), styles[-1] if styles else None))
        return real_inf(label, values, *a, **k)

    monkeypatch.setattr(implot, "set_next_line_style", style)
    monkeypatch.setattr(implot, "plot_inf_lines", inf)
    _frames(_draw_pair(plot, x, y, wres, seen), frames=1)
    assert lines and lines[-1][1] == [0.0]
    assert lines[-1][2] == ZERO_LINE_WIDTH >= 2.0


def test_concatenated_halves_keep_their_x():
    """VV | VH: each half's residuals at its own channels, NaN between the fitted windows."""
    n = 200
    x = np.arange(2 * n, dtype=float)
    wres = np.full(2 * n, np.nan)
    wres[20:150] = 1.0
    wres[n + 20 : n + 150] = -2.0
    plot, seen = ResidualPlot("vvvh"), {}
    y = np.ones(2 * n)
    _frames(_draw_pair(plot, x, y, wres, seen))
    assert plot.x_range == pytest.approx([0.0, 2 * n - 1.0])
    assert plot.reach == pytest.approx(symmetric_limit(wres))


def test_zero_line_takes_the_theme_text_colour():
    """Inside a frame the style's 0..255 text colour becomes the line's 0..1 RGBA."""
    from chisurf.emtk.residual_plot import zero_line_colour

    seen = {}

    def draw():
        seen["colour"] = zero_line_colour()
        seen["text"] = tuple(emtk.im.get_style().color(emtk.im.Col.TEXT))[:3]

    _frames(draw, frames=1)
    r, g, b, a = seen["colour"]
    assert all(0.0 <= c <= 1.0 for c in (r, g, b, a)) and a >= 0.8
    text = [c / 255.0 if max(seen["text"]) > 1 else c for c in seen["text"]]
    assert (r, g, b) == pytest.approx(tuple(text))


def test_a_title_does_not_eat_the_strip():
    """The title line is added on top: the strip's plotting area keeps its share of the pair."""
    x, y, wres = _decay()
    plot, seen = ResidualPlot("titled"), {}
    _frames(_draw_pair(plot, x, y, wres, seen, title="Decay and fit"))
    strip, data = plot.rects["wres"], plot.rects["data"]
    assert 0.17 < strip[3] / (strip[3] + data[3]) < 0.30


def test_the_strip_names_itself_in_its_corner_clear_of_the_tick_labels():
    """A vertical axis name ran into a short strip's tick labels; it sits inside the strip."""
    x, y, wres = _decay()
    plot, seen = ResidualPlot("corner"), {}
    io, storage = emtk.IO(), {}
    rec = None
    for _ in range(3):
        rec = RecordingPainter()
        with emtk.frame(rec, (0, 0, 640, 300), io=io, storage=storage):
            emtk.begin("w")
            _draw_pair(plot, x, y, wres, seen)()
            emtk.end()
    sx, sy, sw, sh = plot.rects["wres"]
    (lx, ly, lw, lh), = [t[:4] for t in rec.texts if t[5] == "w.res."]
    assert sx <= lx and lx + lw <= sx + sw and sy <= ly and ly + lh <= sy + sh
