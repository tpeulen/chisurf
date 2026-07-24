"""pyqtgraph implementation of the chiplot backend contract.

This is the **only** module in ChiSurf permitted to import ``pyqtgraph``. It
translates chiplot's renderer-neutral style/handle vocabulary into pyqtgraph
items and wraps them so they satisfy the
:mod:`chisurf.gui.chiplot.handles` protocols.

Swapping to a different renderer (e.g. an OpenGL backend) means writing a
sibling module with the same classes; no call site changes.
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from qtpy import QtCore, QtWidgets

from chisurf.gui.chiplot import handles as H
from chisurf.gui.chiplot import style as S
from chisurf.gui.chiplot.backends import base

# --------------------------------------------------------------------------
# style translation
# --------------------------------------------------------------------------

_QT_LINE_STYLE = {
    S.LineStyle.SOLID: QtCore.Qt.SolidLine,
    S.LineStyle.DASH: QtCore.Qt.DashLine,
    S.LineStyle.DOT: QtCore.Qt.DotLine,
    S.LineStyle.DASH_DOT: QtCore.Qt.DashDotLine,
    S.LineStyle.NONE: QtCore.Qt.NoPen,
}


def _pen(pen: S.Pen | None):
    """Translate a chiplot :class:`~chisurf.gui.chiplot.style.Pen` to a QPen.

    Parameters
    ----------
    pen : Pen or None
        ``None`` yields a no-line pen.
    """
    if pen is None or pen.style is S.LineStyle.NONE:
        return pg.mkPen(None)
    return pg.mkPen(
        color=pen.color.as_tuple(),
        width=pen.width,
        style=_QT_LINE_STYLE[pen.style],
        cosmetic=pen.cosmetic,
    )


def _brush(brush: S.Brush | None):
    """Translate a chiplot :class:`~chisurf.gui.chiplot.style.Brush` to a QBrush.

    Parameters
    ----------
    brush : Brush or None
        ``None`` yields no brush.
    """
    if brush is None:
        return pg.mkBrush(None)
    return pg.mkBrush(brush.color.as_tuple())


def _lut(cmap: S.Colormap | None):
    """Resolve a chiplot :class:`~chisurf.gui.chiplot.style.Colormap` to a LUT.

    Returns ``None`` if the colormap cannot be resolved by pyqtgraph.

    Parameters
    ----------
    cmap : Colormap or None
        The colormap reference to resolve; ``None`` yields ``None``.
    """
    if cmap is None:
        return None
    for source in (cmap.source, None):
        try:
            cm = pg.colormap.get(cmap.name, source=source) if source else pg.colormap.get(cmap.name)
            if cm is not None:
                return cm.getLookupTable(alpha=True)
        except Exception:
            continue
    return None


_QT_BUTTON = {
    QtCore.Qt.LeftButton: "left",
    QtCore.Qt.RightButton: "right",
    QtCore.Qt.MiddleButton: "middle",
}


# --------------------------------------------------------------------------
# handle wrappers
# --------------------------------------------------------------------------


class _Item:
    """Base wrapper giving a pyqtgraph item the chiplot :class:`Handle` API."""

    def __init__(self, native, plot_item: pg.PlotItem):
        self._native = native
        self._pi = plot_item

    @property
    def visible(self) -> bool:
        """Whether the item is drawn."""
        return bool(self._native.isVisible())

    @visible.setter
    def visible(self, value: bool) -> None:
        self._native.setVisible(bool(value))

    @property
    def z(self) -> float:
        """Stacking order; higher draws on top."""
        return float(self._native.zValue())

    @z.setter
    def z(self, value: float) -> None:
        self._native.setZValue(float(value))

    def remove(self) -> None:
        """Remove the item from its plot."""
        self._pi.removeItem(self._native)

    @property
    def native(self):
        """The wrapped pyqtgraph item."""
        return self._native


class _Curve(_Item):
    """Handle for a pyqtgraph ``PlotDataItem`` / ``PlotCurveItem``."""

    def set_data(self, x: np.ndarray, y: np.ndarray) -> None:
        """Replace the curve samples."""
        self._native.setData(np.asarray(x), np.asarray(y))


class _Scatter(_Item):
    """Handle for a pyqtgraph ``ScatterPlotItem``."""

    def set_data(self, x: np.ndarray, y: np.ndarray) -> None:
        """Replace the scatter positions."""
        self._native.setData(np.asarray(x), np.asarray(y))


class _Bars(_Item):
    """Handle for a pyqtgraph ``BarGraphItem``."""

    def set_data(self, x: np.ndarray, height: np.ndarray) -> None:
        """Replace bar positions/heights."""
        self._native.setOpts(x=np.asarray(x), height=np.asarray(height))


class _ErrorBars(_Item):
    """Handle for a pyqtgraph ``ErrorBarItem``."""

    def set_data(self, x, y, *, height=None, top=None, bottom=None) -> None:
        """Replace error-bar geometry."""
        kw = {"x": np.asarray(x), "y": np.asarray(y)}
        if height is not None:
            kw["height"] = np.asarray(height)
        if top is not None:
            kw["top"] = np.asarray(top)
        if bottom is not None:
            kw["bottom"] = np.asarray(bottom)
        self._native.setData(**kw)


class _Image(_Item):
    """Handle for a pyqtgraph ``ImageItem``."""

    def set_image(self, data: np.ndarray, *, levels=None) -> None:
        """Replace the image data."""
        self._native.setImage(np.asarray(data), autoLevels=levels is None)
        if levels is not None:
            self._native.setLevels(levels)

    def set_rect(self, x: float, y: float, w: float, h: float) -> None:
        """Place the image in data coordinates."""
        self._native.setRect(QtCore.QRectF(x, y, w, h))


class _Region(_Item):
    """Handle for a pyqtgraph ``LinearRegionItem``."""

    @property
    def bounds(self) -> tuple[float, float]:
        """The ``(low, high)`` edges of the region."""
        return tuple(self._native.getRegion())

    @bounds.setter
    def bounds(self, value: tuple[float, float]) -> None:
        self._native.setRegion(tuple(value))

    def on_change(self, callback, *, final: bool = True) -> None:
        """Fire ``callback(low, high)`` while/after the region is dragged."""
        sig = self._native.sigRegionChangeFinished if final else self._native.sigRegionChanged
        sig.connect(lambda item: callback(*item.getRegion()))


class _Marker(_Item):
    """Handle for a pyqtgraph ``InfiniteLine`` cursor."""

    @property
    def value(self) -> float:
        """The line position in data coordinates."""
        return float(self._native.value())

    @value.setter
    def value(self, value: float) -> None:
        self._native.setValue(float(value))

    def on_change(self, callback, *, final: bool = True) -> None:
        """Fire ``callback(pos)`` while/after the marker is dragged."""
        sig = self._native.sigPositionChangeFinished if final else self._native.sigDragged
        sig.connect(lambda item: callback(float(item.value())))


class _DraggableTextItem(pg.TextItem):
    """A ``TextItem`` the user can drag with the left mouse button."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setAcceptHoverEvents(True)
        self.setCursor(QtCore.Qt.OpenHandCursor)
        self._dragging = False
        self._offset = QtCore.QPointF(0, 0)

    def mousePressEvent(self, event):
        """Begin dragging on left-button press."""
        if event.button() == QtCore.Qt.LeftButton:
            self._dragging = True
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            self._offset = event.pos()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        """Reposition while the left button is held."""
        if self._dragging and event.buttons() & QtCore.Qt.LeftButton:
            self.setPos(self.mapToParent(event.pos() - self._offset))
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        """End dragging on left-button release."""
        if event.button() == QtCore.Qt.LeftButton:
            self._dragging = False
            self.setCursor(QtCore.Qt.OpenHandCursor)
            event.accept()
        else:
            event.ignore()


class _Text(_Item):
    """Handle for a pyqtgraph ``TextItem``."""

    @property
    def text(self) -> str:
        """The displayed string."""
        return self._native.toPlainText()

    @text.setter
    def text(self, value: str) -> None:
        self._native.setText(str(value))

    def set_position(self, x: float, y: float) -> None:
        """Move the label."""
        self._native.setPos(x, y)


# --------------------------------------------------------------------------
# canvas
# --------------------------------------------------------------------------


class _PgCanvas(base.Canvas):
    """A pyqtgraph-backed single plot panel."""

    def __init__(self, plot_item: pg.PlotItem, host: QtWidgets.QWidget):
        self._pi = plot_item
        self._host = host  # provides scene() and is the embeddable widget

    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable Qt widget."""
        return self._host

    # -- drawing --------------------------------------------------------
    def add_curve(self, x, y, *, pen, name=None, fill=None, step=False) -> H.Curve:
        """Draw a line/step curve."""
        kw = {"pen": _pen(pen)}
        if name is not None:
            kw["name"] = name
        if step:
            kw["stepMode"] = "center"
        if fill is not None:
            kw["fillLevel"] = 0.0
            kw["brush"] = _brush(fill)
        item = self._pi.plot(np.asarray(x), np.asarray(y), **kw)
        return _Curve(item, self._pi)

    def add_scatter(self, x, y, *, size, pen, brush, symbol, name=None) -> H.Scatter:
        """Draw a scatter cloud."""
        item = pg.ScatterPlotItem(
            x=np.asarray(x),
            y=np.asarray(y),
            size=size,
            pen=_pen(pen),
            brush=_brush(brush),
            symbol=symbol.value,
            name=name,
        )
        self._pi.addItem(item)
        return _Scatter(item, self._pi)

    def add_bars(self, x, height, *, width, pen, brush) -> H.Bars:
        """Draw a bar graph."""
        item = pg.BarGraphItem(
            x=np.asarray(x),
            height=np.asarray(height),
            width=width,
            pen=_pen(pen),
            brush=_brush(brush),
        )
        self._pi.addItem(item)
        return _Bars(item, self._pi)

    def add_errorbars(self, x, y, *, height, top, bottom, pen) -> H.ErrorBars:
        """Draw error bars."""
        kw = {"x": np.asarray(x), "y": np.asarray(y), "pen": _pen(pen)}
        if height is not None:
            kw["height"] = np.asarray(height)
        if top is not None:
            kw["top"] = np.asarray(top)
        if bottom is not None:
            kw["bottom"] = np.asarray(bottom)
        item = pg.ErrorBarItem(**kw)
        self._pi.addItem(item)
        return _ErrorBars(item, self._pi)

    def add_image(self, data, *, colormap, levels, rect) -> H.Image:
        """Draw an image/heatmap."""
        item = pg.ImageItem(np.asarray(data))
        lut = _lut(colormap)
        if lut is not None:
            item.setLookupTable(lut)
        if levels is not None:
            item.setLevels(levels)
        if rect is not None:
            item.setRect(QtCore.QRectF(*rect))
        self._pi.addItem(item)
        return _Image(item, self._pi)

    def add_region(self, bounds, *, orientation, movable, brush, pen) -> H.Region:
        """Draw a draggable interval selector."""
        kw = {
            "values": tuple(bounds),
            "orientation": orientation.value,
            "movable": movable,
        }
        if brush is not None:
            kw["brush"] = _brush(brush)
        if pen is not None:
            kw["pen"] = _pen(pen)
        item = pg.LinearRegionItem(**kw)
        self._pi.addItem(item)
        return _Region(item, self._pi)

    def add_marker(self, pos, *, orientation, movable, pen, label) -> H.Marker:
        """Draw a movable cursor line."""
        angle = 90 if orientation is H.Orientation.VERTICAL else 0
        item = pg.InfiniteLine(pos=pos, angle=angle, movable=movable, pen=_pen(pen), label=label)
        self._pi.addItem(item)
        return _Marker(item, self._pi)

    def add_text(self, text, pos, *, color, anchor, draggable) -> H.Text:
        """Draw a text label."""
        cls = _DraggableTextItem if draggable else pg.TextItem
        item = cls(text=text, color=color.as_tuple(), anchor=anchor)
        item.setPos(*pos)
        self._pi.addItem(item)
        return _Text(item, self._pi)

    def add_legend(self, *, offset=(30, 30)) -> None:
        """Enable a legend collecting named handles."""
        self._pi.addLegend(offset=offset)

    def readd(self, handle: H.Handle) -> None:
        """Re-attach a previously removed handle."""
        self._pi.addItem(handle.native)

    def remove(self, handle: H.Handle) -> None:
        """Remove a handle from this panel."""
        self._pi.removeItem(handle.native)

    def clear(self) -> None:
        """Remove every handle from this panel."""
        self._pi.clear()

    # -- axes / view ----------------------------------------------------
    def set_labels(self, *, left=None, bottom=None, right=None, top=None) -> None:
        """Set axis labels (unset axes unchanged)."""
        for side, txt in (("left", left), ("bottom", bottom), ("right", right), ("top", top)):
            if txt is not None:
                self._pi.setLabel(side, str(txt))

    def set_title(self, title) -> None:
        """Set the panel title."""
        self._pi.setTitle(title)

    def set_log(self, *, x=None, y=None) -> None:
        """Toggle logarithmic scaling per axis."""
        self._pi.setLogMode(x=x, y=y)

    def set_range(self, *, x=None, y=None, padding=None) -> None:
        """Set visible x/y range."""
        if x is not None:
            self._pi.setXRange(x[0], x[1], padding=padding)
        if y is not None:
            self._pi.setYRange(y[0], y[1], padding=padding)

    def get_range(self):
        """Return the current visible ``((x0, x1), (y0, y1))``."""
        (x0, x1), (y0, y1) = self._pi.getViewBox().viewRange()
        return (x0, x1), (y0, y1)

    def auto_range(self) -> None:
        """Fit the view to its contents once."""
        self._pi.getViewBox().autoRange()

    def enable_auto_range(self, *, x=True, y=True) -> None:
        """Keep the view fitted to contents as data changes."""
        vb = self._pi.getViewBox()
        vb.enableAutoRange(x=x, y=y)

    def set_grid(self, *, x=False, y=False, alpha=0.3) -> None:
        """Toggle axis grid lines."""
        self._pi.showGrid(x=x, y=y, alpha=alpha)

    def set_background(self, color) -> None:
        """Set the panel background color."""
        vb = self._pi.getViewBox()
        vb.setBackgroundColor(color.as_tuple() if color is not None else None)

    def set_aspect_locked(self, lock, ratio=1.0) -> None:
        """Lock the x/y pixel aspect ratio."""
        self._pi.getViewBox().setAspectLocked(lock, ratio)

    def invert_y(self, invert=True) -> None:
        """Invert the y-axis direction."""
        self._pi.getViewBox().invertY(invert)

    # -- events ---------------------------------------------------------
    def on_click(self, callback) -> None:
        """Register ``callback(x, y, button)`` for clicks."""

        def _handler(event):
            vb = self._pi.getViewBox()
            pt = vb.mapSceneToView(event.scenePos())
            callback(pt.x(), pt.y(), _QT_BUTTON.get(event.button(), "other"))

        self._host.scene().sigMouseClicked.connect(_handler)

    def on_mouse_move(self, callback) -> None:
        """Register ``callback(x, y)`` for pointer motion."""

        def _handler(pos):
            vb = self._pi.getViewBox()
            if self._host.scene().sceneRect().contains(pos):
                pt = vb.mapSceneToView(pos)
                callback(pt.x(), pt.y())

        self._host.scene().sigMouseMoved.connect(_handler)

    @property
    def native(self):
        """The wrapped pyqtgraph ``PlotItem``."""
        return self._pi


class _PgGrid(base.GridCanvas):
    """A pyqtgraph ``GraphicsLayoutWidget`` grid of panels."""

    def __init__(self, **opts):
        self._w = pg.GraphicsLayoutWidget(**opts)

    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable grid widget."""
        return self._w

    def add_panel(self, *, row=None, col=None, rowspan=1, colspan=1, title=None) -> base.Canvas:
        """Add and return a panel at the given cell."""
        pi = self._w.addPlot(row=row, col=col, rowspan=rowspan, colspan=colspan, title=title)
        return _PgCanvas(pi, self._w)

    def next_row(self) -> None:
        """Advance the implicit insertion cursor to the next row."""
        self._w.nextRow()

    @property
    def native(self):
        """The wrapped ``GraphicsLayoutWidget``."""
        return self._w


class PyQtGraphBackend(base.Backend):
    """chiplot backend rendering through pyqtgraph."""

    name = "pyqtgraph"

    def create_canvas(self, **opts) -> base.Canvas:
        """Create a single-panel canvas backed by a ``pg.PlotWidget``."""
        background = opts.pop("background", None)
        pw = pg.PlotWidget(**opts)
        if background is not None:
            pw.setBackground(background)
        return _PgCanvas(pw.getPlotItem(), pw)

    def create_grid(self, **opts) -> base.GridCanvas:
        """Create a multi-panel grid backed by a ``GraphicsLayoutWidget``."""
        return _PgGrid(**opts)

    def configure(self, **global_opts) -> None:
        """Apply process-wide pyqtgraph options."""
        pg.setConfigOptions(**global_opts)
