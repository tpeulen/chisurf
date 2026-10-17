"""The toolkit-free chiplot panel: :class:`PlotAPI` and :class:`Panel`.

``PlotAPI`` is the verb-first drawing, axis and export API every chiplot panel
shares; :class:`Panel` is that API over an emtk canvas with no widget behind it,
for surfaces that draw panels as emtk controls (a fit window's pages). Nothing
here imports a toolkit: an emtk surface draws a panel as a control.

Design goals versus pyqtgraph call sites:

- **Verb-first drawing** — ``plot.line(x, y)``, ``plot.scatter(x, y)``,
  ``plot.region((a, b))`` — instead of constructing item classes and calling
  ``addItem``.
- **Color-likes everywhere** — pass ``"red"``, ``"#ff0000"``, ``(1.0, 0, 0)``
  or a :class:`~chisurf.chiplot.style.Pen`; no ``mkPen`` ceremony.
- **Behaviour flags, not subclasses** — ``plot.text(..., draggable=True)``
  instead of subclassing ``TextItem``.
- **Backend-neutral events** — ``panel.clicked.connect(cb)`` (data
  coordinates) instead of reaching into a renderer's scene.
"""

from __future__ import annotations

from typing import Any, TypeVar

import numpy as np

from chisurf.chiplot.handles import (
    Arrow,
    Bars,
    ColorBar,
    Curve,
    ErrorBars,
    Handle,
    Image,
    Marker,
    Orientation,
    Region,
    Roi,
    Scatter,
    Symbol,
    Text,
)
from chisurf.chiplot.style import to_brush, to_color, to_colormap, to_pen

#: Sentinel for "argument not given", so an explicit ``None`` keeps its own
#: meaning (a *transparent* background, pyqtgraph's idiom) instead of being
#: indistinguishable from the default.
_UNSET = object()

_P = TypeVar("_P", bound="PlotAPI")


class PlotAPI:
    """The drawing, axis and export API of a chiplot panel, toolkit-free.

    Everything here talks to the backend canvas (``self._canvas``) only. It is
    shared by :class:`Panel`, which is the canvas alone, for a surface that
    draws it as a control (the fit window's emtk surface).
    """

    # Set by the concrete class (``Plot``, ``Panel``, ``PanelPlot``).
    _canvas: Any
    _series: list[tuple[str, Any]]
    _native_menu: bool
    _extra_menu_actions: list[Any]

    # -- drawing --------------------------------------------------------
    def line(
        self,
        x,
        y,
        *,
        pen="w",
        width=None,
        style=None,
        name=None,
        fill=None,
        step=False,
        symbol=None,
        symbol_size=7.0,
        symbol_brush=None,
        symbol_pen=None,
        skip_missing=True,
        max_points=None,
    ) -> Curve:
        """Draw a line (or step) curve, optionally with point markers.

        Parameters
        ----------
        x, y : array-like
            Sample coordinates.
        pen : pen-like
            Line color/style (``"red"``, ``(1, 0, 0)``, a :class:`style.Pen`).
        width : float, optional
            Line width override.
        style : str, optional
            Dash pattern (``"solid"``, ``"dash"``, ``"dot"``, ``"dash_dot"``).
        name : str, optional
            Legend label.
        fill : brush-like, optional
            Fill to the baseline under the curve.
        step : bool or str
            Draw as a step curve (histogram outline). ``True`` uses centered
            bins (requires ``len(x) == len(y) + 1``); the equal-length modes
            ``"left"``/``"right"``/``"center"`` may be passed as strings.
        symbol : str or handles.Symbol, optional
            If given, draw a marker at each point (``"o"``, ``"s"``, ``"x"``, …).
        symbol_size : float
            Marker size in pixels (when ``symbol`` is set).
        symbol_brush : brush-like, optional
            Marker fill.
        symbol_pen : pen-like, optional
            Marker outline.
        skip_missing : bool
            Break the line at non-finite samples (the default) instead of
            drawing a segment straight across them. A masked-out range is
            usually written as NaN and is meant to read as a gap.
        max_points : int, optional
            Thin the curve to about this many samples before drawing it, with
            :func:`chisurf.core.fio.decimate.thin_for_plot` -- min/max per bin,
            so a burst or a dip in a time-ordered trace survives. Opt-in and
            off by default: an already-aggregated curve (a histogram, a
            correlation) is small and must not be touched, and a *stepped*
            curve carries bin edges whose length relationship to ``y`` thinning
            would break, so it is left alone there too. Use it for a raw
            per-photon series; for a plot holding several such curves, split
            the budget with
            :func:`chisurf.core.fio.decimate.per_curve_budget` first.

        Returns
        -------
        handles.Curve
        """
        x = np.asarray(x)
        y = np.asarray(y)
        if max_points and not step and x.size == y.size and x.size > max_points:
            from chisurf.core.fio.decimate import thin_for_plot

            x, y = thin_for_plot(x, y, max_points=int(max_points))
        overrides = {}
        if width is not None:
            overrides["width"] = width
        if style is not None:
            overrides["style"] = style
        sym = None
        if symbol is not None:
            sym = symbol if isinstance(symbol, Symbol) else Symbol(symbol)
        handle = self._canvas.add_curve(
            x,
            y,
            pen=to_pen(pen, **overrides),
            name=name,
            fill=to_brush(fill) if fill is not None else None,
            step=step,
            symbol=sym,
            symbol_size=symbol_size,
            symbol_brush=to_brush(symbol_brush) if symbol_brush is not None else None,
            symbol_pen=to_pen(symbol_pen) if symbol_pen is not None else None,
            skip_missing=skip_missing,
        )
        self._series.append((name or f"curve{len(self._series)}", handle))
        return handle

    def scatter(self, x, y, *, size=7.0, brush="w", pen=None, symbol="o", name=None) -> Scatter:
        """Draw a scatter cloud.

        Parameters
        ----------
        x, y : array-like
            Point coordinates.
        size : float
            Marker size in pixels.
        brush : brush-like
            Marker fill.
        pen : pen-like, optional
            Marker outline (``None`` = no outline).
        symbol : str or handles.Symbol
            Marker shape (``"o"``, ``"s"``, ``"t"``, ``"d"``, ``"+"``, ``"x"``).
        name : str, optional
            Legend label.

        Returns
        -------
        handles.Scatter
        """
        handle = self._canvas.add_scatter(
            np.asarray(x),
            np.asarray(y),
            size=size,
            pen=to_pen(pen) if pen is not None else None,
            brush=to_brush(brush) if brush is not None else None,
            symbol=symbol if isinstance(symbol, Symbol) else Symbol(symbol),
            name=name,
        )
        self._series.append((name or f"points{len(self._series)}", handle))
        return handle

    def bars(self, x, height, *, width=1.0, brush="w", pen=None) -> Bars:
        """Draw a bar graph.

        Parameters
        ----------
        x : array-like
            Bar center x-coordinates.
        height : array-like
            Bar heights.
        width : float
            Bar width in data units.
        brush : brush-like
            Bar fill.
        pen : pen-like, optional
            Bar outline.

        Returns
        -------
        handles.Bars
        """
        return self._canvas.add_bars(
            np.asarray(x),
            np.asarray(height),
            width=width,
            pen=to_pen(pen) if pen is not None else None,
            brush=to_brush(brush) if brush is not None else None,
        )

    def fill_between(self, lower: Curve, upper: Curve, *, brush="w") -> Handle:
        """Fill the area between two curves (e.g. a confidence band).

        Parameters
        ----------
        lower, upper : handles.Curve
            The two curve handles bounding the filled region. The fill tracks
            them, so updating their data updates the band.
        brush : brush-like
            Fill color (typically translucent).

        Returns
        -------
        handles.Handle
        """
        return self._canvas.add_fill_between(lower, upper, brush=to_brush(brush))

    def errorbars(
        self, x, y, *, height=None, top=None, bottom=None, pen="w", beam=None
    ) -> ErrorBars:
        """Draw error bars.

        Parameters
        ----------
        x, y : array-like
            Anchor positions.
        height : array-like, optional
            Total symmetric height (mutually exclusive with ``top``/``bottom``).
        top, bottom : array-like, optional
            Asymmetric extents.
        pen : pen-like
            Bar color/style.
        beam : float, optional
            Width of the end caps in data units.

        Returns
        -------
        handles.ErrorBars
        """
        return self._canvas.add_errorbars(
            np.asarray(x),
            np.asarray(y),
            height=None if height is None else np.asarray(height),
            top=None if top is None else np.asarray(top),
            bottom=None if bottom is None else np.asarray(bottom),
            pen=to_pen(pen),
            beam=beam,
        )

    def image(
        self, data, *, colormap=None, levels=None, rect=None, axis_order="row-major"
    ) -> Image:
        """Draw a 2-D image / heatmap.

        Parameters
        ----------
        data : array-like
            2-D (grayscale) or 3-D (RGB/RGBA) array.
        colormap : str or style.Colormap, optional
            Colormap for grayscale data.
        levels : tuple of float, optional
            ``(min, max)`` mapped to the colormap ends.
        rect : tuple of float, optional
            ``(x, y, w, h)`` placement in data coordinates.
        axis_order : str
            ``"row-major"`` (default) or ``"col-major"`` for the data layout.

        Returns
        -------
        handles.Image
        """
        cmap = to_colormap(colormap)
        return self._canvas.add_image(
            np.asarray(data), colormap=cmap, levels=levels, rect=rect, axis_order=axis_order
        )

    def add_roi(
        self,
        *,
        kind="rect",
        pos=(0.0, 0.0),
        size=(10.0, 10.0),
        pen="y",
        movable=True,
        rotatable=False,
        points=None,
    ) -> Roi:
        """Add a region-of-interest shape over the plot.

        The same shapes as :meth:`ImageView.add_roi`, on a *data* plane: a gate
        on a joint intensity histogram, a cursor round a phasor cluster, a box
        on an E–S plot. A region carries no axes, so one overlay serves both —
        which is what lets the shared region editor gate scattered data and
        restrict an image with the same object.

        Parameters
        ----------
        kind : str
            ``"rect"``, ``"circle"``, ``"ellipse"`` or ``"polygon"``.
        pos, size : tuple of float
            Corner and extent in data coordinates.
        pen : pen-like
            Outline style.
        movable : bool
            Whether the user can drag/resize it.
        rotatable : bool
            Whether a rectangle may be rotated.
        points : sequence of (float, float), optional
            Vertices for ``kind="polygon"``.

        Returns
        -------
        handles.Roi
        """
        return self._canvas.add_roi(
            kind=kind,
            pos=tuple(pos),
            size=tuple(size),
            pen=to_pen(pen),
            movable=movable,
            rotatable=rotatable,
            points=points,
        )

    def region(
        self, bounds, *, orientation="vertical", movable=True, brush=None, pen=None
    ) -> Region:
        """Add a draggable interval selector.

        Parameters
        ----------
        bounds : tuple of float
            Initial ``(low, high)`` edges.
        orientation : str
            ``"vertical"`` (selects an x-interval) or ``"horizontal"``.
        movable : bool
            Whether the user can drag it.
        brush : brush-like, optional
            Fill of the band.
        pen : pen-like, optional
            Edge line style.

        Returns
        -------
        handles.Region
        """
        return self._canvas.add_region(
            tuple(bounds),
            orientation=Orientation(orientation),
            movable=movable,
            brush=to_brush(brush) if brush is not None else None,
            pen=to_pen(pen) if pen is not None else None,
        )

    def vline(self, x, *, movable=False, pen="w", label=None) -> Marker:
        """Add a vertical cursor line.

        Parameters
        ----------
        x : float
            Initial position.
        movable : bool
            Whether the user can drag it.
        pen : pen-like
            Line style.
        label : str, optional
            Attached label text.

        Returns
        -------
        handles.Marker
        """
        return self._canvas.add_marker(
            x, orientation=Orientation.VERTICAL, movable=movable, pen=to_pen(pen), label=label
        )

    def hline(self, y, *, movable=False, pen="w", label=None) -> Marker:
        """Add a horizontal cursor line.

        Parameters
        ----------
        y : float
            Initial position.
        movable : bool
            Whether the user can drag it.
        pen : pen-like
            Line style.
        label : str, optional
            Attached label text.

        Returns
        -------
        handles.Marker
        """
        return self._canvas.add_marker(
            y, orientation=Orientation.HORIZONTAL, movable=movable, pen=to_pen(pen), label=label
        )

    def arrow(
        self,
        x,
        y,
        *,
        angle=0.0,
        size=20.0,
        tip_angle=25.0,
        head_width=None,
        tail_length=None,
        tail_width=3.0,
        pen=None,
        brush="w",
    ) -> Arrow:
        """Add a scale-invariant arrow head at a data coordinate.

        Parameters
        ----------
        x, y : float
            Position of the arrow *tip*, in data coordinates.
        angle : float
            Direction the tip faces, in degrees counter-clockwise from ``+x`` —
            i.e. ``degrees(arctan2(dy, dx))`` for an edge running ``(x0, y0)`` →
            ``(x, y)``. The backend converts to its own convention.
        size : float
            Length of the head from tip to base, in pixels.
        tip_angle : float
            Opening angle of the tip in degrees; smaller is sharper. Ignored
            when ``head_width`` is given.
        head_width : float, optional
            Width of the head at its base, in pixels (overrides ``tip_angle``).
        tail_length : float, optional
            Length of a tail drawn behind the head, in pixels. ``None`` (default)
            draws the head alone — the usual choice when the edge itself is
            already drawn as a line.
        tail_width : float
            Width of that tail, in pixels.
        pen : pen-like, optional
            Outline of the arrow (``None`` = no outline).
        brush : brush-like, optional
            Fill of the arrow.

        Returns
        -------
        handles.Arrow

        Notes
        -----
        Sizes are in pixels, so the arrow keeps its size as the view zooms.
        """
        return self._canvas.add_arrow(
            (float(x), float(y)),
            angle=float(angle),
            size=float(size),
            tip_angle=float(tip_angle),
            head_width=head_width,
            tail_length=tail_length,
            tail_width=float(tail_width),
            pen=to_pen(pen) if pen is not None else None,
            brush=to_brush(brush) if brush is not None else None,
        )

    def text(
        self,
        text,
        pos,
        *,
        color="w",
        anchor=(0, 0),
        draggable=False,
        fill=None,
        border=None,
        anchored=False,
        themed=False,
    ) -> Text:
        """Add a text label.

        Parameters
        ----------
        text : str
            Label content.
        pos : tuple of float
            ``(x, y)`` anchor position. A data coordinate normally; a pixel
            offset from the panel's top-left when ``anchored`` is ``True``.
        color : color-like
            Text color.
        anchor : tuple of float
            Text anchor within its bounding box (``(0, 0)`` = top-left).
        draggable : bool
            If ``True`` the label can be dragged with the mouse.
        fill : brush-like, optional
            Background fill for the label box (``None`` = transparent).
        border : pen-like, optional
            Border pen for the label box (``None`` = no border).
        anchored : bool
            If ``True`` the label is pinned to the panel in screen space and
            does not move or rescale with the data (for fixed overlays such as a
            fit-quality readout); ``pos`` is then a pixel offset. If ``False``
            (default) the label lives at a data coordinate.
        themed : bool
            If ``True`` the label is a box in the window theme's colours (text,
            fill and border follow a light or dark theme, :mod:`emtk.theme`);
            *color*, *fill* and *border* are then not used.

        Returns
        -------
        handles.Text
        """
        return self._canvas.add_text(
            str(text),
            tuple(pos),
            color=to_color(color),
            anchor=tuple(anchor),
            draggable=draggable,
            fill=to_brush(fill) if fill is not None else None,
            border=to_pen(border) if border is not None else None,
            anchored=anchored,
            themed=themed,
        )

    def legend(self, *, offset=(30, 30)) -> None:
        """Show a legend collecting the ``name=`` of drawn handles.

        Parameters
        ----------
        offset : tuple of int
            Pixel offset of the legend box from the top-left corner.
        """
        self._canvas.add_legend(offset=offset)

    def hide_legend(self) -> None:
        """Stop showing the legend (:meth:`legend` shows it again)."""
        self._canvas.remove_legend()

    def add(self, handle: Handle) -> None:
        """Re-attach a previously removed handle.

        Parameters
        ----------
        handle : handles.Handle
            A handle earlier removed from a plot.
        """
        self._canvas.readd(handle)

    def remove(self, handle: Handle) -> None:
        """Remove a handle.

        Also drops it from the exportable-series list, so a removed curve stops
        showing up in the CSV export (and stops being kept alive by the plot).

        Parameters
        ----------
        handle : handles.Handle
            The handle to remove from the panel.
        """
        self._canvas.remove(handle)
        self._series = [entry for entry in self._series if entry[1] is not handle]

    def clear(self) -> None:
        """Remove every drawn handle from the panel."""
        self._series.clear()
        self._canvas.clear()

    def series(self) -> list:
        """The drawn line and scatter series, as ``(name, handle)`` pairs.

        What the plot shows, asked without reaching into a backend's own
        objects; ``handle.get_data()`` returns each series' ``(x, y)``.
        """
        return list(self._series)

    # -- context menu / export ------------------------------------------
    def set_context_menu_enabled(self: _P, enabled: bool) -> _P:
        """Enable/disable chiplot's right-click menu. Returns ``self``."""
        self._context_menu_enabled = bool(enabled)
        return self

    def set_menu_enabled(self: _P, enabled: bool) -> _P:
        """Enable/disable the right-click menu. Returns ``self``.

        The backend's own menu where it has one (pyqtgraph), chiplot's menu
        otherwise -- whichever a right-click would show.
        """
        if self._native_menu:
            self._canvas.set_menu_enabled(bool(enabled))
        else:
            self._context_menu_enabled = bool(enabled)
        return self

    def menu_enabled(self) -> bool:
        """Whether the right-click menu is currently offered.

        The read side of :meth:`set_menu_enabled` — ask this rather than
        reaching for the renderer's own spelling through the seam.
        """
        if self._native_menu:
            return bool(self._canvas.menu_enabled())
        return self._context_menu_enabled

    def add_menu_action(self: _P, label: str, callback) -> _P:
        """Add a custom entry to the right-click menu. Returns ``self``.

        Works whether the menu is the backend's native one (pyqtgraph) or
        chiplot's own fallback.

        Parameters
        ----------
        label : str
            Menu text.
        callback : callable
            Invoked (no args) when the entry is chosen.
        """
        self._extra_menu_actions.append((label, callback))
        if getattr(self, "_native_menu", False):
            self._canvas.add_menu_action(label, callback)
        return self

    def export_csv(self, path: str) -> None:
        """Write every drawn line/scatter series to a CSV file.

        Columns are ``<name> x`` / ``<name> y`` per series, padded to the
        longest series with blanks.

        Parameters
        ----------
        path : str
            Destination ``.csv`` path.
        """
        import csv

        cols: list[tuple[str, np.ndarray]] = []
        for name, handle in self._series:
            getter = getattr(handle, "get_data", None)
            if getter is None:
                continue
            try:
                x, y = getter()
            except Exception:
                continue
            if x is None or y is None:
                continue
            cols.append((f"{name} x", np.asarray(x)))
            cols.append((f"{name} y", np.asarray(y)))
        n = max((c.size for _, c in cols), default=0)
        with open(path, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([h for h, _ in cols])
            for i in range(n):
                w.writerow(["" if i >= c.size else c[i] for _, c in cols])

    def export_image(self, path: str, *, width: int | None = None) -> None:
        """Save the panel as an image, drawn on emtk's CPU rasteriser.

        Parameters
        ----------
        path : str
            Destination image path; the suffix picks the format (PNG, JPEG, ...).
        width : int, optional
            Target pixel width; the picture, text included, is scaled to it.

        Raises
        ------
        OSError
            When the backend could not write the file.
        """
        if not self._canvas.export_image(path, width=width):
            raise OSError(f"chiplot: the panel could not be exported to {path}")

    def _repr_png_(self) -> bytes | None:
        """The panel as PNG bytes: how the console (and a notebook) shows a plot.

        Returns
        -------
        bytes or None
            ``None`` when the panel cannot be drawn here.
        """
        import os
        import tempfile

        handle, path = tempfile.mkstemp(suffix=".png", prefix="chiplot-")
        os.close(handle)
        try:
            self.export_image(path)
            with open(path, "rb") as stream:
                return stream.read() or None
        finally:
            os.unlink(path)

    # -- axes / view ----------------------------------------------------
    def set_labels(
        self: _P,
        *,
        left=None,
        bottom=None,
        right=None,
        top=None,
        left_units: str | None = None,
        bottom_units: str | None = None,
        right_units: str | None = None,
        top_units: str | None = None,
    ) -> _P:
        """Set axis text and units independently. Returns ``self``.

        ``None`` preserves existing text or units; ``""`` clears that field.
        Units describe the supplied data without converting it. SI tick display
        scaling is controlled separately by :meth:`set_si_prefix`.
        """
        self._canvas.set_labels(
            left=left,
            bottom=bottom,
            right=right,
            top=top,
            left_units=left_units,
            bottom_units=bottom_units,
            right_units=right_units,
            top_units=top_units,
        )
        return self

    def set_title(self: _P, title) -> _P:
        """Set the panel title. Returns ``self``."""
        self._canvas.set_title(title)
        return self

    def set_log(self: _P, *, x=None, y=None) -> _P:
        """Toggle logarithmic scaling per axis. Returns ``self``."""
        self._canvas.set_log(x=x, y=y)
        return self

    def set_tick_spacing(self: _P, side, *, major=None, minor=None) -> _P:
        """Fix the tick interval on one axis, or restore automatic spacing.

        Parameters
        ----------
        side : str
            ``"bottom"``, ``"left"``, ``"top"`` or ``"right"``.
        major, minor : float, optional
            Interval between labelled and unlabelled ticks, in axis units --
            decades on a log axis, so ``major=1`` labels once per decade.
            Passing neither restores automatic spacing.

        Returns
        -------
        Plot
            ``self``.
        """
        self._canvas.set_tick_spacing(side, major=major, minor=minor)
        return self

    def on_range_changed(self: _P, callback) -> _P:
        """Call ``callback(x_range, y_range)`` whenever the view is panned or zoomed.

        Parameters
        ----------
        callback : callable
            Receives two ``(low, high)`` tuples in axis units.

        Returns
        -------
        Plot
            ``self``.
        """
        self._canvas.on_range_changed(callback)
        return self

    def set_xlim(self: _P, lo, hi, *, padding=None) -> _P:
        """Set the visible x-range. Returns ``self``."""
        self._canvas.set_range(x=(lo, hi), padding=padding)
        return self

    def set_ylim(self: _P, lo, hi, *, padding=None) -> _P:
        """Set the visible y-range. Returns ``self``."""
        self._canvas.set_range(y=(lo, hi), padding=padding)
        return self

    def set_range(self: _P, *, x=None, y=None, padding=None) -> _P:
        """Set visible x and/or y range. Returns ``self``."""
        self._canvas.set_range(x=x, y=y, padding=padding)
        return self

    def get_range(self):
        """Return the current visible ``((x0, x1), (y0, y1))``."""
        return self._canvas.get_range()

    def is_auto_range(self) -> tuple[bool, bool]:
        """Return whether x and y still follow the data.

        ``False`` for an axis whose range was set or that the user zoomed or
        panned; a saved view restores exactly those axes.
        """
        return self._canvas.is_auto_range()

    def set_auto_range_button(self: _P, shown: bool = True) -> _P:
        """Show (default) or never show the "A" auto-range button. Returns ``self``.

        Every panel has it: while an axis is not auto-ranged -- the user panned,
        zoomed or wheeled, or a caller set a range -- a small "A" sits in the
        lower-left of the plot area, and clicking it fits the view to the data
        again (as pyqtgraph's plots do). Turn it off only for a panel whose view
        must stay where the code put it, such as a fixed-scale reference axis.
        """
        self._canvas.set_auto_range_button(shown)
        return self

    def autoscale(self: _P, *, x=True, y=True, continuous=False) -> _P:
        """Fit the view to its contents. Returns ``self``.

        Parameters
        ----------
        x, y : bool
            Which axes to autoscale.
        continuous : bool
            If ``True`` keep autoscaling as data changes; else fit once now.
        """
        if continuous:
            self._canvas.enable_auto_range(x=x, y=y)
        else:
            self._canvas.auto_range()
        return self

    def grid(self: _P, *, x=False, y=False, alpha=0.3) -> _P:
        """Toggle axis grid lines. Returns ``self``."""
        self._canvas.set_grid(x=x, y=y, alpha=alpha)
        return self

    def set_background(self: _P, color) -> _P:
        """Set the panel background color. Returns ``self``."""
        self._canvas.set_background(to_color(color) if color is not None else None)
        return self

    def set_aspect_locked(self: _P, lock=True, ratio=1.0) -> _P:
        """Lock the x/y pixel aspect ratio. Returns ``self``."""
        self._canvas.set_aspect_locked(lock, ratio)
        return self

    def set_interactive(self: _P, *, mouse: bool = True, menu: bool = True) -> _P:
        """Enable/disable mouse pan-zoom and the right-click menu. Returns ``self``.

        A convenience for static preview plots (e.g. node thumbnails) that want
        neither pan/zoom nor a context menu.
        """
        self._canvas.set_interactive(mouse=mouse, menu=menu)
        # A backend with no menu of its own leaves it to chiplot's: honour the flag there too,
        # or a "static preview" plot still pops a context menu on right-click.
        self.set_menu_enabled(menu)
        return self

    def invert_y(self: _P, invert=True) -> _P:
        """Invert the y-axis direction. Returns ``self``."""
        self._canvas.invert_y(invert)
        return self

    def set_si_prefix(self: _P, *, x: bool | None = None, y: bool | None = None) -> _P:
        """Enable or disable an axis's automatic SI prefix.

        A renderer will happily relabel a 0-to-1 axis as "(x0.001)" with ticks
        running to 400. That is correct arithmetic and unreadable for a quantity —
        a probability, an efficiency, a ratio — that has no unit to prefix.

        Parameters
        ----------
        x, y : bool, optional
            Whether the bottom / left axis may use an SI prefix. ``None`` leaves
            that axis alone.

        Returns
        -------
        Plot
            Self, for chaining.
        """
        self._canvas.set_si_prefix(x=x, y=y)
        return self

    def set_axis_visible(self: _P, *, left=None, bottom=None, right=None, top=None) -> _P:
        """Show/hide individual axes. Only the given sides change. Returns ``self``.

        Example: ``plot.set_axis_visible(left=False, bottom=False)`` for a bare
        canvas (e.g. a network diagram).
        """
        for side, vis in (("left", left), ("bottom", bottom), ("right", right), ("top", top)):
            if vis is not None:
                self._canvas.set_axis_visible(side, bool(vis))
        return self

    def set_axis_style(self: _P, *, line=None, text=None) -> _P:
        """Colour the axis lines (``line``) and the tick/label text (``text``).

        Colours take any spelling :func:`~chisurf.chiplot.style.to_pen`
        accepts (name, ``"#rrggbb"``, RGB tuple). Only the given parts change.
        Returns ``self``.
        """
        self._canvas.set_axis_style(line=line, text=text)
        return self

    def set_tick_labels(self: _P, side, ticks) -> _P:
        """Replace the numeric labels of one axis by ``[(position, text), ...]``.

        Use it for categorical axes (detector names under bars). ``ticks=None``
        restores numeric labels. Returns ``self``.
        """
        self._canvas.set_tick_labels(side, None if ticks is None else list(ticks))
        return self

    def set_legend_style(self: _P, *, text=None) -> _P:
        """Colour the legend text. Returns ``self``."""
        self._canvas.set_legend_style(text=text)
        return self

    def set_compact(self: _P, compact: bool = True, *, font_size: int = 8) -> _P:
        """Shrink the panel's chrome so a small panel is mostly data.

        Margins, tick length, tick-label offset, the view's default padding and
        the tick font are one intent — "this panel is a strip, not a figure" —
        and setting them one at a time is what sends a call site through
        ``getPlotItem()`` into the backend.

        Parameters
        ----------
        compact : bool
            ``False`` restores the ordinary chrome.
        font_size : int
            Tick-label point size while compact.

        Returns
        -------
        Plot
            ``self``.
        """
        self._canvas.set_compact(compact, font_size=font_size)
        return self

    def link_x(self: _P, other: PlotAPI) -> _P:
        """Link this panel's x-axis to ``other``'s so they pan/zoom together.

        Used for stacked diagnostic panels (e.g. residuals above the data) that
        must share a time axis. Returns ``self``.
        """
        self._canvas.link_x(other._canvas)
        return self

    def link_y(self: _P, other: PlotAPI) -> _P:
        """Link this panel's y-axis to ``other``'s so they pan/zoom together. Returns ``self``."""
        self._canvas.link_y(other._canvas)
        return self

    def set_downsampling(self: _P, *, auto: bool = True, mode: str = "peak") -> _P:
        """Enable/disable automatic downsampling of dense curves on this panel.

        A renderer performance hint for very large series. ``mode`` selects
        the reduction strategy (``"peak"`` preserves extrema; ``"subsample"``
        takes evenly spaced points). Returns ``self``.
        """
        self._canvas.set_downsampling(auto=auto, mode=mode)
        return self

    def set_clip_to_view(self: _P, clip: bool = True) -> _P:
        """Hint the backend to skip drawing samples outside the visible range.

        A renderer performance hint for large series. Returns ``self``.
        """
        self._canvas.set_clip_to_view(clip)
        return self

    @property
    def canvas(self):
        """The backend :class:`~chisurf.chiplot.backends.base.Canvas`."""
        return self._canvas

    @property
    def native(self):
        """The backend plot object (escape hatch; avoid in new code)."""
        return self._canvas.native


class _Hook:
    """``connect``/``disconnect``/``emit`` for a :class:`Panel` (no toolkit object behind it)."""

    def __init__(self) -> None:
        self._slots: list = []

    def connect(self, slot) -> None:
        self._slots.append(slot)

    def disconnect(self, slot=None) -> None:
        self._slots = [] if slot is None else [s for s in self._slots if s is not slot]

    def emit(self, *args) -> None:
        for slot in list(self._slots):
            slot(*args)


class Panel(PlotAPI):
    """A chiplot panel that is not a widget: the emtk canvas and the plot API.

    For a surface that draws panels as emtk controls (a fit window page): the
    same ``line``/``set_labels``/``region``/... calls as every chiplot panel,
    and no widget behind it. ``clicked`` and ``mouse_moved`` connect like
    signals. :meth:`control` is what to draw.

    Parameters
    ----------
    title : str, optional
        Panel title.
    background : color-like, optional
        Panel background; an explicit ``None`` is transparent.
    **backend_opts
        Passed to the emtk canvas.
    """

    def __init__(self, *, title: str | None = None, background=_UNSET, **backend_opts):
        from chisurf.chiplot.backends.emtk_backend import EmtkCanvas

        self._canvas = EmtkCanvas(**backend_opts)
        self._series: list = []
        self._extra_menu_actions: list = []
        self._context_menu_enabled = True
        self._native_menu = False
        self.clicked = _Hook()
        self.mouse_moved = _Hook()
        if title is not None:
            self._canvas.set_title(title)
        if background is not _UNSET:
            self._canvas.set_background(None if background is None else to_color(background))
        self._canvas.on_click(lambda x, y, btn: self.clicked.emit(x, y) if btn == "left" else None)
        self._canvas.on_mouse_move(lambda x, y: self.mouse_moved.emit(x, y))

    @classmethod
    def of(cls, canvas) -> Panel:
        """The panel API over an existing canvas (a :class:`PanelGrid` cell)."""
        panel = cls.__new__(cls)
        panel._canvas = canvas
        panel._series = []
        panel._extra_menu_actions = []
        panel._context_menu_enabled = True
        panel._native_menu = False
        panel.clicked = _Hook()
        panel.mouse_moved = _Hook()
        canvas.on_click(lambda x, y, btn: panel.clicked.emit(x, y) if btn == "left" else None)
        canvas.on_mouse_move(lambda x, y: panel.mouse_moved.emit(x, y))
        return panel

    def control(self):
        """The emtk control that draws this panel (its canvas)."""
        return self._canvas


class PanelGrid:
    """Several :class:`Panel` s (and colour ramps) in a grid, drawn as one emtk control.

    Rows, columns, spans and stretch factors as a grid layout has them; a colour
    ramp's column stays narrow. :meth:`control` is what a surface draws.

    Parameters
    ----------
    **backend_opts
        Passed to every panel's canvas.
    """

    def __init__(self, **backend_opts):
        from chisurf.chiplot.backends import get_backend

        self._grid = get_backend().create_grid(**backend_opts)

    def add_plot(self, *, row=None, col=None, rowspan=1, colspan=1, title=None) -> Panel:
        """Add a panel at the given cell (or the next one) and return it."""
        canvas = self._grid.add_panel(
            row=row, col=col, rowspan=rowspan, colspan=colspan, title=title
        )
        return Panel.of(canvas)

    def add_colorbar(
        self, image: Image, *, colormap=None, row=None, col=None, rowspan=1, colspan=1
    ) -> ColorBar:
        """Add a colour ramp with draggable levels bound to ``image``."""
        return self._grid.add_colorbar(
            image,
            colormap=to_colormap(colormap),
            row=row,
            col=col,
            rowspan=rowspan,
            colspan=colspan,
        )

    def next_row(self) -> None:
        """Move the insertion cursor to the start of the next row."""
        self._grid.next_row()

    def clear(self) -> None:
        """Remove every panel and ramp; panels handed out before are gone."""
        self._grid.clear()

    def set_column_stretch(self, column: int, factor: float) -> None:
        """Set the relative width of a column (a colour ramp's column is kept narrow anyway)."""
        self._grid.set_column_stretch(column, factor)

    def set_row_stretch(self, row: int, factor: float) -> None:
        """Set the relative height of a row."""
        self._grid.set_row_stretch(row, factor)

    def control(self):
        """The emtk control that lays out and draws the grid."""
        return self._grid

    @property
    def native(self):
        """The backend grid object (escape hatch; avoid in new code)."""
        return self._grid.native
