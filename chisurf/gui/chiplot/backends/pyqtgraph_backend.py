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


def _colormap(cmap: S.Colormap | None):
    """Resolve a chiplot :class:`~chisurf.gui.chiplot.style.Colormap` to a ``pg.ColorMap``.

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
                return cm
        except Exception:
            continue
    return None


def _lut(cmap: S.Colormap | None):
    """Resolve a chiplot colormap to a lookup table.

    Returns ``None`` if the colormap cannot be resolved by pyqtgraph.

    Parameters
    ----------
    cmap : Colormap or None
        The colormap reference to resolve; ``None`` yields ``None``.
    """
    cm = _colormap(cmap)
    return None if cm is None else cm.getLookupTable(alpha=True)


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

    def set_pen(self, pen) -> None:
        """Restyle the curve's line (accepts a Pen or any pen-like spec)."""
        if pen is None:
            self._native.setPen(_pen(None))
            return
        self._native.setPen(_pen(pen if isinstance(pen, S.Pen) else S.to_pen(pen)))

    def set_symbol(self, symbol) -> None:
        """Set (or clear with ``None``) the per-point marker symbol."""
        if symbol is None:
            self._native.setSymbol(None)
        elif isinstance(symbol, H.Symbol):
            self._native.setSymbol(symbol.value)
        else:
            self._native.setSymbol(symbol)

    def set_symbol_size(self, size) -> None:
        """Set the per-point marker size in pixels."""
        self._native.setSymbolSize(size)

    def set_symbol_brush(self, brush) -> None:
        """Set the per-point marker fill (accepts a Brush or brush-like spec)."""
        self._native.setSymbolBrush(_brush(brush) if isinstance(brush, S.Brush) else brush)

    def set_opacity(self, alpha: float) -> None:
        """Set the whole-curve opacity (0 transparent .. 1 opaque)."""
        self._native.setOpacity(float(alpha))


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
        """Replace error-bar geometry.

        The extents are *replaced*, not merged: an extent that is not passed is
        cleared. ``ErrorBarItem.setData`` only updates the keys it is given and
        lets a stale ``height`` override ``top``/``bottom``, so a handle created
        with ``height`` and later updated with ``top``/``bottom`` would keep
        drawing (or, with mismatched lengths, crash on) the old ``height``.
        """
        self._native.setData(
            x=np.asarray(x),
            y=np.asarray(y),
            height=None if height is None else np.asarray(height),
            top=None if top is None else np.asarray(top),
            bottom=None if bottom is None else np.asarray(bottom),
        )


class _Image(_Item):
    """Handle for a pyqtgraph ``ImageItem``."""

    def set_image(self, data: np.ndarray, *, levels=None) -> None:
        """Replace the image data."""
        self._native.setImage(np.asarray(data), autoLevels=levels is None)
        if levels is not None:
            self._native.setLevels(levels)

    def set_levels(self, low: float, high: float) -> None:
        """Set the intensity range mapped to the colormap ends."""
        self._native.setLevels((float(low), float(high)))

    def set_colormap(self, colormap) -> None:
        """Recolour the image; ``None`` restores the grayscale ramp."""
        self._native.setLookupTable(_lut(S.to_colormap(colormap)))

    def set_rect(self, x: float, y: float, w: float, h: float) -> None:
        """Place the image in data coordinates."""
        self._native.setRect(QtCore.QRectF(x, y, w, h))

    def clear(self) -> None:
        """Clear the image data."""
        self._native.clear()


class _ColorBar(_Item):
    """Handle for a pyqtgraph ``HistogramLUTItem`` bound to an image."""

    def set_colormap(self, colormap) -> None:
        """Apply a colormap (name or :class:`~chisurf.gui.chiplot.style.Colormap`)."""
        cm = _colormap(S.to_colormap(colormap))
        if cm is not None:
            self._native.gradient.setColorMap(cm)

    def set_levels(self, low: float, high: float) -> None:
        """Set the mapped intensity range."""
        self._native.setLevels(float(low), float(high))

    def get_levels(self) -> tuple[float, float]:
        """Return the mapped ``(low, high)`` intensity range."""
        return tuple(float(v) for v in self._native.getLevels())

    def set_histogram_visible(self, visible: bool) -> None:
        """Show or hide the intensity histogram beside the colour ramp."""
        item = self._native
        # Only the histogram *curve* is hidden. The viewbox behind it carries the
        # level handles and the axis that reports them, so hiding that too leaves a
        # ramp labelled 0-1 regardless of the levels actually set.
        curve = getattr(item, "plot", None)
        if curve is not None and hasattr(curve, "setVisible"):
            curve.setVisible(bool(visible))
        if not visible:
            # The item still reserves the histogram's width; shrink it to the ramp
            # and its axis so the panels get the room back.
            try:
                item.setMaximumWidth(70)
            except Exception:
                pass

    def on_levels_changed(self, callback) -> None:
        """Call ``callback(low, high)`` when the user drags the level handles."""
        self._native.sigLevelsChanged.connect(
            lambda item: callback(*(float(v) for v in item.getLevels()))
        )


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

    def set_limits(self, low: float, high: float) -> None:
        """Constrain the region's draggable range to ``(low, high)``.

        Maps to pyqtgraph's ``setBounds`` (the drag limits), which is distinct
        from ``setRegion`` (the current position, exposed as
        :meth:`set_bounds`). Blocks signals so the limit update never re-enters
        an ``on_change`` drag callback.
        """
        blocked = self._native.blockSignals(True)
        try:
            self._native.setBounds((low, high))
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


def _pg_angle(angle: float) -> float:
    """Convert a chiplot pointing angle to pyqtgraph's ``ArrowItem`` angle.

    chiplot measures the direction the tip faces in degrees counter-clockwise
    from ``+x`` (``degrees(arctan2(dy, dx))``). A pyqtgraph arrow at angle ``0``
    points *left*, and its rotation runs clockwise on screen because the scene's
    y-axis points down — so the two conventions differ by ``180 - angle``.

    Parameters
    ----------
    angle : float
        Pointing direction, degrees counter-clockwise from ``+x``.

    Returns
    -------
    float
        The equivalent ``ArrowItem`` angle.
    """
    return 180.0 - float(angle)


class _Arrow(_Item):
    """Handle for a pyqtgraph ``ArrowItem``."""

    @property
    def position(self) -> tuple[float, float]:
        """The ``(x, y)`` tip position in data coordinates."""
        p = self._native.pos()
        return (float(p.x()), float(p.y()))

    @property
    def angle(self) -> float:
        """Pointing direction in degrees counter-clockwise from ``+x``."""
        # Read back through the same conversion rather than caching the value the
        # caller passed, so an angle set on the native item (passthrough) is
        # still reported in chiplot's convention.
        return 180.0 - float(self._native.opts["angle"])

    def set_position(self, x: float, y: float) -> None:
        """Move the arrow tip."""
        self._native.setPos(float(x), float(y))

    def set_angle(self, angle: float) -> None:
        """Re-aim the arrow (degrees counter-clockwise from ``+x``)."""
        self._native.setStyle(angle=_pg_angle(angle))


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

    @property
    def points(self) -> list:
        """The vertices in scene coordinates, for a polygon ROI.

        ``PolyLineROI.getLocalHandlePositions`` gives handle positions in the
        ROI's *own* frame, which is not where the region is once the user has
        dragged the whole polygon; mapping each through the ROI's transform is
        what makes the vertices usable as geometry.
        """
        if not isinstance(self._native, pg.PolyLineROI):
            # Every pyqtgraph ROI has handles, but on a rectangle they are the
            # scale grips — one of them — not the shape. The corners are what a
            # caller means by "the vertices" here.
            x, y = self.pos
            w, h = self.size
            return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        # Map out of the ROI's own frame with the ROI's transform, not through
        # the scene: scene coordinates depend on the viewport transform, which
        # is meaningless until the widget has been laid out — so a polygon read
        # before the window is shown came back scaled by a few hundred.
        return [
            (lambda p: (float(p.x()), float(p.y())))(self._native.mapToParent(local))
            for _, local in self._native.getLocalHandlePositions()
        ]

    def set_pen(self, pen, **overrides) -> None:
        """Restyle the ROI's outline (colour, width).

        A region editor needs this to say which row of its list the picture is
        showing, and to grey out a region the user has switched off.
        """
        self._native.setPen(
            _pen(S.to_pen(pen, **overrides) if not isinstance(pen, S.Pen) or overrides
                 else pen)
        )

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



def _roi_item(kind, pos, size, pen, movable, rotatable, points):
    """Build the pyqtgraph ROI item for a region shape.

    Shared by the image view and the plot canvas: a region carries no axes, so
    the same shapes serve a frame and a data plane (a phasor cursor, a gate on a
    joint histogram).
    """
    if kind == "circle":
        return pg.CircleROI(list(pos), list(size), pen=_pen(pen), movable=movable)
    if kind == "ellipse":
        return pg.EllipseROI(list(pos), list(size), pen=_pen(pen), movable=movable)
    if kind == "polygon":
        # A polygon is defined by its vertices, not a corner and a size; the box
        # is only the fallback when no vertices were given.
        if points is None:
            x, y = float(pos[0]), float(pos[1])
            w, h = float(size[0]), float(size[1])
            points = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        return pg.PolyLineROI(
            [tuple(map(float, p)) for p in points],
            closed=True, pen=_pen(pen), movable=movable,
        )
    return pg.RectROI(
        list(pos), list(size), pen=_pen(pen), movable=movable, rotatable=rotatable
    )


class _PgCanvas(base.Canvas):
    """A pyqtgraph-backed single plot panel."""

    def __init__(self, plot_item: pg.PlotItem, host: QtWidgets.QWidget, *, owns_host: bool = True):
        self._pi = plot_item
        self._host = host  # provides scene() and is the embeddable widget
        # A grid panel shares one host widget with its siblings, so widget-level
        # styling (background) must stay with the canvas that owns the widget.
        self._owns_host = owns_host

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
        skip_missing=True,
    ) -> H.Curve:
        """Draw a line/step curve, optionally with point markers."""
        kw = {"pen": _pen(pen)}
        if skip_missing:
            # Break the line at NaN/inf rather than drawing a segment across the
            # gap, which is what a masked-out range is meant to look like.
            kw["connect"] = "finite"
        if name is not None:
            kw["name"] = name
        if step:
            # A string picks the pyqtgraph step mode directly ("left"/"right"
            # keep x/y equal length; "center" needs len(x) == len(y) + 1). A
            # bare ``True`` defaults to centered bins.
            kw["stepMode"] = step if isinstance(step, str) else "center"
        if fill is not None:
            kw["fillLevel"] = 0.0
            kw["brush"] = _brush(fill)
        if symbol is not None:
            kw["symbol"] = symbol.value
            kw["symbolSize"] = symbol_size
            # Only override the marker fill/outline when the caller asked for
            # one: forwarding ``None`` means *no brush* / *no pen*, i.e. an
            # invisible marker, where "not specified" must mean "the renderer's
            # own default" (a curve with symbol="o" and no colours must show).
            if symbol_brush is not None:
                kw["symbolBrush"] = _brush(symbol_brush)
            if symbol_pen is not None:
                kw["symbolPen"] = _pen(symbol_pen)
        item = self._pi.plot(np.asarray(x), np.asarray(y), **kw)
        return _Curve(item, self._pi)

    def add_scatter(self, x, y, *, size, pen, brush, symbol, name=None) -> H.Scatter:
        """Draw a scatter cloud.

        Backed by a **log-aware** ``PlotDataItem`` (no connecting line + a symbol)
        rather than a raw ``ScatterPlotItem``. A raw ScatterPlotItem ignores the
        plot's log mode, so its points would be drawn at linear positions on a log
        axis and would corrupt auto-range; a PlotDataItem transforms correctly
        under :meth:`set_log`.
        """
        kw = {
            "pen": None,
            "symbol": symbol.value,
            "symbolSize": size,
            "symbolBrush": _brush(brush) if brush is not None else None,
            "symbolPen": _pen(pen) if pen is not None else None,
        }
        if name is not None:
            kw["name"] = name
        item = self._pi.plot(np.asarray(x), np.asarray(y), **kw)
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

    def add_roi(
        self, *, kind="rect", pos=(0.0, 0.0), size=(10.0, 10.0), pen, movable=True,
        rotatable=False, points=None,
    ) -> H.Roi:
        """Add a region-of-interest shape over the plot.

        A region on a *data* plane, not an image: a gate on a joint intensity
        histogram, a cursor round a phasor cluster, a box on an E–S plot. The
        shapes and the handle are the image view's, because a region carries no
        axes and does not care which of the two it is drawn on.
        """
        item = _roi_item(kind, pos, size, pen, movable, rotatable, points)
        self._pi.addItem(item)
        return _Roi(item, self._pi)

    def add_marker(self, pos, *, orientation, movable, pen, label) -> H.Marker:
        """Draw a movable cursor line."""
        angle = 90 if orientation is H.Orientation.VERTICAL else 0
        item = pg.InfiniteLine(pos=pos, angle=angle, movable=movable, pen=_pen(pen), label=label)
        self._pi.addItem(item)
        return _Marker(item, self._pi)

    def add_arrow(
        self, pos, *, angle=0.0, size=20.0, tip_angle=25.0, head_width=None,
        tail_length=None, tail_width=3.0, pen=None, brush=None,
    ) -> H.Arrow:
        """Draw a scale-invariant arrow head at a data coordinate.

        ``angle`` arrives in chiplot's convention (counter-clockwise from ``+x``)
        and is converted here — see :func:`_pg_angle` — so no call site carries a
        renderer-specific sign flip.
        """
        item = pg.ArrowItem(
            pos=(float(pos[0]), float(pos[1])),
            angle=_pg_angle(angle),
            headLen=float(size),
            headWidth=None if head_width is None else float(head_width),
            tipAngle=float(tip_angle),
            tailLen=None if tail_length is None else float(tail_length),
            tailWidth=float(tail_width),
            pen=_pen(pen),
            brush=_brush(brush),
        )
        self._pi.addItem(item)
        return _Arrow(item, self._pi)

    def add_text(
        self, text, pos, *, color, anchor, draggable, fill=None, border=None, anchored=False
    ) -> H.Text:
        """Draw a text label.

        Data-anchored labels (default) are added with ``ignoreBounds=True`` so
        the annotation never drives the view's auto-range — a text placed at a
        data coordinate (especially on a log axis, where a raw coordinate lands
        far off the log scale) must not blow the range out.

        Screen-anchored labels (``anchored=True``) are parented to the
        ``PlotItem`` instead, so they stay pinned to a fixed pixel offset and do
        not move or rescale with the data. Optional ``fill``/``border`` draw a
        background box.
        """
        cls = _DraggableTextItem if draggable else pg.TextItem
        kw = {"text": text, "color": color.as_tuple(), "anchor": anchor}
        if fill is not None:
            kw["fill"] = _brush(fill)
        if border is not None:
            kw["border"] = _pen(border)
        item = cls(**kw)
        if anchored:
            # Pin to the plot rectangle in screen space (pos is a pixel offset
            # from the PlotItem's top-left), not to a data coordinate.
            item.setParentItem(self._pi)
            item.setPos(*pos)
        else:
            item.setPos(*pos)
            self._pi.addItem(item, ignoreBounds=True)
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

    def set_tick_spacing(self, side, *, major=None, minor=None) -> None:
        """Fix the tick interval on one axis, or restore automatic spacing."""
        axis = self._pi.getAxis(side)
        if major is None and minor is None:
            axis.setTickSpacing()
        else:
            axis.setTickSpacing(major=major, minor=minor if minor is not None else major)

    def on_range_changed(self, callback) -> None:
        """Register ``callback(x_range, y_range)`` for pan/zoom of this panel."""
        self._pi.getViewBox().sigRangeChanged.connect(
            lambda _vb, ranges: callback(tuple(ranges[0]), tuple(ranges[1]))
        )

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
        """Set the background color of the panel — and of the whole widget.

        ``ViewBox.setBackgroundColor`` paints only the data rectangle, leaving
        the axis strips, tick labels and title on the process-wide pyqtgraph
        background (black in ChiSurf). A canvas that owns its host widget
        (single ``Plot``, not a grid panel sharing one layout widget) therefore
        paints the widget too, which is what the ``pg.PlotWidget`` +
        ``setBackground`` call sites this replaces did. ``None`` means
        transparent, pyqtgraph's own idiom.
        """
        value = color.as_tuple() if color is not None else None
        self._pi.getViewBox().setBackgroundColor(value)
        if self._owns_host and hasattr(self._host, "setBackground"):
            self._host.setBackground(value)

    def set_aspect_locked(self, lock, ratio=1.0) -> None:
        """Lock the x/y pixel aspect ratio."""
        self._pi.getViewBox().setAspectLocked(lock, ratio)

    def invert_y(self, invert=True) -> None:
        """Invert the y-axis direction."""
        self._pi.getViewBox().invertY(invert)

    def set_si_prefix(self, *, x=None, y=None) -> None:
        """Enable or disable the automatic SI prefix on an axis."""
        for side, enabled in (("bottom", x), ("left", y)):
            if enabled is None:
                continue
            try:
                self._pi.getAxis(side).enableAutoSIPrefix(bool(enabled))
            except Exception:
                pass

    def set_axis_visible(self, side, visible) -> None:
        """Show or hide one axis."""
        self._pi.showAxis(side, bool(visible))

    def link_x(self, other) -> None:
        """Link this panel's x-axis to ``other``'s (shared pan/zoom)."""
        self._pi.getViewBox().setXLink(other._pi.getViewBox())

    def link_y(self, other) -> None:
        """Link this panel's y-axis to ``other``'s (shared pan/zoom)."""
        self._pi.getViewBox().setYLink(other._pi.getViewBox())

    def set_menu_enabled(self, enabled) -> None:
        """Enable/disable pyqtgraph's own right-click viewbox menu."""
        try:
            self._pi.getViewBox().setMenuEnabled(enabled)
            self._pi.setMenuEnabled(enabled)
        except Exception:
            pass

    def menu_enabled(self) -> bool:
        """Whether the viewbox still offers pyqtgraph's right-click menu."""
        try:
            return bool(self._pi.getViewBox().menuEnabled())
        except Exception:
            return False

    def set_interactive(self, *, mouse=True, menu=True) -> None:
        """Enable/disable mouse pan-zoom and the right-click menu."""
        try:
            self._pi.getViewBox().setMouseEnabled(x=mouse, y=mouse)
        except Exception:
            pass
        self.set_menu_enabled(menu)

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
        """Register ``callback(x, y, button)`` for clicks **in this panel**.

        pyqtgraph's mouse signals are scene-wide, and every panel of a grid
        shares one scene, so the position is filtered against this panel's own
        viewbox before it is mapped: otherwise a click on one panel fired on
        all of them, each reporting a coordinate extrapolated through its own
        unrelated view range (and a click in the axis margin of a single plot
        reported data coordinates outside the view).
        """

        def _handler(event):
            if not self._contains(event.scenePos()):
                return
            pt = self._pi.getViewBox().mapSceneToView(event.scenePos())
            callback(pt.x(), pt.y(), _QT_BUTTON.get(event.button(), "other"))

        self._host.scene().sigMouseClicked.connect(_handler)

    def on_mouse_move(self, callback) -> None:
        """Register ``callback(x, y)`` for pointer motion over this panel."""

        def _handler(pos):
            if not self._contains(pos):
                return
            pt = self._pi.getViewBox().mapSceneToView(pos)
            callback(pt.x(), pt.y())

        self._host.scene().sigMouseMoved.connect(_handler)

    def _contains(self, scene_pos) -> bool:
        """Whether a scene position lies inside this panel's plotting area."""
        try:
            return bool(self._pi.getViewBox().sceneBoundingRect().contains(scene_pos))
        except Exception:
            return True

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
        return _PgCanvas(pi, self._w, owns_host=False)

    def add_colorbar(
        self, image, *, colormap=None, row=None, col=None, rowspan=1, colspan=1
    ) -> H.ColorBar:
        """Add an interactive colour bar / level editor bound to ``image``."""
        item = pg.HistogramLUTItem()
        item.setImageItem(image.native)
        bar = _ColorBar(item, self._w)
        bar.set_colormap(colormap)
        self._w.addItem(item, row=row, col=col, rowspan=rowspan, colspan=colspan)
        return bar

    def next_row(self) -> None:
        """Advance the implicit insertion cursor to the next row."""
        self._w.nextRow()

    def set_column_stretch(self, column: int, factor: float) -> None:
        """Set the relative width of a grid column."""
        self._w.ci.layout.setColumnStretchFactor(int(column), int(round(factor)))

    def set_row_stretch(self, row: int, factor: float) -> None:
        """Set the relative height of a grid row."""
        self._w.ci.layout.setRowStretchFactor(int(row), int(round(factor)))

    @property
    def native(self):
        """The wrapped ``GraphicsLayoutWidget``."""
        return self._w


class _PgImageView(base.ImageViewCanvas):
    """A pyqtgraph ``ImageView`` (image + LUT histogram + frame slider)."""

    def __init__(self, **opts):
        self._iv = pg.ImageView(**opts)
        # Items this canvas put on the view (overlays, ROIs) so ``clear`` can
        # take them off again — ``pg.ImageView.clear`` only clears the image.
        self._added: list = []

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
        """Clear the image, and the overlays/ROIs this canvas added.

        ``pg.ImageView.clear`` drops the image only; anything added through
        :meth:`add_overlay` / :meth:`add_roi` survived it and was drawn on top
        of the *next* image.
        """
        view = self._iv.getView()
        for item in self._added:
            try:
                view.removeItem(item)
            except Exception:
                pass
        self._added.clear()
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
        self._added.append(item)
        return _Image(item, view)

    def add_roi(
        self, *, kind="rect", pos=(0.0, 0.0), size=(10.0, 10.0), pen, movable=True,
        rotatable=False, points=None
    ) -> H.Roi:
        """Add a region-of-interest to the view."""
        roi = _roi_item(kind, pos, size, pen, movable, rotatable, points)
        view = self._iv.getView()
        view.addItem(roi)
        self._added.append(roi)
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


class _PgVolumeView(base.VolumeViewCanvas):
    """Volume renderer backed by pyqtgraph's OpenGL ``GLViewWidget``.

    A thin wrapper: the widget, a volume item and a camera. Chiplot owns the
    mapping from a scalar volume to RGBA, because that is the part a native
    renderer would have to reproduce.
    """

    def __init__(self, **opts):
        import pyqtgraph.opengl as gl

        self._gl = gl
        self._view = gl.GLViewWidget(**opts)
        self._item = None
        self._vectors = []
        self._scale = (1.0, 1.0, 1.0)
        self._view.setCameraPosition(distance=200)

    def widget(self):
        return self._view

    def set_volume(self, data, *, colormap="magma", threshold=0.0, gamma=1.0):
        import numpy as np

        vol = np.asarray(data, dtype=float)
        if vol.ndim != 3:
            raise ValueError(f"a volume must be 3-D (nz, ny, nx), got {vol.shape}")

        peak = vol.max()
        norm = vol / peak if peak > 0 else vol
        if threshold > 0.0:
            norm = np.where(norm < threshold, 0.0, norm)
        if gamma != 1.0:
            norm = norm ** gamma

        lut = None
        try:
            name = colormap.name if isinstance(colormap, S.Colormap) else colormap
            lut = pg.colormap.get(name, source="matplotlib").getLookupTable(
                0.0, 1.0, 256)
        except Exception:
            # an unknown name is not worth failing a render over; grey is a
            # legible fallback and the caller still sees its data
            lut = None

        rgba = np.zeros(norm.shape + (4,), dtype=np.ubyte)
        idx = np.clip((norm * 255).astype(int), 0, 255)
        if lut is not None:
            rgba[..., :3] = np.asarray(lut, dtype=np.ubyte)[idx][..., :3]
        else:
            rgba[..., 0] = idx
            rgba[..., 1] = idx
            rgba[..., 2] = idx
        # opacity follows intensity, so empty space stays empty
        rgba[..., 3] = idx

        # GLVolumeItem indexes (x, y, z); the array arrives as (z, y, x)
        rgba = np.ascontiguousarray(rgba.transpose(2, 1, 0, 3))

        self.clear()
        self._item = self._gl.GLVolumeItem(rgba, smooth=True)
        nz, ny, nx = vol.shape
        sx, sy, sz = self._scale
        self._item.scale(sx, sy, sz)
        self._item.translate(-nx * sx / 2, -ny * sy / 2, -nz * sz / 2)
        self._view.addItem(self._item)
        # swapping the item does not by itself schedule a repaint, so a second
        # and later volume would never reach the screen
        self._view.update()

    def set_scale(self, sx=1.0, sy=1.0, sz=1.0):
        self._scale = (float(sx), float(sy), float(sz))

    def set_vectors(self, segments, *, color=(1.0, 1.0, 1.0, 0.8), width=2.0):
        import numpy as np

        for item in self._vectors:
            self._view.removeItem(item)
        self._vectors = []
        if segments is None:
            self._view.update()
            return

        seg = np.asarray(segments, dtype=float)
        if seg.ndim != 3 or seg.shape[1:] != (2, 3):
            raise ValueError(f"segments must be (n, 2, 3), got {seg.shape}")
        sx, sy, sz = self._scale
        scale = np.array([sx, sy, sz])
        for a, b in seg:
            item = self._gl.GLLinePlotItem(
                pos=np.vstack([a, b]) * scale, color=color, width=width,
                antialias=True)
            self._view.addItem(item)
            self._vectors.append(item)
        self._view.update()

    def clear(self):
        if self._item is not None:
            self._view.removeItem(self._item)
            self._item = None
        for item in self._vectors:
            self._view.removeItem(item)
        self._vectors = []

    def set_camera(self, distance=None, elevation=None, azimuth=None):
        self._view.setCameraPosition(
            distance=distance, elevation=elevation, azimuth=azimuth)

    @property
    def native(self):
        return self._view


class PyQtGraphBackend(base.Backend):
    """chiplot backend rendering through pyqtgraph."""

    name = "pyqtgraph"

    def create_canvas(self, **opts) -> base.Canvas:
        """Create a single-panel canvas backed by a ``pg.PlotWidget``."""
        background = opts.pop("background", None)
        pw = pg.PlotWidget(**opts)
        if background is not None:
            pw.setBackground(
                background.as_tuple() if isinstance(background, S.Color) else background
            )
        return _PgCanvas(pw.getPlotItem(), pw)

    def create_grid(self, **opts) -> base.GridCanvas:
        """Create a multi-panel grid backed by a ``GraphicsLayoutWidget``."""
        return _PgGrid(**opts)

    def create_image_view(self, **opts) -> base.ImageViewCanvas:
        """Create an image view backed by a ``pg.ImageView``."""
        return _PgImageView(**opts)

    def create_volume_view(self, **opts) -> base.VolumeViewCanvas:
        """Create a 3-D volume view backed by ``pyqtgraph.opengl``."""
        return _PgVolumeView(**opts)

    def configure(self, **global_opts) -> None:
        """Apply process-wide pyqtgraph options."""
        pg.setConfigOptions(**global_opts)

    def raw_module(self):
        """Return the ``pyqtgraph`` module (the passthrough fall-through target)."""
        return pg
