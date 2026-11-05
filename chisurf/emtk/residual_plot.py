"""Data with its weighted residuals: the one way a ChiSurf fit plot shows residuals.

The rule (OKF concept ``subsystems/chiplot.md``, "Residual strips"): the weighted residuals sit
in a strip **above** the data, about a fifth of the height, on **the same x-axis** -- the same
limits, zooming and panning together, the x tick labels only under the data -- so a deviation
is read straight down onto the part of the curve that causes it. The strip's y-range is
**always symmetric** about zero (:func:`symmetric_limit`), never auto-fitted to one side, and
zero is a **thick line**, so which way the model misses is visible at a glance.

Two drawing paths share the rule:

* immediate-mode tools (``emtk.implot``) draw the pair with :class:`ResidualPlot`;
* the fit windows' retained chiplot panels (``LinePlot``) take :func:`symmetric_limit`,
  :data:`ZERO_LINE_WIDTH` and :func:`zero_line_colour` from here.

Residuals of concatenated data (``VV | VH``) are passed on the data's own x (the residual of
channel *i* at the x of channel *i*), NaN where nothing was fitted -- a NaN is a gap in the line.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence

import numpy as np

from chisurf.core.plotting.residuals import symmetric_limit

__all__ = [
    "WRES_FRACTION",
    "ZERO_LINE_WIDTH",
    "ResidualPlot",
    "Residuals",
    "symmetric_limit",
    "zero_line_colour",
]

#: The strip's share of the pair's height (the rule says 20-25 %).
WRES_FRACTION = 0.22
#: Pixel width of the zero line: thick enough to read at a glance against the residual trace.
ZERO_LINE_WIDTH = 2.5


@dataclass(frozen=True)
class Residuals:
    """One residual trace of the strip.

    ``x`` is the x of the data the residuals belong to (same array, same units); ``y`` the
    weighted residuals, NaN where there are none. ``colour`` (RGBA 0..1 or 0..255, or ``None``
    for the next colour of the plot's cycle) usually repeats the colour of its data curve.
    """

    label: str
    x: Any
    y: Any
    colour: Any = None


def zero_line_colour() -> tuple:
    """The zero line's colour: the theme's text colour, so it reads on every background."""
    try:
        from emtk import im

        rgb = [float(c) for c in tuple(im.get_style().color(im.Col.TEXT))[:3]]
        if max(rgb) > 1.0:  # the style's colours are 0..255
            rgb = [c / 255.0 for c in rgb]
        return (rgb[0], rgb[1], rgb[2], 0.9)
    except Exception:  # noqa: BLE001 - no context yet (tests, the chiplot path)
        return (0.92, 0.92, 0.92, 0.9)


def _finite_extent(xs: Sequence[Any]) -> Optional[tuple]:
    values = [np.asarray(x, dtype=float).ravel() for x in xs if x is not None]
    values = [v[np.isfinite(v)] for v in values]
    values = [v for v in values if v.size]
    if not values:
        return None
    lo = float(min(v.min() for v in values))
    hi = float(max(v.max() for v in values))
    return (lo, hi) if hi > lo else (lo - 0.5, hi + 0.5)


class ResidualPlot:
    """A data plot with its weighted-residual strip above it (immediate mode, ``emtk.implot``).

    Keep one instance per plot (it holds the shared x range, so zoom and pan survive frames)
    and call :meth:`draw` every frame::

        self.decay_plot = ResidualPlot("decay")          # once
        ...
        def draw_data():
            implot.plot_line("Data", t, counts)
            implot.plot_line("Model", t, model)

        self.decay_plot.draw(
            draw_data,
            [Residuals("w.res.", t, wres)],
            x_extent=(t[0], t[-1]), key=id(result),
            x_label="Time (ns)", y_label="Counts", log_y=True,
        )

    Parameters
    ----------
    plot_id : str
        Unique id within the window (the two plots are ``##<id>_wres`` / ``##<id>_data``).
    fraction : float
        The strip's share of the height (:data:`WRES_FRACTION`).
    """

    def __init__(self, plot_id: str, *, fraction: float = WRES_FRACTION) -> None:
        self.plot_id = str(plot_id)
        self.fraction = float(fraction)
        #: The x range both plots are linked to (data units), updated in place by zoom/pan.
        self.x_range: list = [0.0, 1.0]
        #: The y half-height the strip was last drawn with (``-reach .. reach``).
        self.reach: float = 1.0
        self._key: Any = object()
        #: Screen rects ``(x, y, w, h)`` of the strip's and the data plot's plotting area.
        self.rects: dict = {}

    def reset_x(self, extent: Optional[tuple]) -> None:
        """Show *extent* (``(lo, hi)``) in both plots, e.g. after new data arrived."""
        if extent is not None:
            self.x_range[0], self.x_range[1] = float(extent[0]), float(extent[1])

    def draw(
        self,
        data: Callable[[], None],
        residuals: Sequence[Residuals],
        *,
        x_extent: Optional[tuple] = None,
        key: Any = None,
        size: tuple = (-1.0, -1.0),
        x_label: str = "",
        y_label: str = "",
        wres_label: str = "w.res.",
        title: Optional[str] = None,
        log_x: bool = False,
        log_y: bool = False,
        y_limits: Optional[tuple] = None,
        legend: Optional[int] = None,
        data_flags: int = 0,
        percentile: float = 100.0,
        minimum: float = 0.0,
        wres_tooltip: Optional[str] = None,
        fit_y: bool = True,
    ) -> bool:
        """Draw the strip and the data plot; ``True`` when the data plot was drawn.

        Parameters
        ----------
        data : callable
            Draws the data plot's items (lines, scatters, drag tools, hover handling); called
            between that plot's ``begin_plot`` and ``end_plot``, axes already set up.
        residuals : sequence of Residuals
            The traces of the strip, on the data's x.
        x_extent : (float, float), optional
            The x range to show when *key* changes (new data); by default the finite extent of
            the residuals' x.
        key : hashable, optional
            Identity of the shown data; a new key re-fits x to *x_extent*. By default the
            extent itself.
        size : (float, float)
            The pair's size, ``-1`` filling the available space.
        x_label, y_label, wres_label : str
            Axis names: x under the data plot only, y of the data; *wres_label* is written in
            the strip's top-left corner.
        title : str, optional
            The data plot's title, shown above the strip (``None``: no title).
        log_x, log_y : bool
            Log scales; x applies to both plots.
        y_limits : (float, float), optional
            The data plot's y range (``COND_ALWAYS``); ``None`` leaves it to the user / fit.
        legend : int, optional
            ``implot.LOCATION_*`` of the data plot's legend; ``None`` keeps the default.
        data_flags : int
            Extra ``implot.FLAGS_*`` for the data plot.
        percentile, minimum : float
            :func:`symmetric_limit`'s; the strip's range is ``-reach .. reach`` always.
        wres_tooltip : str, optional
            Hover text of the strip.
        fit_y : bool
            Fit the data plot's y to its items when *key* changes; ``False`` when *data* frames
            y itself (``setup_axis_limits`` before its first item).
        """
        from emtk import im, implot

        residuals = [r for r in residuals if r is not None]
        extent = x_extent if x_extent is not None else _finite_extent([r.x for r in residuals])
        token = extent if key is None else key
        refit = token != self._key
        if refit:
            self._key = token
            self.reset_x(extent)

        width, height = size
        avail_w, avail_h = im.get_content_region_avail()
        width = avail_w if width is None or width <= 0 else float(width)
        height = avail_h if height is None or height <= 0 else float(height)
        height = max(height, 140.0)
        spacing = float(im.get_style().item_spacing[1])
        # the title sits on the strip; its line is extra, so the strip's plotting area keeps
        # its share of the pair
        title_h = (im.get_text_line_height_with_spacing() + 4.0) if title else 0.0
        strip_h = max(48.0, (height - spacing - title_h) * self.fraction) + title_h
        data_h = max(80.0, height - spacing - strip_h)

        self.reach = symmetric_limit(
            [r.y for r in residuals], percentile=percentile, minimum=minimum
        )
        drawn = False
        aligned = implot.begin_aligned_plots(f"##{self.plot_id}_aligned")
        try:
            strip_title = (title or "") + f"##{self.plot_id}_wres"
            if implot.begin_plot(strip_title, (width, strip_h), implot.FLAGS_NO_LEGEND):
                # no axis name beside the strip: in a short strip a vertical one runs into the
                # tick labels, so it is written in the strip's top-left corner (below)
                implot.setup_axes(
                    None,
                    None,
                    implot.AXIS_FLAGS_NO_TICK_LABELS | implot.AXIS_FLAGS_NO_LABEL,
                    implot.AXIS_FLAGS_NO_LABEL,
                )
                implot.setup_axis_links(implot.AXIS_X1, self.x_range)
                if log_x:
                    implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
                implot.setup_axis_limits(
                    implot.AXIS_Y1, -self.reach, self.reach, implot.COND_ALWAYS
                )
                for trace in residuals:
                    if trace.colour is not None:
                        implot.set_next_line_style(trace.colour, 1.5)
                    implot.plot_line(
                        trace.label,
                        np.asarray(trace.x, dtype=float),
                        np.asarray(trace.y, dtype=float),
                    )
                # on top of the traces, so it stays visible where they crowd around zero
                implot.set_next_line_style(zero_line_colour(), ZERO_LINE_WIDTH)
                implot.plot_inf_lines(
                    "##zero", np.array([0.0]), flags=implot.INF_LINES_HORIZONTAL
                )
                self.rects["wres"] = (*implot.get_plot_pos(), *implot.get_plot_size())
                if wres_label:
                    corner = implot.get_plot_pos()
                    implot.get_plot_draw_list().add_text(
                        (corner[0] + 5.0, corner[1] + 2.0), zero_line_colour(), wres_label
                    )
                if wres_tooltip and implot.is_plot_hovered():
                    im.set_tooltip(wres_tooltip)
                implot.end_plot()
            data_id = f"##{self.plot_id}_data"
            if refit and fit_y and y_limits is None:
                implot.set_next_axis_to_fit(implot.AXIS_Y1)  # new data: its own y range
            if implot.begin_plot(data_id, (width, data_h), int(data_flags)):
                implot.setup_axes(x_label or None, y_label or None)
                implot.setup_axis_links(implot.AXIS_X1, self.x_range)
                if log_x:
                    implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
                if log_y:
                    implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
                if y_limits is not None:
                    implot.setup_axis_limits(
                        implot.AXIS_Y1, float(y_limits[0]), float(y_limits[1]), implot.COND_ALWAYS
                    )
                if legend is not None:
                    implot.setup_legend(legend)
                self.rects["data"] = (*implot.get_plot_pos(), *implot.get_plot_size())
                data()
                implot.end_plot()
                drawn = True
        finally:
            if aligned:
                implot.end_aligned_plots()
        return drawn
