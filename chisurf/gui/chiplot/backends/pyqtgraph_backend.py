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


def _apply_autorange_compat() -> None:
    """Restore ``PlotWidget.autoRangeEnabled`` dropped in pyqtgraph >= 0.14.

    pyqtgraph moved ``autoRangeEnabled`` from ``PlotWidget`` onto ``ViewBox``.
    Code (and headless harnesses) that call it on the widget otherwise hit a
    swallowed ``AttributeError`` and silently take a degraded path. Applied when
    this backend module loads, so it covers full GUI startup, tests, and scripts
    alike. Idempotent: returns early once the attribute already exists.
    """
    try:
        from pyqtgraph.widgets.PlotWidget import PlotWidget as _PW
    except Exception:
        return
    if hasattr(_PW, "autoRangeEnabled"):
        return

    def _compat(self):
        vb = None
        try:
            vb = self.getViewBox()
        except Exception:
            vb = None
        if vb is not None and hasattr(vb, "autoRangeEnabled"):
            try:
                return vb.autoRangeEnabled()
            except Exception:
                pass
        return (True, True)

    try:
        _PW.autoRangeEnabled = _compat
    except Exception:
        pass


_apply_autorange_compat()


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

    def hide(self) -> None:
        """Hide the item."""
        self._native.setVisible(False)

    def show(self) -> None:
        """Show the item."""
        self._native.setVisible(True)

    def remove(self) -> None:
        """Remove the item from its plot."""
        self._pi.removeItem(self._native)

    @property
    def native(self):
        """The wrapped pyqtgraph item."""
        return self._native

    def __getattr__(self, name: str):
        """Proxy unknown handle attributes to the native pyqtgraph item, flagged.

        Guarantees pyqtgraph parity: any item method chiplot does not expose
        natively (``clear``, ``setExportHint``, ``setSymbol``, …) still works via
        the underlying item and is recorded as a migration gap.

        Parameters
        ----------
        name : str
            Attribute not found on this handle.

        Raises
        ------
        AttributeError
            During construction (before ``_native`` exists) or if the native
            item also lacks ``name``.
        """
        if name.startswith("__") or name in ("_native", "_pi"):
            raise AttributeError(name)
        native = object.__getattribute__(self, "_native")
        if hasattr(native, name):
            from chisurf.gui.chiplot._passthrough import record_and_warn

            record_and_warn(type(self).__name__.lstrip("_"), name)
            return getattr(native, name)
        raise AttributeError(name)

    def __setattr__(self, name, value):
        """Forward attribute *assignment* to the native item for parity.

        Wrapper internals (``_native``/``_pi``) and chiplot's own properties stay
        on the wrapper; a name the native item already exposes is set on the
        native item (so ``item.attr = x`` behaves as in pyqtgraph); anything else
        is set on the wrapper (consistent read-back via normal lookup).
        """
        if name.startswith("_") or isinstance(getattr(type(self), name, None), property):
            object.__setattr__(self, name, value)
            return
        native = self.__dict__.get("_native")
        if native is not None:
            setattr(native, name, value)
            return
        object.__setattr__(self, name, value)

    # -- transparent container/dunder forwarding (pyqtgraph parity) ---------
    # ``__bool__`` returns True so truthiness (``if handle:``) never falls through
    # to ``__len__`` on items that aren't sized. The rest forward to the native
    # item and raise the native's own TypeError when it isn't supported.
    def __bool__(self):
        return True

    def __len__(self):
        return len(self._native)

    def __getitem__(self, key):
        return self._native[key]

    def __setitem__(self, key, value):
        self._native[key] = value

    def __iter__(self):
        return iter(self._native)

    def __contains__(self, item):
        return item in self._native


class _Curve(_Item):
    """Handle for a pyqtgraph ``PlotDataItem`` / ``PlotCurveItem``."""

    def set_data(self, x: np.ndarray, y: np.ndarray) -> None:
        """Replace the curve samples."""
        self._native.setData(np.asarray(x), np.asarray(y))

    def get_data(self):
        """Return the curve's current ``(x, y)`` samples."""
        return self._native.getData()


class _Scatter(_Item):
    """Handle for a pyqtgraph ``ScatterPlotItem``."""

    def set_data(self, x: np.ndarray, y: np.ndarray) -> None:
        """Replace the scatter positions."""
        self._native.setData(np.asarray(x), np.asarray(y))

    def get_data(self):
        """Return the scatter's current ``(x, y)`` positions."""
        return self._native.getData()


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

    def clear(self) -> None:
        """Clear the image data."""
        self._native.clear()


class _Region(_Item):
    """Handle for a pyqtgraph ``LinearRegionItem``."""

    @property
    def bounds(self) -> tuple[float, float]:
        """The ``(low, high)`` edges of the region."""
        return tuple(self._native.getRegion())

    def set_bounds(self, low: float, high: float) -> None:
        """Move the region to new ``(low, high)`` edges.

        Programmatic moves block the native item's signals so an ``on_change``
        callback (meant for user drags) is not re-entered by code updating the
        region — the method-based-mutation contract that replaces the old manual
        ``blockSignals`` dance at call sites.
        """
        blocked = self._native.blockSignals(True)
        try:
            self._native.setRegion((low, high))
        finally:
            self._native.blockSignals(blocked)

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

    def set_value(self, value: float) -> None:
        """Move the marker to a new position.

        Programmatic moves block the native item's signals so an ``on_change``
        callback (meant for user drags) is not re-entered by code updating the
        marker — the method-based-mutation contract that replaces the old manual
        ``blockSignals`` dance at call sites.
        """
        blocked = self._native.blockSignals(True)
        try:
            self._native.setValue(float(value))
        finally:
            self._native.blockSignals(blocked)

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


class _Roi(_Item):
    """Handle for a pyqtgraph ROI (``RectROI`` / ``CircleROI``)."""

    @property
    def pos(self) -> tuple[float, float]:
        """The ``(x, y)`` lower-left corner in image coordinates."""
        p = self._native.pos()
        return (float(p.x()), float(p.y()))

    @property
    def size(self) -> tuple[float, float]:
        """The ``(w, h)`` size in image coordinates."""
        s = self._native.size()
        return (float(s.x()), float(s.y()))

    def set_pos(self, x: float, y: float) -> None:
        """Move the ROI's lower-left corner."""
        self._native.setPos((float(x), float(y)))

    def set_size(self, w: float, h: float) -> None:
        """Resize the ROI."""
        self._native.setSize((float(w), float(h)))

    def on_change(self, callback, *, final: bool = True) -> None:
        """Fire ``callback()`` while/after the ROI is dragged or resized."""
        sig = self._native.sigRegionChangeFinished if final else self._native.sigRegionChanged
        sig.connect(lambda *_: callback())


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
    def add_curve(
        self,
        x,
        y,
        *,
        pen,
        name=None,
        fill=None,
        step=False,
        symbol=None,
        symbol_size=7.0,
        symbol_brush=None,
        symbol_pen=None,
    ) -> H.Curve:
        """Draw a line/step curve, optionally with point markers."""
        kw = {"pen": _pen(pen)}
        if name is not None:
            kw["name"] = name
        if step:
            kw["stepMode"] = "center"
        if fill is not None:
            kw["fillLevel"] = 0.0
            kw["brush"] = _brush(fill)
        if symbol is not None:
            kw["symbol"] = symbol.value
            kw["symbolSize"] = symbol_size
            kw["symbolBrush"] = _brush(symbol_brush) if symbol_brush is not None else None
            kw["symbolPen"] = _pen(symbol_pen) if symbol_pen is not None else None
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

    def add_fill_between(self, lower, upper, *, brush) -> H.Handle:
        """Fill the area between two curve handles."""
        item = pg.FillBetweenItem(lower.native, upper.native, brush=_brush(brush))
        self._pi.addItem(item)
        return _Item(item, self._pi)

    def add_errorbars(self, x, y, *, height, top, bottom, pen, beam=None) -> H.ErrorBars:
        """Draw error bars."""
        kw = {"x": np.asarray(x), "y": np.asarray(y), "pen": _pen(pen)}
        if beam is not None:
            kw["beam"] = beam
        if height is not None:
            kw["height"] = np.asarray(height)
        if top is not None:
            kw["top"] = np.asarray(top)
        if bottom is not None:
            kw["bottom"] = np.asarray(bottom)
        item = pg.ErrorBarItem(**kw)
        self._pi.addItem(item)
        return _ErrorBars(item, self._pi)

    def add_image(self, data, *, colormap, levels, rect, axis_order="row-major") -> H.Image:
        """Draw an image/heatmap."""
        item = pg.ImageItem(np.asarray(data), axisOrder=axis_order)
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
        """Enable a legend collecting named handles (idempotent).

        Removes any legend created by an earlier call first, so refreshing a
        plot (clear → legend → redraw) does not stack orphaned legend boxes in
        the scene.
        """
        existing = getattr(self._pi, "legend", None)
        if existing is not None:
            scene = existing.scene()
            if scene is not None:
                scene.removeItem(existing)
            else:
                self._pi.removeItem(existing)
            self._pi.legend = None
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

    def set_menu_enabled(self, enabled) -> None:
        """Enable/disable pyqtgraph's own right-click viewbox menu."""
        try:
            self._pi.getViewBox().setMenuEnabled(enabled)
            self._pi.setMenuEnabled(enabled)
        except Exception:
            pass

    def provides_native_menu(self) -> bool:
        """Pyqtgraph ships its own rich Export/CSV/image right-click menu."""
        return True

    def add_menu_action(self, label, callback) -> None:
        """Inject a custom action into pyqtgraph's viewbox right-click menu."""
        try:
            self._pi.getViewBox().menu.addAction(label, callback)
        except Exception:
            pass

    def export_image(self, path, *, width=None) -> bool:
        """Export the panel to an image via pyqtgraph's ImageExporter."""
        try:
            from pyqtgraph import exporters

            exp = exporters.ImageExporter(self._pi)
            if width is not None:
                exp.parameters()["width"] = int(width)
            exp.export(path)
            return True
        except Exception:
            return False

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


class _PgImageView(base.ImageViewCanvas):
    """A pyqtgraph ``ImageView`` (image + LUT histogram + frame slider)."""

    def __init__(self, **opts):
        self._iv = pg.ImageView(**opts)

    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable image-view widget."""
        return self._iv

    def set_image(self, data, *, auto_levels=True, axes=None) -> None:
        """Show an image or ``(t, y, x)`` stack."""
        kw = {"autoLevels": auto_levels}
        if axes is not None:
            kw["axes"] = axes
        self._iv.setImage(np.asarray(data), **kw)

    def set_colormap(self, name, source="matplotlib") -> None:
        """Apply a named colormap to the image."""
        for src in (source, None):
            try:
                cm = pg.colormap.get(name, source=src) if src else pg.colormap.get(name)
                if cm is not None:
                    self._iv.setColorMap(cm)
                    return
            except Exception:
                continue

    def clear(self) -> None:
        """Clear the image and overlays."""
        self._iv.clear()

    def set_histogram_width(self, width) -> None:
        """Constrain (or free, with ``None``) the LUT histogram panel width."""
        try:
            self._iv.ui.histogram.setMaximumWidth(16777215 if width is None else int(width))
        except Exception:
            pass

    def set_interactive(self, *, mouse=True, menu=True) -> None:
        """Toggle view pan/zoom and the right-click menu."""
        vb = self._iv.getView()
        try:
            vb.setMouseEnabled(x=mouse, y=mouse)
            vb.setMenuEnabled(menu)
        except Exception:
            pass

    def add_overlay(self, data, *, colormap=None) -> H.Image:
        """Overlay a second image item on the view."""
        item = pg.ImageItem(np.asarray(data))
        lut = _lut(colormap)
        if lut is not None:
            item.setLookupTable(lut)
        view = self._iv.getView()
        view.addItem(item)
        return _Image(item, view)

    def add_roi(
        self, *, kind="rect", pos=(0.0, 0.0), size=(10.0, 10.0), pen, movable=True, rotatable=False
    ) -> H.Roi:
        """Add a region-of-interest to the view."""
        if kind == "circle":
            roi = pg.CircleROI(list(pos), list(size), pen=_pen(pen), movable=movable)
        else:
            roi = pg.RectROI(
                list(pos), list(size), pen=_pen(pen), movable=movable, rotatable=rotatable
            )
        view = self._iv.getView()
        view.addItem(roi)
        return _Roi(roi, view)

    def on_click(self, callback) -> None:
        """Register ``callback(x, y)`` for clicks in image coordinates."""

        def _handler(event):
            vb = self._iv.getView()
            pt = vb.mapSceneToView(event.scenePos())
            callback(pt.x(), pt.y())

        self._iv.getView().scene().sigMouseClicked.connect(_handler)

    @property
    def native(self):
        """The wrapped pyqtgraph ``ImageView``."""
        return self._iv


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

    def create_image_view(self, **opts) -> base.ImageViewCanvas:
        """Create an image view backed by a ``pg.ImageView``."""
        return _PgImageView(**opts)

    def configure(self, **global_opts) -> None:
        """Apply process-wide pyqtgraph options."""
        pg.setConfigOptions(**global_opts)

    def raw_module(self):
        """Return the ``pyqtgraph`` module (the passthrough fall-through target)."""
        return pg
