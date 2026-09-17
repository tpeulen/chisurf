"""Minimal chiplot-backed shims for the small slice of the guiqwt API that a
couple of legacy chisurf plot widgets still use.

ChiSurf standardizes on the renderer-neutral :mod:`chisurf.gui.chiplot` seam;
this module lets ``global_tcspc`` and ``surfaceplot`` keep their old
``guiqwt`` / ``guidata`` call surface without a full rewrite, while drawing
through chiplot (no direct pyqtgraph). It reproduces only the methods those
widgets actually call:

- ``CurveDialog`` / ``ImageDialog`` -> a :class:`~chisurf.gui.chiplot.Plot` that
  also answers ``get_plot()`` (returning itself) plus ``add_item`` /
  ``do_autoscale`` / ``set_scales`` / ``set_titles`` / ``set_aspect_ratio``.
- ``make.curve`` / ``make.label`` / ``make.histogram`` / ``make.histogram2D`` /
  ``make.range`` -> lightweight adapter items that materialise a chiplot handle
  on ``attach`` and expose the ``set_data`` / ``set_hist_data`` /
  ``set_logscale`` / ``set_range`` / ``get_range`` methods the callers use.

It is intentionally not a general guiqwt emulation.
"""

from __future__ import annotations

import numpy as np

from chisurf.gui import chiplot as cp


class _PgPlot(cp.Plot):
    """A chiplot ``Plot`` exposing the handful of guiqwt plot methods used."""

    def __init__(self, *args, aspect_locked: bool = False, **kwargs):
        # guiqwt dialog kwargs (``edit``, ``toolbar``, …) are accepted and ignored.
        super().__init__()
        if aspect_locked:
            self.set_aspect_locked(True)

    # guiqwt: ``win.get_plot()`` returned the plot; here the widget is the plot.
    def get_plot(self) -> _PgPlot:
        return self

    def add_item(self, item) -> None:
        if item is None:
            return
        item.attach(self)

    def do_autoscale(self, *args, **kwargs) -> None:
        self.autoscale()

    def set_scales(self, xscale: str = "lin", yscale: str = "lin") -> None:
        self.set_log(x=(xscale == "log"), y=(yscale == "log"))

    def set_titles(self, ylabel: str | None = None, xlabel: str | None = None, **kwargs) -> None:
        if ylabel:
            self.set_labels(left=str(ylabel))
        if xlabel:
            self.set_labels(bottom=str(xlabel))

    def set_aspect_ratio(self, lock: bool = False, **kwargs) -> None:
        self.set_aspect_locked(bool(lock))


class _PgCurve:
    """A line curve; the chiplot handle is created when attached to a plot."""

    def __init__(self, color="w", linewidth: int = 2):
        self._color = color
        self._lw = linewidth
        self._x = np.asarray([], dtype=float)
        self._y = np.asarray([], dtype=float)
        self._handle = None

    def attach(self, plot: _PgPlot) -> None:
        self._handle = plot.line(self._x, self._y, pen=self._color, width=self._lw)

    def set_data(self, x, y) -> None:
        self._x = np.asarray(x, dtype=float)
        self._y = np.asarray(y, dtype=float)
        if self._handle is not None:
            self._handle.set_data(self._x, self._y)


class _PgLabel:
    """guiqwt legend-style label; rendered as the plot title (best effort)."""

    def __init__(self, text: str):
        self.text = str(text)

    def attach(self, plot: _PgPlot) -> None:
        try:
            plot.set_title(self.text)
        except Exception:
            pass


class _PgHistogram:
    """A filled step histogram; recomputed and redrawn on data/scale changes."""

    def __init__(self, color="w", bins: int = 50):
        self._color = color
        self._bins = bins
        self._log = False
        self._plot = None
        self._handle = None
        self._edges = None
        self._counts = None

    def attach(self, plot: _PgPlot) -> None:
        self._plot = plot
        self._redraw()

    def set_logscale(self, log: bool) -> None:
        self._log = bool(log)
        self._redraw()

    def set_hist_data(self, data) -> None:
        data = np.asarray(data, dtype=float)
        data = data[np.isfinite(data)]
        if data.size == 0:
            self._edges = self._counts = None
        else:
            counts, edges = np.histogram(data, bins=self._bins)
            if self._log:
                counts = np.log10(counts.astype(float) + 1.0)
            self._edges, self._counts = edges, counts.astype(float)
        self._redraw()

    def _redraw(self) -> None:
        if self._plot is None:
            return
        if self._handle is not None:
            self._plot.remove(self._handle)
            self._handle = None
        if self._edges is None:
            return
        # step=True (edges of len y+1) draws the histogram outline; fill shades it.
        self._handle = self._plot.line(
            self._edges,
            self._counts,
            pen=self._color,
            step=True,
            fill=self._color,
        )


class _PgHistogram2D:
    """2D histogram backed by a chiplot image."""

    def __init__(self, logscale: bool = True, bins=(50, 50)):
        self._log = logscale
        self._bins = bins
        self._cmap = None
        self._plot = None
        self._handle = None
        self._data = None

    def attach(self, plot: _PgPlot) -> None:
        self._plot = plot
        self._redraw()

    def set_color_map(self, name: str) -> None:
        self._cmap = name
        self._redraw()

    def set_bins(self, nx, ny) -> None:
        self._bins = (int(nx), int(ny))

    def set_interpolation(self, *args, **kwargs) -> None:
        pass

    def set_data(self, x, y) -> None:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        if x.size == 0 or y.size == 0:
            return
        hist, _xe, _ye = np.histogram2d(x, y, bins=self._bins)
        if self._log:
            hist = np.log10(hist + 1.0)
        self._data = hist
        self._redraw()

    def _redraw(self) -> None:
        if self._plot is None or self._data is None:
            return
        if self._handle is None:
            self._handle = self._plot.image(self._data, colormap=self._cmap)
        else:
            self._handle.set_image(self._data)


class _PgRange:
    """A draggable horizontal/vertical span selector."""

    def __init__(self, lower: float, upper: float):
        self._lower = lower
        self._upper = upper
        self._handle = None

    def attach(self, plot: _PgPlot) -> None:
        self._handle = plot.region((self._lower, self._upper))

    def set_range(self, lower: float, upper: float) -> None:
        self._lower, self._upper = lower, upper
        if self._handle is not None:
            self._handle.set_bounds(lower, upper)

    def get_range(self):
        if self._handle is not None:
            return self._handle.bounds
        return (self._lower, self._upper)


class _Make:
    """Drop-in for ``guiqwt.builder.make`` (only the used factory methods)."""

    @staticmethod
    def curve(x, y, color="w", linewidth: int = 2, **kwargs) -> _PgCurve:
        curve = _PgCurve(color=color, linewidth=linewidth)
        curve.set_data(x, y)
        return curve

    @staticmethod
    def label(text, *args, **kwargs) -> _PgLabel:
        return _PgLabel(text)

    @staticmethod
    def histogram(data, color="w", **kwargs) -> _PgHistogram:
        hist = _PgHistogram(color=color)
        data = np.asarray(data)
        if data.size > 0:
            hist.set_hist_data(data)
        return hist

    @staticmethod
    def histogram2D(x, y, logscale: bool = True, **kwargs) -> _PgHistogram2D:
        return _PgHistogram2D(logscale=logscale)

    @staticmethod
    def range(lower: float, upper: float) -> _PgRange:
        return _PgRange(lower, upper)


make = _Make()


def CurveDialog(*args, **kwargs) -> _PgPlot:  # noqa: N802 (guiqwt name)
    return _PgPlot()


def ImageDialog(*args, **kwargs) -> _PgPlot:  # noqa: N802 (guiqwt name)
    return _PgPlot(aspect_locked=False)
