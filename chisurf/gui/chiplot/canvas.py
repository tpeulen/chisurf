"""Public chiplot widgets: :class:`Plot` and :class:`Grid`.

These are the ergonomic, renderer-neutral front end callers use. Both are
``QWidget`` subclasses that embed the active backend's canvas, so they drop
straight into Qt layouts where a ``pg.PlotWidget`` used to go.

Design goals versus pyqtgraph call sites:

- **Verb-first drawing** — ``plot.line(x, y)``, ``plot.scatter(x, y)``,
  ``plot.region((a, b))`` — instead of constructing item classes and calling
  ``addItem``.
- **Color-likes everywhere** — pass ``"red"``, ``"#ff0000"``, ``(1.0, 0, 0)``
  or a :class:`~chisurf.gui.chiplot.style.Pen`; no ``mkPen`` ceremony.
- **Behaviour flags, not subclasses** — ``plot.text(..., draggable=True)``
  instead of subclassing ``TextItem``.
- **Backend-neutral events** — ``plot.clicked.connect(cb)`` (Qt signal in data
  coordinates) instead of reaching into ``scene().sigMouseClicked``.
"""

from __future__ import annotations

import numpy as np
from qtpy import QtCore, QtWidgets

from chisurf.gui.chiplot import handles as H
from chisurf.gui.chiplot import style as S
from chisurf.gui.chiplot.backends import get_backend

#: Sentinel for "argument not given", so an explicit ``None`` keeps its own
#: meaning (a *transparent* background, pyqtgraph's idiom) instead of being
#: indistinguishable from the default.
_UNSET = object()


class Plot(QtWidgets.QWidget):
    """A single plot panel with a verb-first drawing API.

    Parameters
    ----------
    parent : QWidget, optional
        Qt parent.
    title : str, optional
        Panel title.
    background : color-like, optional
        Background color of the whole panel widget (data rectangle *and* axis
        margins). An explicit ``None`` means transparent.
    **backend_opts
        Passed through to the backend canvas factory.

    Signals
    -------
    clicked(float, float)
        Emitted with the ``(x, y)`` data coordinates of a left click.
    mouse_moved(float, float)
        Emitted with the ``(x, y)`` data coordinates under the pointer.
    """

    clicked = QtCore.Signal(float, float)
    mouse_moved = QtCore.Signal(float, float)

    def __init__(
        self, parent=None, *, title: str | None = None, background=_UNSET, **backend_opts
    ):
        super().__init__(parent)
        self._canvas = get_backend().create_canvas(**backend_opts)
        # (name, handle) of exportable x/y series, for the CSV context action.
        self._series: list = []
        self._extra_menu_actions: list = []
        self._context_menu_enabled = True
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._canvas.widget())
        if title is not None:
            self._canvas.set_title(title)
        if background is not _UNSET:
            self._canvas.set_background(None if background is None else S.to_color(background))
        self._canvas.on_click(lambda x, y, btn: self.clicked.emit(x, y) if btn == "left" else None)
        self._canvas.on_mouse_move(lambda x, y: self.mouse_moved.emit(x, y))
        # If the backend already ships a rich menu (pyqtgraph: Export/CSV/image),
        # keep it for parity and inject custom actions into it; otherwise chiplot
        # builds its own menu via contextMenuEvent.
        self._native_menu = self._canvas.provides_native_menu()
        if self._native_menu:
            self._install_native_export_actions()

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
    ) -> H.Curve:
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
            sym = symbol if isinstance(symbol, H.Symbol) else H.Symbol(symbol)
        handle = self._canvas.add_curve(
            x,
            y,
            pen=S.to_pen(pen, **overrides),
            name=name,
            fill=S.to_brush(fill) if fill is not None else None,
            step=step,
            symbol=sym,
            symbol_size=symbol_size,
            symbol_brush=S.to_brush(symbol_brush) if symbol_brush is not None else None,
            symbol_pen=S.to_pen(symbol_pen) if symbol_pen is not None else None,
            skip_missing=skip_missing,
        )
        self._series.append((name or f"curve{len(self._series)}", handle))
        return handle

    def scatter(self, x, y, *, size=7.0, brush="w", pen=None, symbol="o", name=None) -> H.Scatter:
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
            pen=S.to_pen(pen) if pen is not None else None,
            brush=S.to_brush(brush) if brush is not None else None,
            symbol=symbol if isinstance(symbol, H.Symbol) else H.Symbol(symbol),
            name=name,
        )
        self._series.append((name or f"points{len(self._series)}", handle))
        return handle

    def bars(self, x, height, *, width=1.0, brush="w", pen=None) -> H.Bars:
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
            pen=S.to_pen(pen) if pen is not None else None,
            brush=S.to_brush(brush) if brush is not None else None,
        )

    def fill_between(self, lower: H.Curve, upper: H.Curve, *, brush="w") -> H.Handle:
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
        return self._canvas.add_fill_between(lower, upper, brush=S.to_brush(brush))

    def errorbars(
        self, x, y, *, height=None, top=None, bottom=None, pen="w", beam=None
    ) -> H.ErrorBars:
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
            pen=S.to_pen(pen),
            beam=beam,
        )

    def image(
        self, data, *, colormap=None, levels=None, rect=None, axis_order="row-major"
    ) -> H.Image:
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
        cmap = S.to_colormap(colormap)
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
    ) -> H.Roi:
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
            pen=S.to_pen(pen),
            movable=movable,
            rotatable=rotatable,
            points=points,
        )

    def region(
        self, bounds, *, orientation="vertical", movable=True, brush=None, pen=None
    ) -> H.Region:
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
            orientation=H.Orientation(orientation),
            movable=movable,
            brush=S.to_brush(brush) if brush is not None else None,
            pen=S.to_pen(pen) if pen is not None else None,
        )

    def vline(self, x, *, movable=False, pen="w", label=None) -> H.Marker:
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
            x, orientation=H.Orientation.VERTICAL, movable=movable, pen=S.to_pen(pen), label=label
        )

    def hline(self, y, *, movable=False, pen="w", label=None) -> H.Marker:
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
            y, orientation=H.Orientation.HORIZONTAL, movable=movable, pen=S.to_pen(pen), label=label
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
    ) -> H.Arrow:
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
            pen=S.to_pen(pen) if pen is not None else None,
            brush=S.to_brush(brush) if brush is not None else None,
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
    ) -> H.Text:
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

        Returns
        -------
        handles.Text
        """
        return self._canvas.add_text(
            str(text),
            tuple(pos),
            color=S.to_color(color),
            anchor=tuple(anchor),
            draggable=draggable,
            fill=S.to_brush(fill) if fill is not None else None,
            border=S.to_pen(border) if border is not None else None,
            anchored=anchored,
        )

    def legend(self, *, offset=(30, 30)) -> None:
        """Show a legend collecting the ``name=`` of drawn handles.

        Parameters
        ----------
        offset : tuple of int
            Pixel offset of the legend box from the top-left corner.
        """
        self._canvas.add_legend(offset=offset)

    def add(self, handle: H.Handle) -> None:
        """Re-attach a previously removed handle.

        Parameters
        ----------
        handle : handles.Handle
            A handle earlier removed from a plot.
        """
        self._canvas.readd(handle)

    def remove(self, handle: H.Handle) -> None:
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
    def set_context_menu_enabled(self, enabled: bool) -> Plot:
        """Enable/disable chiplot's right-click menu. Returns ``self``."""
        self._context_menu_enabled = bool(enabled)
        return self

    def set_menu_enabled(self, enabled: bool) -> Plot:
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

    def add_menu_action(self, label: str, callback) -> Plot:
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

    def _install_native_export_actions(self) -> None:
        """Add chiplot's CSV/image export entries to the backend's native menu."""
        self._canvas.add_menu_action("Export data as CSV…", self._on_export_csv)
        self._canvas.add_menu_action("Export image…", self._on_export_image)

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
        """Save the panel as an image (PNG/SVG via the backend, else a grab).

        Parameters
        ----------
        path : str
            Destination image path.
        width : int, optional
            Target pixel width (backend exporter only).
        """
        if not self._canvas.export_image(path, width=width):
            self._canvas.widget().grab().save(path)

    def contextMenuEvent(self, event):  # noqa: N802 (Qt override)
        """Show chiplot's right-click menu (export data/image, auto-range).

        Skipped when the backend already shows its own rich menu (pyqtgraph),
        so the two never double up.
        """
        if not self._context_menu_enabled or getattr(self, "_native_menu", False):
            event.ignore()
            return
        menu = QtWidgets.QMenu(self)
        menu.addAction("Export data as CSV…", self._on_export_csv)
        menu.addAction("Export image…", self._on_export_image)
        menu.addSeparator()
        menu.addAction("Auto-range", lambda: self.autoscale())
        if self._extra_menu_actions:
            menu.addSeparator()
            for label, cb in self._extra_menu_actions:
                menu.addAction(label, cb)
        menu.exec_(event.globalPos())

    def _on_export_csv(self):
        """File-dialog + write for the CSV export menu action."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export data as CSV", "", "CSV files (*.csv)"
        )
        if path:
            self.export_csv(path)

    def _on_export_image(self):
        """File-dialog + write for the image export menu action."""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export image", "", "Images (*.png *.svg *.jpg)"
        )
        if path:
            self.export_image(path)

    # -- axes / view ----------------------------------------------------
    def set_labels(self, *, left=None, bottom=None, right=None, top=None) -> Plot:
        """Set axis labels; unset axes are left unchanged. Returns ``self``."""
        self._canvas.set_labels(left=left, bottom=bottom, right=right, top=top)
        return self

    def set_title(self, title) -> Plot:
        """Set the panel title. Returns ``self``."""
        self._canvas.set_title(title)
        return self

    def set_log(self, *, x=None, y=None) -> Plot:
        """Toggle logarithmic scaling per axis. Returns ``self``."""
        self._canvas.set_log(x=x, y=y)
        return self

    def set_tick_spacing(self, side, *, major=None, minor=None) -> Plot:
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

    def on_range_changed(self, callback) -> Plot:
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

    def set_xlim(self, lo, hi, *, padding=None) -> Plot:
        """Set the visible x-range. Returns ``self``."""
        self._canvas.set_range(x=(lo, hi), padding=padding)
        return self

    def set_ylim(self, lo, hi, *, padding=None) -> Plot:
        """Set the visible y-range. Returns ``self``."""
        self._canvas.set_range(y=(lo, hi), padding=padding)
        return self

    def set_range(self, *, x=None, y=None, padding=None) -> Plot:
        """Set visible x and/or y range. Returns ``self``."""
        self._canvas.set_range(x=x, y=y, padding=padding)
        return self

    def get_range(self):
        """Return the current visible ``((x0, x1), (y0, y1))``."""
        return self._canvas.get_range()

    def autoscale(self, *, x=True, y=True, continuous=False) -> Plot:
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

    def grid(self, *, x=False, y=False, alpha=0.3) -> Plot:
        """Toggle axis grid lines. Returns ``self``."""
        self._canvas.set_grid(x=x, y=y, alpha=alpha)
        return self

    def set_background(self, color) -> Plot:
        """Set the panel background color. Returns ``self``."""
        self._canvas.set_background(S.to_color(color) if color is not None else None)
        return self

    def set_aspect_locked(self, lock=True, ratio=1.0) -> Plot:
        """Lock the x/y pixel aspect ratio. Returns ``self``."""
        self._canvas.set_aspect_locked(lock, ratio)
        return self

    def set_interactive(self, *, mouse: bool = True, menu: bool = True) -> Plot:
        """Enable/disable mouse pan-zoom and the right-click menu. Returns ``self``.

        A convenience for static preview plots (e.g. node thumbnails) that want
        neither pan/zoom nor a context menu.
        """
        self._canvas.set_interactive(mouse=mouse, menu=menu)
        return self

    def invert_y(self, invert=True) -> Plot:
        """Invert the y-axis direction. Returns ``self``."""
        self._canvas.invert_y(invert)
        return self

    def set_si_prefix(self, *, x: bool | None = None, y: bool | None = None) -> Plot:
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

    def set_axis_visible(self, *, left=None, bottom=None, right=None, top=None) -> Plot:
        """Show/hide individual axes. Only the given sides change. Returns ``self``.

        Example: ``plot.set_axis_visible(left=False, bottom=False)`` for a bare
        canvas (e.g. a network diagram).
        """
        for side, vis in (("left", left), ("bottom", bottom), ("right", right), ("top", top)):
            if vis is not None:
                self._canvas.set_axis_visible(side, bool(vis))
        return self

    def set_compact(self, compact: bool = True, *, font_size: int = 8) -> Plot:
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

    def link_x(self, other: Plot) -> Plot:
        """Link this panel's x-axis to ``other``'s so they pan/zoom together.

        Used for stacked diagnostic panels (e.g. residuals above the data) that
        must share a time axis. Returns ``self``.
        """
        self._canvas.link_x(other._canvas)
        return self

    def link_y(self, other: Plot) -> Plot:
        """Link this panel's y-axis to ``other``'s so they pan/zoom together. Returns ``self``."""
        self._canvas.link_y(other._canvas)
        return self

    def set_downsampling(self, *, auto: bool = True, mode: str = "peak") -> Plot:
        """Enable/disable automatic downsampling of dense curves on this panel.

        A renderer performance hint for very large series. ``mode`` selects
        the reduction strategy (``"peak"`` preserves extrema; ``"subsample"``
        takes evenly spaced points). Returns ``self``.
        """
        self._canvas.set_downsampling(auto=auto, mode=mode)
        return self

    def set_clip_to_view(self, clip: bool = True) -> Plot:
        """Hint the backend to skip drawing samples outside the visible range.

        A renderer performance hint for large series. Returns ``self``.
        """
        self._canvas.set_clip_to_view(clip)
        return self

    @property
    def canvas(self):
        """The backend :class:`~chisurf.gui.chiplot.backends.base.Canvas`."""
        return self._canvas

    @property
    def native(self):
        """The backend plot object (escape hatch; avoid in new code)."""
        return self._canvas.native

    def __getattr__(self, name: str):
        """Proxy unknown attributes to the native plot object, flagged.

        Only invoked when normal lookup fails, so it never shadows chiplot's own
        API. Lets a migrated ``Plot`` still answer pyqtgraph-only calls
        (``setLogMode``, ``getViewBox``, …) while recording each as a migration
        gap via :func:`~chisurf.gui.chiplot.passthrough_gaps`.

        Parameters
        ----------
        name : str
            Attribute not found on this :class:`Plot`.

        Two objects are consulted, in order: the backend's plot object (a
        pyqtgraph ``PlotItem``) and then the widget hosting it (a
        ``PlotWidget``). pyqtgraph splits its API across the two — ``setLogMode``
        and ``getViewBox`` live on the item, ``getPlotItem`` and ``plotItem``
        only on the widget — and a migrated call site that reaches through the
        widget-level half would otherwise get an ``AttributeError`` from a seam
        whose whole purpose is to keep working.

        Raises
        ------
        AttributeError
            During construction (before the canvas exists) or if neither the
            native plot object nor its host widget has ``name``.
        """
        if name.startswith("__") or name == "_canvas":
            raise AttributeError(name)
        from chisurf.gui.chiplot._passthrough import record_and_warn

        for target in (self._canvas.native, self._canvas.widget()):
            if hasattr(target, name):
                record_and_warn("Plot", name)
                return getattr(target, name)
        raise AttributeError(name)


class Grid(QtWidgets.QWidget):
    """A grid of :class:`Plot`-style panels sharing one widget.

    Replaces ``pg.GraphicsLayoutWidget``. Use :meth:`add_plot` to add panels.

    Parameters
    ----------
    parent : QWidget, optional
        Qt parent.
    **backend_opts
        Passed to the backend grid factory.
    """

    def __init__(self, parent=None, **backend_opts):
        super().__init__(parent)
        self._grid = get_backend().create_grid(**backend_opts)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._grid.widget())

    def add_plot(self, *, row=None, col=None, rowspan=1, colspan=1, title=None) -> PanelPlot:
        """Add and return a panel at the given grid cell.

        Parameters
        ----------
        row, col : int, optional
            Target cell (implicit next cell if omitted).
        rowspan, colspan : int
            Cell span.
        title : str, optional
            Panel title.

        Returns
        -------
        PanelPlot
        """
        canvas = self._grid.add_panel(
            row=row, col=col, rowspan=rowspan, colspan=colspan, title=title
        )
        return PanelPlot(canvas)

    def set_column_stretch(self, column: int, factor: float) -> None:
        """Set the relative width of a grid column.

        Panels in a grid share the width equally by default, which is wrong the
        moment one of them is a colour bar: it takes as much room as a plot and
        renders as an unreadable sliver of gradient.

        Parameters
        ----------
        column : int
            Column index.
        factor : float
            Relative width. Larger is wider; the factors are compared with each
            other, not with any absolute size.
        """
        self._grid.set_column_stretch(column, factor)

    def set_row_stretch(self, row: int, factor: float) -> None:
        """Set the relative height of a grid row.

        Parameters
        ----------
        row : int
            Row index.
        factor : float
            Relative height.
        """
        self._grid.set_row_stretch(row, factor)

    def add_colorbar(
        self, image: H.Image, *, colormap=None, row=None, col=None, rowspan=1, colspan=1
    ) -> H.ColorBar:
        """Add a colour bar with interactive level handles, bound to ``image``.

        Replaces pyqtgraph's ``HistogramLUTItem``: the bar shows the image's
        intensity histogram, its handles set the mapped level range, and its
        gradient sets the colormap of both bar and image.

        Parameters
        ----------
        image : handles.Image
            The image handle the bar drives (from :meth:`Plot.image`).
        colormap : colormap-like, optional
            Initial colormap (name or :class:`~chisurf.gui.chiplot.style.Colormap`).
        row, col : int, optional
            Target cell (implicit next cell if omitted).
        rowspan, colspan : int
            Cell span.

        Returns
        -------
        handles.ColorBar
        """
        return self._grid.add_colorbar(
            image,
            colormap=S.to_colormap(colormap),
            row=row,
            col=col,
            rowspan=rowspan,
            colspan=colspan,
        )

    def next_row(self) -> None:
        """Advance the implicit insertion cursor to the next row."""
        self._grid.next_row()

    def clear(self) -> None:
        """Remove every panel, and reset the insertion cursor to the first cell.

        Panels obtained from :meth:`add_plot` before this call are gone; a
        rebuild must ask for new ones.
        """
        self._grid.clear()

    @property
    def native(self):
        """The backend grid object (escape hatch; avoid in new code)."""
        return self._grid.native

    def __getattr__(self, name: str):
        """Proxy unknown attributes to the native grid widget, flagged.

        Gives pyqtgraph parity for ``GraphicsLayoutWidget`` methods chiplot does
        not model natively (``addItem``, ``ci``, …).

        Parameters
        ----------
        name : str
            Attribute not found on this :class:`Grid`.

        Raises
        ------
        AttributeError
            During construction or if the native grid also lacks ``name``.
        """
        if name.startswith("__") or name == "_grid":
            raise AttributeError(name)
        from chisurf.gui.chiplot._passthrough import record_and_warn

        native = self._grid.native
        if hasattr(native, name):
            record_and_warn("Grid", name)
            return getattr(native, name)
        raise AttributeError(name)


class VolumeView(QtWidgets.QWidget):
    """3-D volume viewer: orbit a translucent ``(nz, ny, nx)`` scalar volume.

    Where :class:`ImageView` shows one plane of a stack behind a frame slider,
    this renders the whole volume at once. Drops into a Qt layout like any
    widget.

    Parameters
    ----------
    parent : QWidget, optional
        Qt parent.
    **backend_opts
        Passed to the backend volume-view factory.
    """

    def __init__(self, parent=None, **backend_opts):
        super().__init__(parent)
        self._vv = get_backend().create_volume_view(**backend_opts)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._vv.widget())
        # A GL viewport has no content to derive a size hint from, so a
        # scroll area or a dock collapses it to zero height and renders
        # nothing at all -- with no error, and the data still arriving.
        self.setMinimumSize(240, 240)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)

    def set_volume(self, data, *, colormap="magma", threshold=0.0, gamma=1.0):
        """Show a ``(nz, ny, nx)`` scalar volume."""
        self._vv.set_volume(data, colormap=colormap, threshold=threshold,
                            gamma=gamma)

    def set_scale(self, sx=1.0, sy=1.0, sz=1.0):
        """Per-axis voxel scaling, for anisotropically sampled volumes."""
        self._vv.set_scale(sx, sy, sz)

    def set_vectors(self, segments, *, color=(1.0, 1.0, 1.0, 0.8), width=2.0):
        """Overlay line segments, ``(n, 2, 3)``; ``None`` clears them."""
        self._vv.set_vectors(segments, color=color, width=width)

    def set_camera(self, distance=None, elevation=None, azimuth=None):
        """Position the orbit camera."""
        self._vv.set_camera(distance=distance, elevation=elevation,
                            azimuth=azimuth)

    def clear(self):
        """Remove the volume."""
        self._vv.clear()

    @property
    def native(self):
        """The backend-specific view object (escape hatch)."""
        return self._vv.native


class ImageView(QtWidgets.QWidget):
    """Image viewer: image + intensity/LUT histogram + (3-D) frame slider.

    Replaces ``pg.ImageView``. Drops into a Qt layout like any widget. Overlays
    and ROIs attach to its internal view.

    Parameters
    ----------
    parent : QWidget, optional
        Qt parent.
    **backend_opts
        Passed to the backend image-view factory.

    Signals
    -------
    clicked(float, float)
        Emitted with the ``(x, y)`` image coordinates of a click.
    """

    clicked = QtCore.Signal(float, float)
    #: Emitted with a :class:`chisurf.core.roi.PickedSpot` for each pick, whether
    #: or not the fit converged — a refusal carries its reason and is worth
    #: showing, where a silently dropped click is not.
    picked = QtCore.Signal(object)

    def __init__(self, parent=None, **backend_opts):
        super().__init__(parent)
        self._iv = get_backend().create_image_view(**backend_opts)
        self._picking = False
        self._pick_fit = "gaussian"
        self._pick_window = 9
        self._pick_image = None
        self._last_image = None
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._iv.widget())
        self._iv.on_click(lambda x, y: self.clicked.emit(x, y))

    def set_image(self, data, *, auto_levels=True, axes=None) -> None:
        """Show a 2-D image or a 3-D ``(t, y, x)`` stack.

        Parameters
        ----------
        data : array-like
            2-D image or 3-D stack.
        auto_levels : bool
            Auto-scale the intensity range to the data.
        axes : dict, optional
            Dimension map for stacks, e.g. ``{"t": 0, "y": 1, "x": 2}``.
        """
        data = np.asarray(data)
        # Kept so picking has something to fit against without the caller
        # having to hand the same array over twice.
        self._last_image = data
        self._iv.set_image(data, auto_levels=auto_levels, axes=axes)

    def set_colormap(self, name, source="matplotlib") -> None:
        """Apply a named colormap.

        Parameters
        ----------
        name : str
            Colormap identifier (e.g. ``"viridis"``, ``"CET-L4"``).
        source : str
            Namespace hint for the backend.
        """
        self._iv.set_colormap(name, source)

    def clear(self) -> None:
        """Clear the image and overlays."""
        self._iv.clear()

    def set_histogram_width(self, width) -> None:
        """Constrain (int) or free (``None``) the LUT histogram panel width."""
        self._iv.set_histogram_width(width)

    def set_interactive(self, *, mouse=True, menu=True) -> None:
        """Toggle view pan/zoom (``mouse``) and the right-click menu."""
        self._iv.set_interactive(mouse=mouse, menu=menu)

    def add_overlay(self, data, *, colormap=None) -> H.Image:
        """Overlay a second image on the view.

        Parameters
        ----------
        data : array-like
            Overlay image (typically RGBA with transparency).
        colormap : str or style.Colormap, optional
            Colormap for grayscale overlays.

        Returns
        -------
        handles.Image
        """
        cmap = colormap
        if isinstance(cmap, str):
            cmap = S.colormap(cmap)
        return self._iv.add_overlay(np.asarray(data), colormap=cmap)

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
        angle=0.0,
    ) -> H.Roi:
        """Add a region-of-interest shape over the image.

        Parameters
        ----------
        kind : str
            ``"rect"``, ``"circle"``, ``"ellipse"`` or ``"polygon"``. The last
            two exist because the ROI subsystem has an ellipse and a polygon
            region and, until they could be drawn, no GUI could produce one.
        pos : tuple of float
            Lower-left corner in image coordinates.
        size : tuple of float
            ``(w, h)`` in image coordinates.
        pen : pen-like
            Outline style.
        movable : bool
            Whether the user can drag/resize it.
        rotatable : bool
            Whether a rectangle ROI can be rotated (ignored for the others).
        points : sequence of (float, float), optional
            Vertices for ``kind="polygon"``; a polygon is defined by these, not
            by a corner and a size. Without them the polygon starts as the box
            described by *pos* and *size*.
        angle : float, optional
            Rotation of an ellipse, in **radians**, about its own centre —
            the unit :class:`chisurf.core.roi.EllipseROI` carries.

        Returns
        -------
        handles.Roi
        """
        return self._iv.add_roi(
            kind=kind,
            pos=tuple(pos),
            size=tuple(size),
            pen=S.to_pen(pen),
            movable=movable,
            rotatable=rotatable,
            points=points,
            angle=np.degrees(float(angle)),
        )

    def add_region(self, region, *, pen="y", movable=False, name: str = "") -> H.Roi:
        """Draw a :class:`chisurf.core.roi.ROI` over the image.

        The shape-agnostic form of :meth:`add_roi`. Every caller that had a
        region and wanted it on screen was converting it to ``kind``/``pos``/
        ``size`` by hand, differently, and getting the ellipse's radius-versus-
        diameter convention wrong in at least two places. A region knows what
        shape it is; this asks it.

        Parameters
        ----------
        region : chisurf.core.roi.ROI
            Rectangle, ellipse/circle or polygon. A mask-backed region has no
            analytic outline and raises — draw it as an overlay instead.
        pen : pen-like
            Outline style.
        movable : bool
            Whether the user can drag/resize it. Default is **not**: a region
            drawn from a measurement is a result, and dragging one would claim
            to edit something the analysis owns.
        name : str, optional
            Unused by the backend; accepted so a caller can keep its own
            bookkeeping in one call.

        Returns
        -------
        handles.Roi

        Raises
        ------
        TypeError
            For a region with no analytic outline, naming the alternative.
        """
        from chisurf.core.roi import EllipseROI, PolygonROI, RectangleROI

        if isinstance(region, RectangleROI):
            x0, y0, x1, y1 = region.bounds()
            return self.add_roi(kind="rect", pos=(x0, y0), size=(x1 - x0, y1 - y0),
                                pen=pen, movable=movable)
        if isinstance(region, EllipseROI):
            # pos/size are the bounding box, so the radii double. Getting this
            # wrong draws an ellipse half the size of the region it describes,
            # which looks plausible on every screenshot.
            return self.add_roi(
                kind="ellipse",
                pos=(region.cx - region.rx, region.cy - region.ry),
                size=(2.0 * region.rx, 2.0 * region.ry),
                pen=pen, movable=movable, angle=region.angle,
            )
        if isinstance(region, PolygonROI):
            return self.add_roi(kind="polygon", points=[tuple(v) for v in region.vertices],
                                pen=pen, movable=movable)
        raise TypeError(
            f"{type(region).__name__} has no analytic outline to draw; "
            "show it with add_overlay(region.to_mask(shape)) instead"
        )

    def enable_picking(self, image_source=None, *, fit: str = "gaussian",
                       window: int = 9) -> None:
        """Turn clicks into picked regions.

        The third way a region gets made — beside a batch detector and a drawn
        shape — offered here because it is a *gesture*, and a gesture belongs to
        the thing being clicked. Before this, every tool that wanted it reached
        past the plotting seam for the click and re-implemented the fit.

        The click is a **seed, not the answer**: it lands a pixel or two off
        centre, and a region built on it inherits that as a biased centroid.
        With ``fit="gaussian"`` the click selects a window, the brightest pixel
        in it seeds a 2-D Gaussian, and the fit decides where the spot is and
        how wide it is (:func:`chisurf.core.roi.fit_gaussian_spot`). A fit that
        does not converge emits a :class:`~chisurf.core.roi.PickedSpot` with
        ``success`` false and a reason, rather than a region placed where
        nothing was found.

        Parameters
        ----------
        image_source : callable, optional
            Returns the 2-D array to fit against. Defaults to whatever was last
            passed to :meth:`set_image`, which is right whenever the canvas is
            showing the data rather than a rendering of it.
        fit : str, optional
            ``"gaussian"`` to refine the click, or ``"none"`` to take it as-is
            (for a canvas whose pixels are not a picture of anything fittable).
        window : int, optional
            Side of the square the fit sees.

        Notes
        -----
        Connect to :attr:`picked` to receive each pick.
        """
        self._pick_fit = str(fit)
        self._pick_window = int(window)
        self._pick_image = image_source
        if not self._picking:
            self._picking = True
            self.clicked.connect(self._on_pick_click)

    def _on_pick_click(self, x: float, y: float) -> None:
        """Turn one click into a pick and emit it."""
        from chisurf.core.roi import PickedSpot, fit_gaussian_spot

        image = self._pick_image() if callable(self._pick_image) else self._last_image
        if image is None:
            return
        if self._pick_fit == "none":
            self.picked.emit(PickedSpot(y=float(y), x=float(x), success=True))
            return
        self.picked.emit(
            fit_gaussian_spot(np.asarray(image), y, x, window=self._pick_window)
        )

    @property
    def native(self):
        """The backend image-view object (escape hatch; avoid in new code)."""
        return self._iv.native

    def __getattr__(self, name: str):
        """Proxy unknown attributes to the native image view, flagged.

        Parameters
        ----------
        name : str
            Attribute not found on this :class:`ImageView`.

        Raises
        ------
        AttributeError
            During construction or if the native image view also lacks ``name``.
        """
        if name.startswith("__") or name == "_iv":
            raise AttributeError(name)
        from chisurf.gui.chiplot._passthrough import record_and_warn

        native = self._iv.native
        if hasattr(native, name):
            record_and_warn("ImageView", name)
            return getattr(native, name)
        raise AttributeError(name)


class PanelPlot(Plot):
    """A :class:`Plot` bound to an existing grid-panel canvas.

    Constructed by :meth:`Grid.add_plot`; not instantiated directly. It shares
    :class:`Plot`'s full drawing/axis API but is not a standalone top-level
    widget (its canvas already lives inside a :class:`Grid`).
    """

    def __init__(self, canvas):
        # Bypass Plot.__init__ (which would create a fresh top-level canvas);
        # a panel is a QObject only for signal support and wraps an existing canvas.
        QtWidgets.QWidget.__init__(self)
        self._canvas = canvas
        self._series = []
        self._extra_menu_actions = []
        # A panel is not a standalone widget, so chiplot's contextMenuEvent never
        # fires here — keep the backend's own menu for grid panels.
        self._context_menu_enabled = False
        self._native_menu = self._canvas.provides_native_menu()
        if self._native_menu:
            self._install_native_export_actions()
        self._canvas.on_click(lambda x, y, btn: self.clicked.emit(x, y) if btn == "left" else None)
