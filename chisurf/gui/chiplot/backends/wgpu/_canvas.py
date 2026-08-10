"""Widget-side canvas for the chiplot WebGPU backend.

The widget is a plain :class:`QWidget`. Its ``paintEvent`` renders the data
area offscreen on the GPU (:mod:`._gpu`), blits the resulting RGBA into the
plot rectangle, and then draws the axes, ticks, labels and legend on top with
``QPainter``.

That ordering is deliberate. Hosting a GPU *surface* inside the widget would
put the renderer and ``QPainter`` in a fight over the same framebuffer — the
failure that left the previous OpenGL attempt drawing chrome onto a black
rectangle — and would make every headless screenshot a special case. Rendering
to an image costs one GPU→CPU copy per repaint and removes both problems.

:class:`_WgpuCanvas` implements :class:`base.Canvas`, :class:`_WgpuGrid`
implements :class:`base.GridCanvas`, and :class:`_WgpuImageView` implements
:class:`base.ImageViewCanvas`.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable
from typing import Any

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

from chisurf.gui.chiplot import handles as H
from chisurf.gui.chiplot import style as S
from chisurf.gui.chiplot.backends import base
from chisurf.gui.chiplot.backends.wgpu import _gpu, _handles
from chisurf.gui.chiplot.backends.wgpu._view import PixelView as _PixelView
from chisurf.gui.chiplot.backends.wgpu._view import pow10 as _pow10

#: Pixel insets reserved for axis chrome. The left inset is a floor: the real
#: one is measured from the widest tick label each frame, because a fixed
#: margin is what makes ``1e+04`` sit on top of the axis line.
_LEFT_MARGIN = 46
_BOTTOM_MARGIN = 38
_TOP_MARGIN = 10
_RIGHT_MARGIN = 14

#: Breathing room on a side that draws nothing, and the two pieces of an axis
#: that does: the tick mark itself and the gap before its label.
_EDGE_PAD = 6
_TICK_LEN = 4
_TICK_GAP = 4

_AXIS_COLOR = QtGui.QColor(170, 170, 175)
_GRID_COLOR = (0.62, 0.62, 0.66)
#: How close to the pointer (in pixels) a draggable edge must be to grab it.
_GRAB_PX = 6.0

#: Pixels a press must travel before it counts as a drag rather than a click.
#: pyqtgraph's ``GraphicsScene`` uses 5, and the distinction is what decides
#: whether a right button raises the context menu or scales the view.
_DRAG_PX = 5.0

#: Decades below the peak a logarithmic auto-range will show. Past this the
#: samples are the tail of the arithmetic rather than of the measurement.
_AUTORANGE_DECADES = 9.0

#: Geometry of the auto-range button in the plot's bottom-left corner.
_AUTO_BTN_SIZE = 14
_AUTO_BTN_INSET = 3


class _Margins:
    """Pixel insets that define the plot area inside the widget."""

    def __init__(self):
        self.left = _LEFT_MARGIN
        self.bottom = _BOTTOM_MARGIN
        self.top = _TOP_MARGIN
        self.right = _RIGHT_MARGIN

    def plot_rect(self, w: int, h: int) -> tuple[int, int, int, int]:
        """Return ``(x, y, plot_w, plot_h)`` for the data-plot area."""
        pw = max(w - self.left - self.right, 1)
        ph = max(h - self.top - self.bottom, 1)
        return self.left, self.top, pw, ph


class _DrawContext:
    """What a handle needs to turn data into clip-space geometry.

    Attributes
    ----------
    to_ndc : callable
        ``(xs, ys) -> (nx, ny)`` data-to-clip mapping, log-aware.
    viewport : tuple of float
        Plot-area size in *device* pixels; widths and marker sizes are measured
        in this space.
    scale : float
        Device-pixel ratio, so a 2-px pen is 2 px on a Retina panel too.
    """

    __slots__ = ("to_ndc", "viewport", "scale")

    def __init__(self, to_ndc, viewport, scale):
        self.to_ndc = to_ndc
        self.viewport = viewport
        self.scale = scale


# ---------------------------------------------------------------------------
# Tick generation
# ---------------------------------------------------------------------------

def nice_ticks(lo: float, hi: float, target: int = 8) -> list[float]:
    """Return round tick positions spanning ``[lo, hi]``."""
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo == hi:
        return [lo] if math.isfinite(lo) else [0.0]
    if hi < lo:
        lo, hi = hi, lo
    raw_step = (hi - lo) / max(target, 1)
    mag = 10.0 ** math.floor(math.log10(raw_step))
    norm = raw_step / mag
    step = (1.0 if norm < 1.5 else 2.0 if norm < 3.0 else 5.0 if norm < 7.0 else 10.0) * mag
    start = math.ceil(lo / step) * step
    out, v, guard = [], start, 0
    while v <= hi + step * 1e-3 and guard < 1000:
        out.append(v)
        v += step
        guard += 1
    return out


def log_ticks(lo: float, hi: float, max_ticks: int = 12) -> list[float]:
    """Return decade (and, when there is room, 1-2-5) ticks for a log axis.

    A log axis whose ticks were chosen linearly is the tell-tale of the
    previous renderer: every label piles into the top decade because that is
    where all the linear space is.
    """
    lo = max(float(lo), 1e-300)
    hi = max(float(hi), lo * 10.0)
    d0 = math.floor(math.log10(lo))
    d1 = math.ceil(math.log10(hi))
    decades = list(range(int(d0), int(d1) + 1))
    if len(decades) <= 1:
        return [10.0 ** d0, 10.0 ** d1]
    stride = max(1, int(math.ceil(len(decades) / max_ticks)))
    ticks = [10.0 ** d for d in decades[::stride]]
    if len(ticks) <= 3:
        ticks = [m * 10.0 ** d for d in decades for m in (1.0, 2.0, 5.0)]
    return [t for t in ticks if lo * 0.999 <= t <= hi * 1.001] or [lo, hi]


def format_tick(value: float, step: float, *, log: bool = False) -> str:
    """Format one tick label."""
    if log:
        exp = math.log10(value) if value > 0 else 0.0
        if abs(exp - round(exp)) < 1e-9:
            e = int(round(exp))
            if -4 <= e <= 4:
                return f"{10.0 ** e:g}"
            return f"1e{e:+03d}"
        return f"{value:.3g}"
    if value == 0:
        return "0"
    if abs(value) >= 1e5 or abs(value) < 1e-4:
        return f"{value:.2e}"
    if step and step > 0:
        decimals = max(0, -int(math.floor(math.log10(step))))
        return f"{value:.{min(decimals, 6)}f}"
    return f"{value:g}"


# ---------------------------------------------------------------------------
# The widget
# ---------------------------------------------------------------------------

class _PlotWidget(QtWidgets.QWidget):
    """The surface: paints a GPU-rendered image plus QPainter chrome."""

    def __init__(self, canvas: _WgpuCanvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Expanding)
        self.setFocusPolicy(QtCore.Qt.WheelFocus)
        self.setAttribute(QtCore.Qt.WA_OpaquePaintEvent, True)
        # The menu is raised from a right *click* on release, the way
        # pyqtgraph does it — see _mouse_release. Letting Qt raise it from the
        # press instead is what broke dragging: the menu runs modally and
        # swallows the release, so the scale-drag never ended and every later
        # mouse move went on scaling the view.
        self.setContextMenuPolicy(QtCore.Qt.PreventContextMenu)

    def sizeHint(self) -> QtCore.QSize:
        """Ask for the same room a pyqtgraph panel asks for.

        A layout hands out space in proportion to what its children advertise,
        and this widget advertised nothing — Qt fell back to the minimum, so a
        panel sharing a column with a form collapsed to a strip a few pixels
        tall while the same plot on the other backend came out full height.
        pyqtgraph's ``GraphicsView`` reports 600x450; matching it is what makes
        switching backend not rearrange the window.
        """
        return QtCore.QSize(600, 450)

    def minimumSizeHint(self) -> QtCore.QSize:
        """Enough room for the axis chrome plus a usable data area.

        The old floor was a flat 50x50, which is smaller than the margins the
        ticks and labels need — the axes would draw over each other rather than
        the panel refusing to shrink.
        """
        margins = self._canvas._margins
        return QtCore.QSize(margins.left + margins.right + 60,
                            margins.top + margins.bottom + 50)

    def paintEvent(self, event):
        """Render the data area on the GPU, then draw the chrome."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing, True)
        try:
            self._canvas._paint(painter, self.width(), self.height())
        finally:
            painter.end()

    def mousePressEvent(self, event):
        """Forward to the canvas (drag a region, start a pan, or click)."""
        self._canvas._mouse_press(event)

    def mouseReleaseEvent(self, event):
        """Forward to the canvas."""
        self._canvas._mouse_release(event)

    def mouseMoveEvent(self, event):
        """Forward to the canvas."""
        self._canvas._mouse_move(event)

    def leaveEvent(self, event):
        """Drop any in-progress drag when the pointer leaves the panel."""
        self._canvas._cancel_interaction()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Reset the view to auto-range, matching the other backend."""
        self._canvas.auto_range()

    def wheelEvent(self, event):
        """Forward to the canvas."""
        self._canvas._wheel(event)

    def contextMenuEvent(self, event):
        """Ignored: the menu is raised on a right click, not by Qt's policy."""
        event.ignore()


# ---------------------------------------------------------------------------
# Single-panel canvas
# ---------------------------------------------------------------------------

class _WgpuCanvas(base.Canvas):
    """WebGPU canvas implementing the chiplot :class:`base.Canvas` contract."""

    def __init__(self, **opts):
        self._widget = _PlotWidget(self)
        self._handles: list[Any] = []
        self._view = _PixelView()
        self._margins = _Margins()
        self._renderer: _gpu.PlotRenderer | None = None
        self._render_error: str | None = None
        self._auto_range_x = True
        self._auto_range_y = True
        self._title: str | None = None
        self._xlabel: str | None = None
        self._ylabel: str | None = None
        self._rlabel: str | None = None
        self._tlabel: str | None = None
        self._show_grid_x = False
        self._show_grid_y = False
        self._grid_alpha = 0.3
        self._show_legend = False
        self._legend_offset = (8, 8)
        self._bg = S.Color(0, 0, 0)
        self._aspect_locked = False
        self._aspect_ratio = 1.0
        self._si_x = False
        self._si_y = False
        self._invert_y = False
        self._axis_visible = {"left": True, "bottom": True, "right": False, "top": False}
        self._interactive_mouse = True
        self._menu_enabled = True
        self._click_callbacks: list[Callable] = []
        self._mouse_move_callbacks: list[Callable] = []
        self._range_callbacks: list[Callable] = []
        self._menu_actions: list[tuple[str, Callable]] = []
        self._tick_spacing: dict[str, tuple[float | None, float | None]] = {}
        self._panning = False
        self._pan_start: tuple[float, float] | None = None
        self._pan_range_start = None
        self._scaling = False
        self._scale_last: tuple[float, float] | None = None
        self._scale_anchor: tuple[float, float] | None = None
        self._press_button = None
        self._press_pos: tuple[float, float] | None = None
        self._dragged = False
        self._rubber: tuple[float, float, float, float] | None = None
        self._auto_btn_rect = None
        self._drag: tuple[Any, str, float] | None = None
        self._lock = threading.RLock()
        self._linked_x: list[_WgpuCanvas] = []
        self._linked_y: list[_WgpuCanvas] = []
        self._image_buffer: np.ndarray | None = None

    # -- painting -------------------------------------------------------
    def _context(self, viewport, scale) -> _DrawContext:
        """Build the geometry context handed to each handle."""
        return _DrawContext(self._view.transform_array, viewport, scale)

    def _grid_batches(self, ctx) -> list:
        """Grid lines, as GPU geometry so they sit under the data."""
        if not (self._show_grid_x or self._show_grid_y):
            return []
        color = (*_GRID_COLOR, float(self._grid_alpha))
        segs = []
        if self._show_grid_x:
            y0, y1 = self._view.visible_range("y")
            for tv in self._tick_values("bottom"):
                segs.append(([tv, tv], [y0, y1]))
        if self._show_grid_y:
            x0, x1 = self._view.visible_range("x")
            for tv in self._tick_values("left"):
                segs.append(([x0, x1], [tv, tv]))
        if not segs:
            return []
        xs, ys = [], []
        for sx, sy in segs:
            xs.extend([*sx, np.nan])
            ys.extend([*sy, np.nan])
        nx, ny = ctx.to_ndc(np.array(xs), np.array(ys))
        tris = _gpu.expand_polyline(
            np.column_stack([nx, ny]), ctx.viewport, max(1.0 * ctx.scale, 1.0))
        return [_gpu.solid(tris, color)] if len(tris) else []

    def _build_batches(self, viewport, scale) -> list:
        """Grid plus every visible handle's geometry, in z order."""
        ctx = self._context(viewport, scale)
        out = self._grid_batches(ctx)
        with self._lock:
            ordered = sorted(self._handles, key=lambda hd: hd._z)
        for hd in ordered:
            out.extend(hd.batches(ctx))
        return out

    def _render_plot_area(self, pw: int, ph: int, dpr: float) -> np.ndarray | None:
        """Render the data area and return ``(h, w, 4)`` uint8, or ``None``."""
        if self._renderer is None:
            try:
                self._renderer = _gpu.PlotRenderer()
            except Exception as exc:  # no GPU on this machine
                self._render_error = str(exc)
                return None
        fw, fh = max(int(pw * dpr), 1), max(int(ph * dpr), 1)
        batches = self._build_batches((fw, fh), dpr)
        r, g, b, a = self._bg.as_tuple()
        return self._renderer.render(
            batches, fw, fh, (r / 255.0, g / 255.0, b / 255.0, a / 255.0))

    def _paint(self, painter: QtGui.QPainter, w: int, h: int) -> None:
        """Paint one frame: GPU image, then chrome, then text overlays."""
        if self._auto_range_x or self._auto_range_y:
            self._recompute_auto_range()
        self._measure_margins(painter, w, h)
        ix, iy, pw, ph = self._margins.plot_rect(w, h)
        dpr = float(self._widget.devicePixelRatioF())

        r, g, b, a = self._bg.as_tuple()
        painter.fillRect(QtCore.QRect(0, 0, w, h), QtGui.QColor(r, g, b, a))

        pixels = self._render_plot_area(pw, ph, dpr)
        if pixels is not None:
            self._image_buffer = pixels  # QImage does not own the bytes
            img = QtGui.QImage(
                pixels.data, pixels.shape[1], pixels.shape[0],
                pixels.strides[0], QtGui.QImage.Format_RGBA8888)
            img.setDevicePixelRatio(dpr)
            painter.drawImage(QtCore.QRectF(ix, iy, pw, ph), img,
                              QtCore.QRectF(0, 0, pixels.shape[1], pixels.shape[0]))
        elif self._render_error:
            painter.setPen(QtGui.QColor(220, 120, 120))
            painter.drawText(QtCore.QRectF(ix, iy, pw, ph), QtCore.Qt.AlignCenter,
                             f"WebGPU unavailable:\n{self._render_error}")

        self._paint_chrome(painter, w, h)
        with self._lock:
            ordered = sorted(self._handles, key=lambda hd: hd._z)
        for hd in ordered:
            if hasattr(hd, "paint_overlay"):
                hd.paint_overlay(painter, self._view, w, h, self._margins)
        if self._rubber is not None:
            x0, y0, x1, y1 = self._rubber
            band = QtCore.QRectF(min(x0, x1), min(y0, y1),
                                 abs(x1 - x0), abs(y1 - y0))
            painter.fillRect(band, QtGui.QColor(120, 170, 255, 45))
            painter.setPen(QtGui.QPen(QtGui.QColor(150, 190, 255), 1,
                                      QtCore.Qt.DashLine))
            painter.drawRect(band)
        if self._show_legend:
            self._paint_legend(painter, w, h)

    def _measure_margins(self, painter: QtGui.QPainter, w: int, h: int) -> None:
        """Size each inset from what that side actually draws.

        Every inset used to be a constant with a floor, whether or not the side
        had anything on it. A residual strip hides its bottom axis and is only
        eighty pixels tall, so a reserved 24-pixel bottom margin was a third of
        the panel spent on nothing — and a stack of them turned into the band of
        empty space between plots. Measure the text instead: a hidden axis costs
        a couple of pixels of breathing room and no more.
        """
        tick_fm = QtGui.QFontMetrics(S.chrome_font("tick"))
        label_fm = QtGui.QFontMetrics(S.chrome_font("label"))

        if self._axis_visible.get("left", True):
            labels = self._tick_labels("left")
            widest = max((tick_fm.horizontalAdvance(t) for t in labels), default=0)
            left = widest + _TICK_GAP + _TICK_LEN
        else:
            left = _EDGE_PAD
        if self._ylabel:
            left += label_fm.height() + 2
        self._margins.left = int(max(left, _EDGE_PAD))

        if self._axis_visible.get("bottom", True):
            bottom = tick_fm.height() + _TICK_GAP + _TICK_LEN
        else:
            bottom = _EDGE_PAD
        if self._xlabel:
            bottom += label_fm.height() + 2
        self._margins.bottom = int(bottom)

        self._margins.top = int(_EDGE_PAD + (label_fm.height() + 4 if self._title else 0))
        self._margins.right = int(_EDGE_PAD)

    def _tick_values(self, side: str) -> list[float]:
        """Return the tick positions for one axis."""
        horizontal = side in ("bottom", "top")
        # The *sanitised* range, so the ticks describe the axis the geometry is
        # actually drawn against.
        lo, hi = self._view.visible_range("x" if horizontal else "y")
        log = self._view.log_x if horizontal else self._view.log_y
        spacing = self._tick_spacing.get(side)
        if spacing and spacing[0]:
            step = float(spacing[0])
            out, v, guard = [], math.ceil(lo / step) * step, 0
            while v <= hi + step * 1e-3 and guard < 1000:
                out.append(v)
                v += step
                guard += 1
            return out
        if log:
            return log_ticks(lo, hi)
        w, h = self._widget.width(), self._widget.height()
        _, _, pw, ph = self._margins.plot_rect(w, h)
        extent = pw if horizontal else ph
        return nice_ticks(lo, hi, max(int(extent / (70 if horizontal else 45)), 2))

    def _tick_labels(self, side: str) -> list[str]:
        """Return the formatted labels for one axis."""
        ticks = self._tick_values(side)
        log = self._view.log_y if side in ("left", "right") else self._view.log_x
        step = (ticks[1] - ticks[0]) if len(ticks) > 1 else 0.0
        return [format_tick(t, step, log=log) for t in ticks]

    def _paint_chrome(self, painter: QtGui.QPainter, w: int, h: int) -> None:
        """Draw the frame, ticks, tick labels, axis labels and title."""
        ix, iy, pw, ph = self._margins.plot_rect(w, h)
        painter.setPen(QtGui.QPen(_AXIS_COLOR, 1))
        painter.drawRect(QtCore.QRectF(ix + 0.5, iy + 0.5, pw - 1, ph - 1))

        font = S.chrome_font("tick")
        painter.setFont(font)
        fm = painter.fontMetrics()

        if self._axis_visible.get("bottom", True):
            ticks = self._tick_values("bottom")
            labels = self._tick_labels("bottom")
            last_right = -1e9
            for tv, label in zip(ticks, labels):
                px, _ = self._view.data_to_pixel(tv, self._view.y_range[0], w, h,
                                                 self._margins)
                if not math.isfinite(px) or px < ix - 1 or px > ix + pw + 1:
                    continue
                painter.drawLine(QtCore.QPointF(px, iy + ph),
                                 QtCore.QPointF(px, iy + ph + 4))
                tw = fm.horizontalAdvance(label)
                if px - tw / 2 < last_right + 4:
                    continue  # never overprint the previous label
                last_right = px + tw / 2
                painter.drawText(
                    QtCore.QRectF(px - tw / 2 - 2, iy + ph + 5, tw + 4, fm.height()),
                    QtCore.Qt.AlignCenter, label)

        if self._axis_visible.get("left", True):
            ticks = self._tick_values("left")
            labels = self._tick_labels("left")
            last_top = 1e9
            for tv, label in zip(ticks, labels):
                _, py = self._view.data_to_pixel(self._view.x_range[0], tv, w, h,
                                                 self._margins)
                if not math.isfinite(py) or py < iy - 1 or py > iy + ph + 1:
                    continue
                painter.drawLine(QtCore.QPointF(ix - 4, py), QtCore.QPointF(ix, py))
                tw = fm.horizontalAdvance(label)
                if py + fm.height() / 2 > last_top - 2:
                    continue
                last_top = py - fm.height() / 2
                painter.drawText(
                    QtCore.QRectF(ix - tw - 7, py - fm.height() / 2, tw, fm.height()),
                    QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, label)

        # pyqtgraph's little corner button, and for the same reason: a view
        # panned or zoomed away from the data needs one obvious way back, and
        # "double-click somewhere" is not discoverable.
        size, inset = _AUTO_BTN_SIZE, _AUTO_BTN_INSET
        self._auto_btn_rect = QtCore.QRectF(
            ix + inset, iy + ph - size - inset, size, size)
        painter.setPen(QtGui.QPen(_AXIS_COLOR, 1))
        painter.setBrush(QtGui.QColor(0, 0, 0, 110))
        painter.drawRoundedRect(self._auto_btn_rect, 3, 3)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setFont(S.chrome_font("tick"))
        painter.drawText(self._auto_btn_rect, QtCore.Qt.AlignCenter, "A")

        font = S.chrome_font("label")
        painter.setFont(font)
        if self._xlabel:
            painter.drawText(QtCore.QRectF(ix, h - 19, pw, 18),
                             QtCore.Qt.AlignCenter, self._xlabel)
        if self._ylabel:
            painter.save()
            painter.translate(11, iy + ph / 2)
            painter.rotate(-90)
            painter.drawText(QtCore.QRectF(-ph / 2, -9, ph, 18),
                             QtCore.Qt.AlignCenter, self._ylabel)
            painter.restore()
        if self._title:
            painter.setFont(S.chrome_font("title", bold=True))
            painter.drawText(QtCore.QRectF(ix, 2, pw, self._margins.top - 2),
                             QtCore.Qt.AlignCenter, self._title)

    def _legend_entries(self) -> list[tuple[str, S.Color]]:
        """Return ``(name, colour)`` for every named handle."""
        out = []
        with self._lock:
            for hd in self._handles:
                name = getattr(hd, "_name", None)
                if not name or not getattr(hd, "_visible", True):
                    continue
                pen = getattr(hd, "_pen", None)
                brush = getattr(hd, "_brush", None)
                color = (pen.color if pen is not None else
                         brush.color if brush is not None else S.Color(255, 255, 255))
                out.append((str(name), color))
        return out

    def _paint_legend(self, painter: QtGui.QPainter, w: int, h: int) -> None:
        """Draw a legend box inside the top-right of the plot area."""
        entries = self._legend_entries()
        if not entries:
            return
        ix, iy, pw, ph = self._margins.plot_rect(w, h)
        painter.setFont(S.chrome_font("legend"))
        fm = painter.fontMetrics()
        row = fm.height() + 3
        text_w = max(fm.horizontalAdvance(n) for n, _ in entries)
        bw, bh = text_w + 34, row * len(entries) + 8
        ox, oy = self._legend_offset
        x0 = ix + pw - bw - ox
        y0 = iy + oy
        painter.fillRect(QtCore.QRectF(x0, y0, bw, bh), QtGui.QColor(0, 0, 0, 140))
        painter.setPen(QtGui.QPen(_AXIS_COLOR, 1))
        painter.drawRect(QtCore.QRectF(x0 + 0.5, y0 + 0.5, bw - 1, bh - 1))
        for i, (name, color) in enumerate(entries):
            cy = y0 + 4 + i * row + row / 2
            r, g, b, a = color.as_tuple()
            painter.setPen(QtGui.QPen(QtGui.QColor(r, g, b, a), 2))
            painter.drawLine(QtCore.QPointF(x0 + 6, cy), QtCore.QPointF(x0 + 24, cy))
            painter.setPen(_AXIS_COLOR)
            painter.drawText(QtCore.QRectF(x0 + 29, y0 + 4 + i * row, text_w + 4, row),
                             QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, name)

    # -- auto range -----------------------------------------------------
    def _recompute_auto_range(self) -> None:
        """Fit the view to the visible handles' data."""
        all_x, all_y = [], []
        with self._lock:
            handles = list(self._handles)
        for hd in handles:
            if not getattr(hd, "_visible", True):
                continue
            xs, ys = self._handle_data_range(hd)
            if xs is not None:
                all_x.append(xs)
            if ys is not None:
                all_y.append(ys)
        if self._auto_range_x and all_x:
            lo, hi = min(r[0] for r in all_x), max(r[1] for r in all_x)
            self._view.x_range = self._padded(
                *self._clip_log_floor(lo, hi, self._view.log_x), self._view.log_x)
        if self._auto_range_y and all_y:
            lo, hi = min(r[0] for r in all_y), max(r[1] for r in all_y)
            self._view.y_range = self._padded(
                *self._clip_log_floor(lo, hi, self._view.log_y), self._view.log_y)

    @staticmethod
    def _clip_log_floor(lo: float, hi: float, log: bool) -> tuple[float, float]:
        """Keep a log auto-range from chasing numerical noise to the floor.

        A convolved decay does not stop at the last real count: it trails off
        through denormals to ~1e-300, and those samples are positive, so an
        honest min/max spans three hundred decades and squashes the data into
        the top two pixels. No detector has that dynamic range — the tail is
        arithmetic, not measurement. Anything more than
        :data:`_AUTORANGE_DECADES` below the peak is dropped from the fit; the
        user can still pan or zoom down to it.
        """
        if not log or not (hi > 0):
            return lo, hi
        return max(lo, hi * 10.0 ** -_AUTORANGE_DECADES), hi

    @staticmethod
    def _padded(lo: float, hi: float, log: bool) -> list[float]:
        """Add 5 % headroom, in the axis's own space."""
        if not (math.isfinite(lo) and math.isfinite(hi)):
            return [0.0, 1.0]
        if log:
            lo = max(lo, 1e-300)
            hi = max(hi, lo * 10.0)
            llo, lhi = math.log10(lo), math.log10(hi)
            pad = max((lhi - llo) * 0.05, 0.05)
            return [10.0 ** (llo - pad), 10.0 ** (lhi + pad)]
        if lo == hi:
            return [lo - 0.5, hi + 0.5]
        pad = (hi - lo) * 0.05
        return [lo - pad, hi + pad]

    def _handle_data_range(self, hd):
        """Return ``(x_range, y_range)`` covered by one handle."""
        log_y, log_x = self._view.log_y, self._view.log_x
        if isinstance(hd, (_handles._Curve, _handles._Scatter)):
            xs, ys = np.asarray(hd._x, float), np.asarray(hd._y, float)
            n = min(len(xs), len(ys))
            xs, ys = xs[:n], ys[:n]
            mask = np.isfinite(xs) & np.isfinite(ys)
            # A log axis cannot show a non-positive sample, and letting one into
            # the auto-range collapses the whole decade span onto the top edge.
            if log_x:
                mask &= xs > 0
            if log_y:
                mask &= ys > 0
            if mask.any():
                return ((float(xs[mask].min()), float(xs[mask].max())),
                        (float(ys[mask].min()), float(ys[mask].max())))
        elif isinstance(hd, _handles._Bars):
            if len(hd._x):
                w = np.broadcast_to(np.asarray(hd._width, float), hd._x.shape)
                heights = np.asarray(hd._height, float)
                heights = heights[np.isfinite(heights)]
                top = float(heights.max()) if heights.size else 1.0
                base = 0.0 if not log_y else max(float(top) * 1e-4, 1e-12)
                return ((float((hd._x - w / 2).min()), float((hd._x + w / 2).max())),
                        (base, top))
        elif isinstance(hd, _handles._Image):
            x, y, w, h = hd._rect
            return (float(x), float(x + w)), (float(y), float(y + h))
        elif isinstance(hd, _handles._ErrorBars) and len(hd._x):
            return ((float(np.nanmin(hd._x)), float(np.nanmax(hd._x))),
                    (float(np.nanmin(hd._bottom)), float(np.nanmax(hd._top))))
        return None, None

    def _y_baseline(self) -> float:
        """Return the y value that bars and fills are drawn down to."""
        if self._view.log_y:
            return max(self._view.y_range[0], 1e-300)
        return min(0.0, self._view.y_range[0]) if self._view.y_range[0] > 0 else \
            self._view.y_range[0]

    # -- interaction ----------------------------------------------------
    @staticmethod
    def _event_pos(event) -> tuple[float, float]:
        """Return the event position, across Qt bindings."""
        try:
            p = event.position()
            return p.x(), p.y()
        except AttributeError:
            return float(event.x()), float(event.y())

    def _update_hover(self, px: float, py: float) -> bool:
        """Mark the draggable part under the pointer; return whether it moved.

        pyqtgraph highlights what a press would grab — the line under the
        cursor turns red and a region's band brightens — and that is the only
        thing telling a user an edge is draggable at all. Nothing is highlighted
        mid-drag: the answer is already known then.
        """
        target, part = (None, None)
        if self._drag is None and not self._panning and not self._scaling:
            target, part = self._hit_draggable(px, py)
        changed = False
        with self._lock:
            handles = list(self._handles)
        for hd in handles:
            setter = getattr(hd, "set_hover", None)
            if setter is None:
                continue
            changed |= bool(setter(part if hd is target else None))
        return changed

    def _cancel_interaction(self) -> None:
        """Forget any in-progress press, drag, pan, scale or rubber band.

        Called whenever the panel can no longer trust that it will see the
        matching release — the pointer leaving, or a move arriving with no
        button held. Without it a swallowed release leaves the panel scaling
        for the rest of the session: the context menu used to run modally from
        the *press*, so the release went to the menu and every later mouse move
        went on zooming.
        """
        self._panning = False
        self._pan_start = None
        self._pan_range_start = None
        self._scaling = False
        self._scale_last = None
        self._scale_anchor = None
        self._press_button = None
        self._press_pos = None
        self._dragged = False
        if self._rubber is not None:
            self._rubber = None
            self._widget.update()
        if self._drag is not None:
            self._drag = None
        with self._lock:
            handles = list(self._handles)
        for hd in handles:
            setter = getattr(hd, "set_hover", None)
            if setter is not None:
                setter(None)

    def _hit_draggable(self, px: float, py: float):
        """Return ``(handle, part)`` for a draggable edge under the pointer."""
        w, h = self._widget.width(), self._widget.height()
        with self._lock:
            handles = list(self._handles)
        for hd in reversed(handles):
            if not getattr(hd, "_visible", True) or not getattr(hd, "_movable", False):
                continue
            if isinstance(hd, _handles._Region):
                lo, hi = sorted(hd._bounds)
                vertical = hd._orientation is H.Orientation.VERTICAL
                for part, value in (("low", lo), ("high", hi)):
                    ex, ey = self._view.data_to_pixel(
                        value if vertical else self._view.x_range[0],
                        self._view.y_range[0] if vertical else value, w, h, self._margins)
                    if abs((ex if vertical else ey) - (px if vertical else py)) <= _GRAB_PX:
                        return hd, part
                a, b = self._view.data_to_pixel(
                    lo if vertical else self._view.x_range[0],
                    self._view.y_range[0] if vertical else lo, w, h, self._margins)
                c, d = self._view.data_to_pixel(
                    hi if vertical else self._view.x_range[1],
                    self._view.y_range[1] if vertical else hi, w, h, self._margins)
                inside = (min(a, c) <= px <= max(a, c)) if vertical else \
                    (min(b, d) <= py <= max(b, d))
                if inside:
                    return hd, "body"
            elif isinstance(hd, _handles._Marker):
                vertical = hd._orientation is H.Orientation.VERTICAL
                ex, ey = self._view.data_to_pixel(
                    hd._value if vertical else self._view.x_range[0],
                    self._view.y_range[0] if vertical else hd._value, w, h, self._margins)
                if abs((ex if vertical else ey) - (px if vertical else py)) <= _GRAB_PX:
                    return hd, "value"
        return None, None

    def _left_button_pans(self) -> bool:
        """Whether a left drag pans, or draws a zoom rectangle.

        The same preference the other backend reads, so the two renderers do
        not answer the same gesture differently.
        """
        try:
            from chisurf.core.settings import cs_settings

            cfg = cs_settings.get("gui", {}).get("plot", {}).get("pyqtgraph_config", {})
            return bool(cfg.get("leftButtonPan", True))
        except Exception:
            return True

    @staticmethod
    def _is_view_drag_button(button) -> bool:
        """Whether a button drives the view's pan / zoom-rectangle gesture.

        Left **and middle**, exactly as pyqtgraph has it: its ``ViewBox``
        handles the two in one branch, and its ``GraphicsView`` pans on either.
        The middle button is how a user pans without giving up a left-drag
        that has been rebound to a zoom rectangle.
        """
        return button in (QtCore.Qt.LeftButton, QtCore.Qt.MiddleButton)

    def _mouse_press(self, event):
        """Route a press: the corner button, a draggable handle, pan, or scale.

        The button semantics are pyqtgraph's, because that is what the hands
        using this application already know: left and middle drag the view
        (pan, or a zoom rectangle under the ``leftButtonPan`` preference),
        right drags scale about the point it started from, and the wheel zooms
        about the cursor. Only the *left* button grabs a region, a marker or
        the corner button — pyqtgraph's items ignore the middle one, so a
        middle drag pans across a fit range instead of moving it.
        """
        px, py = self._event_pos(event)
        w, h = self._widget.width(), self._widget.height()

        if event.button() == QtCore.Qt.LeftButton and self._auto_btn_rect is not None:
            if self._auto_btn_rect.contains(QtCore.QPointF(px, py)):
                self.auto_range()
                return

        self._press_button = event.button()
        self._press_pos = (px, py)
        self._dragged = False

        if event.button() == QtCore.Qt.RightButton:
            # Recorded, not started. A right button that never moves is a
            # click and raises the menu; one that moves is a scale drag. That
            # is pyqtgraph's distinction, and making it here is what stops a
            # menu from opening in the middle of a drag.
            if self._interactive_mouse:
                self._scale_last = (px, py)
                self._scale_anchor = self._view.pixel_to_data(
                    px, py, w, h, self._margins)
            return

        if not self._is_view_drag_button(event.button()):
            return

        if event.button() == QtCore.Qt.LeftButton:
            dx, dy = self._view.pixel_to_data(px, py, w, h, self._margins)
            hd, part = self._hit_draggable(px, py)
            if hd is not None:
                anchor = (dx if getattr(hd, "_orientation", None) is H.Orientation.VERTICAL
                          else dy)
                self._drag = (hd, part, anchor)
                return
        if not self._interactive_mouse:
            return
        if self._left_button_pans():
            self._panning = True
            self._pan_start = (px, py)
            self._pan_range_start = (list(self._view.x_range), list(self._view.y_range))
        else:
            self._rubber = (px, py, px, py)

    def _mouse_release(self, event):
        """Finish a scale, a zoom rectangle, a handle drag, or a pan."""
        px, py = self._event_pos(event)
        if event.button() == QtCore.Qt.RightButton:
            was_drag = self._dragged
            self._scaling = False
            self._scale_last = None
            self._scale_anchor = None
            self._press_button = None
            self._press_pos = None
            self._dragged = False
            if not was_drag:
                self._raise_context_menu(event, px, py)
            return
        if not self._is_view_drag_button(event.button()):
            return
        self._press_button = None
        self._press_pos = None
        self._dragged = False
        if self._rubber is not None:
            band, self._rubber = self._rubber, None
            self._apply_rubber_band(band)
            self._widget.update()
            return
        if self._drag is not None:
            hd, _, _ = self._drag
            self._drag = None
            hd._fire(final=True)
            return
        if self._panning:
            self._panning = False
            if self._pan_start:
                moved = (abs(px - self._pan_start[0]) >= 3
                         or abs(py - self._pan_start[1]) >= 3)
                if not moved:
                    w, h = self._widget.width(), self._widget.height()
                    dx, dy = self._view.pixel_to_data(px, py, w, h, self._margins)
                    name = ("middle" if event.button() == QtCore.Qt.MiddleButton
                            else "left")
                    for cb in self._click_callbacks:
                        cb(dx, dy, name)

    def _apply_rubber_band(self, band) -> None:
        """Set the view to a dragged rectangle, ignoring an accidental flick."""
        x0, y0, x1, y1 = band
        if abs(x1 - x0) < 4 or abs(y1 - y0) < 4:
            return
        w, h = self._widget.width(), self._widget.height()
        a = self._view.pixel_to_data(min(x0, x1), max(y0, y1), w, h, self._margins)
        b = self._view.pixel_to_data(max(x0, x1), min(y0, y1), w, h, self._margins)
        self.set_range(x=(a[0], b[0]), y=(a[1], b[1]))

    def _mouse_move(self, event):
        """Report the cursor position, and drag whatever is grabbed."""
        px, py = self._event_pos(event)

        # A move with nothing held means the press this panel is still tracking
        # ended somewhere it could not see — a modal menu, another widget, a
        # window switch. Anything else leaves the panel dragging forever.
        try:
            buttons = event.buttons()
        except Exception:
            buttons = None
        if buttons is not None and buttons == QtCore.Qt.NoButton:
            if (self._panning or self._scaling or self._rubber is not None
                    or self._drag is not None or self._press_button is not None):
                self._cancel_interaction()

        if (self._press_pos is not None and not self._dragged
                and (abs(px - self._press_pos[0]) >= _DRAG_PX
                     or abs(py - self._press_pos[1]) >= _DRAG_PX)):
            self._dragged = True
            if self._press_button == QtCore.Qt.RightButton and self._interactive_mouse:
                self._scaling = True
        w, h = self._widget.width(), self._widget.height()
        dx, dy = self._view.pixel_to_data(px, py, w, h, self._margins)
        for cb in self._mouse_move_callbacks:
            cb(dx, dy)

        if self._scaling and self._scale_last is not None:
            lx, ly = self._scale_last
            self._scale_last = (px, py)
            # pyqtgraph's right-drag: 1.02 per pixel, x inverted, anchored at
            # the point the drag started from so that point stays put.
            sx = 1.02 ** -(px - lx)
            sy = 1.02 ** (py - ly)
            ax, ay = self._scale_anchor or (dx, dy)
            self._view.x_range = self._zoom(self._view.x_range, ax, sx, self._view.log_x)
            self._view.y_range = self._zoom(self._view.y_range, ay, sy, self._view.log_y)
            self._auto_range_x = self._auto_range_y = False
            self._fire_range_changed()
            self._widget.update()
            return

        if self._rubber is not None:
            x0, y0, _, _ = self._rubber
            self._rubber = (x0, y0, px, py)
            self._widget.update()
            return

        if self._update_hover(px, py):
            self._widget.update()

        if self._drag is not None:
            hd, part, anchor = self._drag
            vertical = getattr(hd, "_orientation", None) is H.Orientation.VERTICAL
            value = dx if vertical else dy
            if isinstance(hd, _handles._Marker):
                hd._value = value
            elif part == "body":
                delta = value - anchor
                hd._bounds = [hd._bounds[0] + delta, hd._bounds[1] + delta]
                self._drag = (hd, part, value)
            else:
                lo, hi = hd._bounds
                hd._bounds = [value, hi] if part == "low" else [lo, value]
            if getattr(hd, "_limits", None):
                lim_lo, lim_hi = hd._limits
                if isinstance(hd, _handles._Marker):
                    hd._value = min(max(hd._value, lim_lo), lim_hi)
                else:
                    hd._bounds = [min(max(v, lim_lo), lim_hi) for v in hd._bounds]
            hd._fire(final=False)
            self._widget.update()
            return

        if self._panning and self._pan_start and self._interactive_mouse:
            sx, sy = self._pan_start
            _, _, pw, ph = self._margins.plot_rect(w, h)
            xr0, yr0 = self._pan_range_start
            self._view.x_range = self._shift(xr0, -(px - sx) / max(pw, 1),
                                             self._view.log_x)
            self._view.y_range = self._shift(yr0, (py - sy) / max(ph, 1),
                                             self._view.log_y)
            self._auto_range_x = self._auto_range_y = False
            self._fire_range_changed()
            self._widget.update()

    @staticmethod
    def _shift(rng, fraction: float, log: bool) -> list[float]:
        """Translate a range by a fraction of its span, log-aware."""
        if log:
            lo, hi = math.log10(max(rng[0], 1e-300)), math.log10(max(rng[1], 1e-299))
            d = (hi - lo) * fraction
            return [_pow10(lo + d), _pow10(hi + d)]
        d = (rng[1] - rng[0]) * fraction
        return [rng[0] + d, rng[1] + d]

    def _wheel(self, event):
        """Zoom about the pointer."""
        if not self._interactive_mouse:
            return
        delta = event.angleDelta().y()
        factor = 1.0 / 1.15 if delta > 0 else 1.15
        px, py = self._event_pos(event)
        w, h = self._widget.width(), self._widget.height()
        mx, my = self._view.pixel_to_data(px, py, w, h, self._margins)
        self._view.x_range = self._zoom(self._view.x_range, mx, factor, self._view.log_x)
        self._view.y_range = self._zoom(self._view.y_range, my, factor, self._view.log_y)
        self._auto_range_x = self._auto_range_y = False
        self._fire_range_changed()
        self._widget.update()

    @staticmethod
    def _zoom(rng, center: float, factor: float, log: bool) -> list[float]:
        """Scale a range about *center*, log-aware."""
        if log:
            lo, hi = math.log10(max(rng[0], 1e-300)), math.log10(max(rng[1], 1e-299))
            c = math.log10(max(center, 1e-300))
            # Zooming out multiplies the decade span every notch, so an
            # unclamped 10 ** ... stops being a float after about thirty of them.
            return [_pow10(c + (lo - c) * factor), _pow10(c + (hi - c) * factor)]
        return [center + (rng[0] - center) * factor,
                center + (rng[1] - center) * factor]

    @staticmethod
    def _global_pos(event, widget, px: float, py: float):
        """Return the event's screen position, across Qt bindings."""
        for name in ("globalPosition", "globalPos"):
            getter = getattr(event, name, None)
            if getter is None:
                continue
            try:
                value = getter()
            except Exception:
                continue
            return value.toPoint() if hasattr(value, "toPoint") else value
        return widget.mapToGlobal(QtCore.QPoint(int(px), int(py)))

    def _raise_context_menu(self, event, px: float, py: float) -> None:
        """Show the menu for a right *click*, the way pyqtgraph does.

        Raised from the release, and only when the press did not turn into a
        drag — a menu that opens from the press runs modally and eats the
        release, which left the panel scaling for good.
        """
        if not self._menu_enabled:
            return
        global_pos = self._global_pos(event, self._widget, px, py)
        parent = self._widget.parent()
        while parent is not None:
            if hasattr(parent, "contextMenuEvent") and hasattr(parent, "_series"):
                menu_event = QtGui.QContextMenuEvent(
                    QtGui.QContextMenuEvent.Mouse,
                    QtCore.QPoint(int(px), int(py)), global_pos)
                parent.contextMenuEvent(menu_event)
                return
            parent = parent.parent()
        self._context_menu(global_pos)

    def _context_menu(self, global_pos):
        """Show the backend's own menu (used when no chiplot Plot hosts us)."""
        if not self._menu_enabled:
            return
        if hasattr(global_pos, "globalPos"):  # an event was passed
            global_pos = global_pos.globalPos()
        menu = QtWidgets.QMenu(self._widget)
        for label, cb in self._menu_actions:
            menu.addAction(label).triggered.connect(cb)
        if self._menu_actions:
            menu.addSeparator()
        menu.addAction("Auto range").triggered.connect(self.auto_range)
        menu.exec_(global_pos)

    def _fire_range_changed(self):
        """Notify listeners and propagate to linked panels."""
        for cb in self._range_callbacks:
            cb(tuple(self._view.x_range), tuple(self._view.y_range))
        for other in self._linked_x:
            if list(other._view.x_range) != list(self._view.x_range):
                other._view.x_range = list(self._view.x_range)
                other._auto_range_x = False
                other._widget.update()
        for other in self._linked_y:
            if list(other._view.y_range) != list(self._view.y_range):
                other._view.y_range = list(self._view.y_range)
                other._auto_range_y = False
                other._widget.update()

    # -- internal -------------------------------------------------------
    def _request_update(self):
        """Schedule a repaint."""
        self._widget.update()

    def _remove_handle(self, handle):
        """Drop a handle from the draw list."""
        with self._lock:
            if handle in self._handles:
                self._handles.remove(handle)
        self._widget.update()

    def _add(self, handle):
        """Append a handle and repaint."""
        with self._lock:
            self._handles.append(handle)
        self._widget.update()
        return handle

    # -- Canvas contract: widget ---------------------------------------
    def widget(self) -> QtWidgets.QWidget:
        """Return the Qt widget hosting this canvas."""
        return self._widget

    # -- Canvas contract: drawing --------------------------------------
    def add_curve(self, x, y, *, pen, name=None, fill=None, step=False,
                  symbol=None, symbol_size=7.0, symbol_brush=None,
                  symbol_pen=None, skip_missing=True) -> H.Curve:
        """Add a line/step curve."""
        return self._add(_handles._Curve(
            self, x, y, pen=pen, name=name, fill=fill, step=step, symbol=symbol,
            symbol_size=symbol_size, symbol_brush=symbol_brush,
            symbol_pen=symbol_pen, skip_missing=skip_missing))

    def add_scatter(self, x, y, *, size, pen, brush, symbol, name=None) -> H.Scatter:
        """Add a scatter cloud."""
        return self._add(_handles._Scatter(
            self, x, y, size=size, pen=pen, brush=brush, symbol=symbol, name=name))

    def add_bars(self, x, height, *, width, pen, brush) -> H.Bars:
        """Add a bar graph."""
        return self._add(_handles._Bars(
            self, x, height, width=width, pen=pen, brush=brush))

    def add_fill_between(self, lower, upper, *, brush) -> H.Handle:
        """Fill the band between two curves."""
        return self._add(_handles._FillBetween(self, lower, upper, brush=brush))

    def add_errorbars(self, x, y, *, height=None, top=None, bottom=None,
                      pen, beam=None) -> H.ErrorBars:
        """Add vertical error bars."""
        return self._add(_handles._ErrorBars(
            self, x, y, height=height, top=top, bottom=bottom, pen=pen, beam=beam))

    def add_image(self, data, *, colormap=None, levels=None, rect=None,
                  axis_order="row-major") -> H.Image:
        """Add a 2-D image / heatmap."""
        return self._add(_handles._Image(
            self, data, colormap=colormap, levels=levels, rect=rect,
            axis_order=axis_order))

    def add_region(self, bounds, *, orientation, movable, brush, pen) -> H.Region:
        """Add a draggable interval band."""
        return self._add(_handles._Region(
            self, bounds, orientation=orientation, movable=movable,
            brush=brush, pen=pen))

    def add_roi(self, *, kind="rect", pos=(0.0, 0.0), size=(10.0, 10.0),
                pen: S.Pen, movable=True, rotatable=False, points=None) -> H.Roi:
        """Add a region of interest."""
        return self._add(_handles._Roi(
            self, kind=kind, pos=pos, size=size, pen=pen, movable=movable,
            rotatable=rotatable, points=points))

    def add_marker(self, pos, *, orientation, movable, pen, label=None) -> H.Marker:
        """Add a movable infinite line."""
        return self._add(_handles._Marker(
            self, pos, orientation=orientation, movable=movable, pen=pen, label=label))

    def add_arrow(self, pos, *, angle, size=20.0, tip_angle=25.0,
                  head_width=None, tail_length=None, tail_width=2.0,
                  pen=None, brush=None) -> H.Arrow:
        """Add an arrow head at a data coordinate."""
        return self._add(_handles._Arrow(
            self, pos, angle=angle, size=size, tip_angle=tip_angle,
            head_width=head_width, tail_length=tail_length,
            tail_width=tail_width, pen=pen, brush=brush))

    def add_text(self, text, pos, *, color, anchor=(0.0, 0.0), draggable=False,
                 fill=None, border=None, anchored=False) -> H.Text:
        """Add a text label."""
        return self._add(_handles._Text(
            self, text, pos, color=color, anchor=anchor, draggable=draggable,
            fill=fill, border=border, anchored=anchored))

    def add_legend(self, *, offset=(5, 5)) -> None:
        """Show a legend listing the named handles."""
        self._show_legend = True
        self._legend_offset = offset
        self._widget.update()

    def readd(self, handle) -> None:
        """Put a removed handle back."""
        with self._lock:
            if handle not in self._handles:
                self._handles.append(handle)
        self._widget.update()

    def remove(self, handle) -> None:
        """Remove a handle."""
        self._remove_handle(handle)

    def clear(self) -> None:
        """Remove every handle."""
        with self._lock:
            self._handles.clear()
        self._widget.update()

    # -- Canvas contract: axes / view ----------------------------------
    def set_labels(self, *, left=None, bottom=None, right=None, top=None) -> None:
        """Set the axis labels."""
        if left is not None:
            self._ylabel = left
        if bottom is not None:
            self._xlabel = bottom
        if right is not None:
            self._rlabel = right
        if top is not None:
            self._tlabel = top
        self._widget.update()

    def set_title(self, title) -> None:
        """Set the panel title."""
        self._title = title
        self._widget.update()

    def set_log(self, *, x=None, y=None) -> None:
        """Switch either axis to a logarithmic scale."""
        if x is not None:
            self._view.log_x = bool(x)
        if y is not None:
            self._view.log_y = bool(y)
        self._recompute_auto_range()
        self._widget.update()

    def set_tick_spacing(self, side, *, major=None, minor=None) -> None:
        """Force the tick interval on one axis."""
        self._tick_spacing[side] = (major, minor)
        self._widget.update()

    def on_range_changed(self, callback) -> None:
        """Register a callback for view-range changes."""
        self._range_callbacks.append(callback)

    def set_range(self, *, x=None, y=None, padding=None) -> None:
        """Set the visible data range."""
        if x is not None:
            self._view.x_range = list(x)
            self._auto_range_x = False
        if y is not None:
            self._view.y_range = list(y)
            self._auto_range_y = False
        self._fire_range_changed()
        self._widget.update()

    def get_range(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Return the visible ``((x0, x1), (y0, y1))`` range."""
        return tuple(self._view.x_range), tuple(self._view.y_range)

    def auto_range(self) -> None:
        """Fit the view to the data."""
        self._auto_range_x = self._auto_range_y = True
        self._recompute_auto_range()
        self._fire_range_changed()
        self._widget.update()

    def enable_auto_range(self, *, x=True, y=True) -> None:
        """Enable or disable automatic ranging per axis."""
        self._auto_range_x = x
        self._auto_range_y = y

    def set_grid(self, *, x=False, y=False, alpha=0.3) -> None:
        """Show grid lines."""
        self._show_grid_x = x
        self._show_grid_y = y
        self._grid_alpha = alpha
        self._widget.update()

    def set_background(self, color) -> None:
        """Set the panel background colour."""
        if color is None:
            self._bg = S.Color(0, 0, 0, 0)
        else:
            self._bg = color if isinstance(color, S.Color) else S.to_color(color)
        self._widget.update()

    def set_aspect_locked(self, lock, ratio=1.0) -> None:
        """Lock the data aspect ratio."""
        self._aspect_locked = lock
        self._aspect_ratio = ratio

    def set_si_prefix(self, *, x=None, y=None) -> None:
        """Enable/disable SI-prefixed tick labels."""
        if x is not None:
            self._si_x = x
        if y is not None:
            self._si_y = y
        self._widget.update()

    def invert_y(self, invert=True) -> None:
        """Draw the y axis increasing downwards."""
        self._invert_y = invert
        self._view.invert_y = bool(invert)
        self._widget.update()

    def set_axis_visible(self, side, visible) -> None:
        """Show or hide one axis's chrome."""
        self._axis_visible[side] = visible
        self._widget.update()

    def link_x(self, other) -> None:
        """Share the x range with another panel."""
        if isinstance(other, _WgpuCanvas) and other not in self._linked_x:
            self._linked_x.append(other)
            other._linked_x.append(self)

    def link_y(self, other) -> None:
        """Share the y range with another panel."""
        if isinstance(other, _WgpuCanvas) and other not in self._linked_y:
            self._linked_y.append(other)
            other._linked_y.append(self)

    def set_downsampling(self, *, auto: bool = True, mode: str = "peak") -> None:
        """Accept and ignore; see :meth:`._handles._Curve.set_downsampling`."""

    def set_clip_to_view(self, clip: bool = True) -> None:
        """Accept and ignore; see :meth:`._handles._Curve.set_clip_to_view`."""

    def set_menu_enabled(self, enabled) -> None:
        """Enable or disable the context menu."""
        self._menu_enabled = enabled

    def menu_enabled(self) -> bool:
        """Whether the context menu is enabled."""
        return self._menu_enabled

    def set_interactive(self, *, mouse=True, menu=True) -> None:
        """Enable or disable mouse interaction and the context menu."""
        self._interactive_mouse = mouse
        self._menu_enabled = menu

    def provides_native_menu(self) -> bool:
        """Whether the renderer supplies its own context menu."""
        return False

    def add_menu_action(self, label, callback) -> None:
        """Add an entry to the context menu."""
        self._menu_actions.append((label, callback))

    def export_image(self, path, *, width=None) -> bool:
        """Write the panel to an image file, optionally at a different width.

        The export re-renders rather than screen-grabbing, so a figure for a
        paper is not limited to the pixels the panel happened to occupy.
        """
        w = int(width) if width else self._widget.width()
        h = max(int(round(w * self._widget.height() / max(self._widget.width(), 1))), 1)
        image = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32)
        r, g, b, a = self._bg.as_tuple()
        image.fill(QtGui.QColor(r, g, b, a))
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        try:
            self._paint(painter, w, h)
        finally:
            painter.end()
        return bool(image.save(str(path)))

    # -- Canvas contract: events ---------------------------------------
    def on_click(self, callback) -> None:
        """Register a click callback ``(x, y, button)``."""
        self._click_callbacks.append(callback)

    def on_mouse_move(self, callback) -> None:
        """Register a cursor-move callback ``(x, y)``."""
        self._mouse_move_callbacks.append(callback)

    @property
    def native(self):
        """The Qt widget — this backend has no renderer-level plot object."""
        return self._widget


# ---------------------------------------------------------------------------
# Grid canvas
# ---------------------------------------------------------------------------

class _WgpuGrid(base.GridCanvas):
    """A grid of :class:`_WgpuCanvas` panels."""

    def __init__(self, **opts):
        self._widget = QtWidgets.QWidget()
        self._layout = QtWidgets.QGridLayout(self._widget)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._panels: list[tuple[_WgpuCanvas, int, int, int, int]] = []
        self._row = 0
        self._colorbars: list[Any] = []

    def widget(self) -> QtWidgets.QWidget:
        """Return the Qt widget hosting the grid."""
        return self._widget

    def add_panel(self, *, row=None, col=None, rowspan=1, colspan=1,
                  title=None) -> base.Canvas:
        """Add a panel to the grid."""
        r = row if row is not None else self._row
        c = col if col is not None else 0
        canvas = _WgpuCanvas()
        if title:
            canvas.set_title(title)
        self._layout.addWidget(canvas.widget(), r, c, rowspan, colspan)
        self._panels.append((canvas, r, c, rowspan, colspan))
        return canvas

    def add_colorbar(self, image, *, colormap=None, row=None, col=None,
                     rowspan=1, colspan=1) -> H.ColorBar:
        """Add a colour bar bound to *image*."""
        cb = _handles._ColorBar(self, image, colormap=colormap)
        self._colorbars.append(cb)
        return cb

    def next_row(self) -> None:
        """Move the implicit insertion point to the next row."""
        self._row += 1

    def clear(self) -> None:
        """Remove every panel."""
        for canvas, *_ in self._panels:
            canvas.clear()
        self._panels.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._row = 0

    def set_column_stretch(self, column, factor) -> None:
        """Set a column's stretch factor."""
        self._layout.setColumnStretch(column, factor)

    def set_row_stretch(self, row, factor) -> None:
        """Set a row's stretch factor."""
        self._layout.setRowStretch(row, factor)

    @property
    def native(self):
        """The Qt widget hosting the grid."""
        return self._widget


# ---------------------------------------------------------------------------
# Image view canvas
# ---------------------------------------------------------------------------

class _WgpuImageView(base.ImageViewCanvas):
    """Image viewer: one image, optional overlays and ROIs."""

    def __init__(self, **opts):
        self._widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self._canvas = _WgpuCanvas()
        layout.addWidget(self._canvas.widget())
        self._image: _handles._Image | None = None
        self._overlays: list[_handles._Image] = []
        self._rois: list[_handles._Roi] = []
        self._histogram_width: int | None = None
        self._click_callbacks: list[Callable] = []

    def widget(self) -> QtWidgets.QWidget:
        """Return the Qt widget hosting the viewer."""
        return self._widget

    def set_image(self, data, *, auto_levels=True, axes=None) -> None:
        """Show *data*, auto-scaling the levels by default."""
        levels = None
        if auto_levels:
            arr = np.asarray(data)
            if arr.ndim == 2 and arr.size:
                finite = arr[np.isfinite(arr)]
                if finite.size:
                    levels = (float(finite.min()), float(finite.max()))
        if self._image is None:
            self._image = self._canvas.add_image(data, levels=levels)
        else:
            self._image.set_image(data, levels=levels)

    def set_colormap(self, name, source="matplotlib") -> None:
        """Set the image colour map."""
        if self._image:
            self._image.set_colormap(name)

    def clear(self) -> None:
        """Remove the image, overlays and ROIs."""
        self._canvas.clear()
        self._image = None
        self._overlays.clear()
        self._rois.clear()

    def set_histogram_width(self, width) -> None:
        """Set the level-histogram width (no histogram is drawn yet)."""
        self._histogram_width = width

    def set_interactive(self, *, mouse=True, menu=True) -> None:
        """Enable or disable interaction."""
        self._canvas.set_interactive(mouse=mouse, menu=menu)

    def add_overlay(self, data, *, colormap=None) -> H.Image:
        """Add an image drawn over the main one."""
        overlay = self._canvas.add_image(data, colormap=colormap)
        self._overlays.append(overlay)
        return overlay

    def add_roi(self, *, kind="rect", pos=(0.0, 0.0), size=(10.0, 10.0),
                pen: S.Pen, movable=True, rotatable=False,
                points=None) -> H.Roi:
        """Add a region of interest."""
        roi = self._canvas.add_roi(kind=kind, pos=pos, size=size, pen=pen,
                                   movable=movable, rotatable=rotatable,
                                   points=points)
        self._rois.append(roi)
        return roi

    def on_click(self, callback) -> None:
        """Register a click callback ``(x, y)``."""
        self._click_callbacks.append(callback)
        self._canvas.on_click(lambda x, y, btn: callback(x, y))

    @property
    def native(self):
        """The Qt widget of the underlying canvas."""
        return self._canvas._widget
