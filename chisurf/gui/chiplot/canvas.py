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


class Plot(QtWidgets.QWidget):
    """A single plot panel with a verb-first drawing API.

    Parameters
    ----------
    parent : QWidget, optional
        Qt parent.
    title : str, optional
        Panel title.
    background : color-like, optional
        Background color.
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

    def __init__(self, parent=None, *, title: str | None = None, background=None, **backend_opts):
        super().__init__(parent)
        self._canvas = get_backend().create_canvas(**backend_opts)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._canvas.widget())
        if title is not None:
            self._canvas.set_title(title)
        if background is not None:
            self._canvas.set_background(S.to_color(background))
        self._canvas.on_click(lambda x, y, btn: self.clicked.emit(x, y) if btn == "left" else None)
        self._canvas.on_mouse_move(lambda x, y: self.mouse_moved.emit(x, y))

    # -- drawing --------------------------------------------------------
    def line(
        self, x, y, *, pen="w", width=None, style=None, name=None, fill=None, step=False
    ) -> H.Curve:
        """Draw a line (or step) curve.

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
        step : bool
            Draw as a centered step curve (histogram outline).

        Returns
        -------
        handles.Curve
        """
        overrides = {}
        if width is not None:
            overrides["width"] = width
        if style is not None:
            overrides["style"] = style
        return self._canvas.add_curve(
            np.asarray(x),
            np.asarray(y),
            pen=S.to_pen(pen, **overrides),
            name=name,
            fill=S.to_brush(fill) if fill is not None else None,
            step=step,
        )

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
        return self._canvas.add_scatter(
            np.asarray(x),
            np.asarray(y),
            size=size,
            pen=S.to_pen(pen) if pen is not None else None,
            brush=S.to_brush(brush) if brush is not None else None,
            symbol=symbol if isinstance(symbol, H.Symbol) else H.Symbol(symbol),
            name=name,
        )

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

    def errorbars(self, x, y, *, height=None, top=None, bottom=None, pen="w") -> H.ErrorBars:
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
        )

    def image(self, data, *, colormap=None, levels=None, rect=None) -> H.Image:
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

        Returns
        -------
        handles.Image
        """
        cmap = colormap
        if isinstance(cmap, str):
            cmap = S.colormap(cmap)
        return self._canvas.add_image(np.asarray(data), colormap=cmap, levels=levels, rect=rect)

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

    def text(self, text, pos, *, color="w", anchor=(0, 0), draggable=False) -> H.Text:
        """Add a text label in data coordinates.

        Parameters
        ----------
        text : str
            Label content.
        pos : tuple of float
            ``(x, y)`` anchor position.
        color : color-like
            Text color.
        anchor : tuple of float
            Text anchor within its bounding box (``(0, 0)`` = top-left).
        draggable : bool
            If ``True`` the label can be dragged with the mouse.

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

        Parameters
        ----------
        handle : handles.Handle
            The handle to remove from the panel.
        """
        self._canvas.remove(handle)

    def clear(self) -> None:
        """Remove every drawn handle from the panel."""
        self._canvas.clear()

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

    def invert_y(self, invert=True) -> Plot:
        """Invert the y-axis direction. Returns ``self``."""
        self._canvas.invert_y(invert)
        return self

    @property
    def canvas(self):
        """The backend :class:`~chisurf.gui.chiplot.backends.base.Canvas`."""
        return self._canvas

    @property
    def native(self):
        """The backend plot object (escape hatch; avoid in new code)."""
        return self._canvas.native


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

    def next_row(self) -> None:
        """Advance the implicit insertion cursor to the next row."""
        self._grid.next_row()

    @property
    def native(self):
        """The backend grid object (escape hatch; avoid in new code)."""
        return self._grid.native


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
        self._canvas.on_click(lambda x, y, btn: self.clicked.emit(x, y) if btn == "left" else None)
