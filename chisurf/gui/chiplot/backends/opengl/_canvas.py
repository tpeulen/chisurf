"""QOpenGLWidget-based canvas for the chiplot OpenGL backend.

The GL widget (:class:`_PlotGLWidget`) is a thin Qt surface: it creates an
OpenGL context, compiles the shader programs once, and delegates all
drawing to the canvas and its handles.  The data-item rendering is pure
OpenGL (shaders + VBOs); axes, ticks, text labels, and the legend are
painted on top with ``QPainter`` — so the only Qt dependency beyond the
context provider is the text/chrome overlay, which is easy to retarget.

:class:`_GlCanvas` implements :class:`base.Canvas`, :class:`_GlGrid`
implements :class:`base.GridCanvas`, and :class:`_GlImageView` implements
:class:`base.ImageViewCanvas`.
"""

from __future__ import annotations

import ctypes
import math
import threading
from typing import Any, Callable

import numpy as np
from OpenGL import GL
from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtWidgets import QOpenGLWidget

from chisurf.gui.chiplot import handles as H
from chisurf.gui.chiplot import style as S
from chisurf.gui.chiplot.backends import base
from chisurf.gui.chiplot.backends.opengl import _glcore, _handles


# ---------------------------------------------------------------------------
# Layout margins (pixel space reserved for axes)
# ---------------------------------------------------------------------------

_LEFT_MARGIN = 55
_BOTTOM_MARGIN = 45
_TOP_MARGIN = 8
_RIGHT_MARGIN = 12


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


# ---------------------------------------------------------------------------
# Extended ViewTransform with pixel mapping
# ---------------------------------------------------------------------------

class _PixelView(_glcore.ViewTransform):
    """View transform that also maps data to/from pixel coordinates."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def data_to_pixel(
        self, x: float, y: float, w: int, h: int, margins: _Margins,
    ) -> tuple[float, float]:
        """Map data coordinates to pixel coordinates within the widget."""
        nx, ny = self.data_to_ndc(x, y)
        px, py, pw, ph = margins.plot_rect(w, h)
        return px + (nx + 1) * 0.5 * pw, py + (1 - (ny + 1) * 0.5) * ph

    def pixel_to_data(
        self, px: float, py: float, w: int, h: int, margins: _Margins,
    ) -> tuple[float, float]:
        """Map pixel coordinates to data coordinates."""
        ix, iy, pw, ph = margins.plot_rect(w, h)
        nx = 2.0 * (px - ix) / max(pw, 1) - 1.0
        ny = 1.0 - 2.0 * (py - iy) / max(ph, 1)
        return self._inv_normalize(nx, self.x_range, self.log_x), self._inv_normalize(
            ny, self.y_range, self.log_y)

    @staticmethod
    def _inv_normalize(ndc: float, rng: list[float], log: bool) -> float:
        t = (ndc + 1) * 0.5
        if log:
            llo = math.log10(max(rng[0], 1e-10))
            lhi = math.log10(max(rng[1], 1e-10))
            return 10.0 ** (llo + t * (lhi - llo))
        return rng[0] + t * (rng[1] - rng[0])


# ---------------------------------------------------------------------------
# QOpenGLWidget surface
# ---------------------------------------------------------------------------

class _PlotGLWidget(QOpenGLWidget):
    """The raw GL surface: manages context, shaders, and the paint loop.

    Parameters
    ----------
    canvas : _GlCanvas
        The owning canvas that holds handle state and view transform.
    """

    def __init__(self, canvas: _GlCanvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self.setMouseTracking(True)
        self.setMinimumSize(50, 50)

    def initializeGL(self) -> None:
        """Compile shader programs on first context creation."""
        self._canvas._init_gl()

    def resizeGL(self, w: int, h: int) -> None:
        """Set the viewport to cover the whole widget."""
        GL.glViewport(0, 0, w * self.devicePixelRatio(), h * self.devicePixelRatio())

    def paintGL(self) -> None:
        """Render data items with OpenGL, then chrome with QPainter."""
        self._canvas._paint_gl()

    def mousePressEvent(self, event):
        self._canvas._mouse_press(event)

    def mouseReleaseEvent(self, event):
        self._canvas._mouse_release(event)

    def mouseMoveEvent(self, event):
        self._canvas._mouse_move(event)

    def wheelEvent(self, event):
        self._canvas._wheel(event)

    def contextMenuEvent(self, event):
        """Forward to the parent Plot widget so chiplot's menu logic applies."""
        parent = self.parent()
        while parent is not None:
            if hasattr(parent, "contextMenuEvent") and hasattr(parent, "_series"):
                # This is a chiplot Plot wrapper — let it build the menu.
                parent.contextMenuEvent(event)
                return
            parent = parent.parent()
        # Fallback: the backend's own small menu.
        self._canvas._context_menu(event)


# ---------------------------------------------------------------------------
# Single-panel canvas
# ---------------------------------------------------------------------------

class _GlCanvas(base.Canvas):
    """OpenGL canvas implementing the chiplot :class:`base.Canvas` contract."""

    def __init__(self, **opts):
        self._widget = _PlotGLWidget(self)
        self._handles: list[Any] = []
        self._view = _PixelView()
        self._margins = _Margins()
        self._gl_ready = False
        self._prog_line = None
        self._prog_point = None
        self._prog_image = None
        self._auto_range_x = True
        self._auto_range_y = True
        self._log_x = False
        self._log_y = False
        self._title: str | None = None
        self._xlabel: str | None = None
        self._ylabel: str | None = None
        self._rlabel: str | None = None
        self._tlabel: str | None = None
        self._show_grid_x = False
        self._show_grid_y = False
        self._grid_alpha = 0.3
        self._bg = S.Color(0, 0, 0)
        self._aspect_locked = False
        self._aspect_ratio = 1.0
        self._si_x = True
        self._si_y = True
        self._invert_y = False
        self._axis_visible = {"left": True, "bottom": True, "right": True, "top": True}
        self._interactive_mouse = True
        self._menu_enabled = True
        self._click_callbacks: list[Callable] = []
        self._mouse_move_callbacks: list[Callable] = []
        self._range_callbacks: list[Callable] = []
        self._menu_actions: list[tuple[str, Callable]] = []
        self._tick_spacing: dict[str, tuple[float | None, float | None]] = {}
        self._panning = False
        self._pan_start: tuple[float, float] | None = None
        self._lock = threading.Lock()
        self._legend_offset = (5, 5)
        self._linked_x: _GlCanvas | None = None
        self._linked_y: _GlCanvas | None = None
        # Apply any backend opts
        if opts:
            pass

    # -- GL lifecycle ---------------------------------------------------
    def _init_gl(self):
        self._gl_ready = True
        self._prog_line = _glcore.ShaderProgram(
            _glcore._VERT_SRC, _glcore._FRAG_SRC)
        self._prog_point = _glcore.ShaderProgram(
            _glcore._POINT_VERT_SRC, _glcore._FRAG_SRC)
        self._prog_image = _glcore.ShaderProgram(
            _glcore._IMAGE_VERT_SRC, _glcore._IMAGE_FRAG_SRC)

    def _paint_gl(self):
        w = self._widget.width()
        h = self._widget.height()
        dpr = self._widget.devicePixelRatioF()

        painter = QtGui.QPainter(self._widget)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        painter.beginNativePainting()

        GL.glViewport(0, 0, max(int(w * dpr), 1), max(int(h * dpr), 1))
        bg = self._bg
        br, bg_, bb, ba = bg.as_tuple()
        GL.glClearColor(br / 255.0, bg_ / 255.0, bb / 255.0, ba / 255.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        ix, iy, pw, ph = self._margins.plot_rect(w, h)
        GL.glEnable(GL.GL_SCISSOR_TEST)
        GL.glScissor(
            max(int(ix * dpr), 0),
            max(int((h - iy - ph) * dpr), 0),
            max(int(pw * dpr), 1),
            max(int(ph * dpr), 1),
        )

        if self._auto_range_x or self._auto_range_y:
            self._recompute_auto_range()

        mvp = np.identity(4, dtype=np.float32)

        with self._lock:
            ordered = sorted(self._handles, key=lambda hd: hd._z)
        for hd in ordered:
            if hasattr(hd, "paint"):
                try:
                    hd.paint(self._prog_line, mvp)
                except Exception:
                    pass

        GL.glDisable(GL.GL_SCISSOR_TEST)
        GL.glFlush()

        painter.endNativePainting()

        self._paint_chrome(painter, w, h)
        for hd in ordered:
            if hasattr(hd, "paint_overlay"):
                try:
                    hd.paint_overlay(painter, self._view, w, h, self._margins)
                except Exception:
                    pass
        painter.end()

    def _paint_chrome(self, painter: QtGui.QPainter, w: int, h: int):
        fg = QtGui.QColor(200, 200, 200)
        painter.setPen(fg)
        ix, iy, pw, ph = self._margins.plot_rect(w, h)

        # Draw plot border
        painter.setPen(QtGui.QColor(120, 120, 120))
        painter.drawRect(QtCore.QRectF(ix, iy, pw, ph))

        # X axis ticks/labels
        if self._axis_visible.get("bottom", True):
            self._paint_axis(painter, "bottom", ix, iy, pw, ph)
        if self._axis_visible.get("left", True):
            self._paint_axis(painter, "left", ix, iy, pw, ph)

        # Labels
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        painter.setPen(fg)
        if self._xlabel:
            painter.drawText(
                QtCore.QRectF(ix, h - self._margins.bottom + 18, pw, 20),
                QtCore.Qt.AlignCenter, self._xlabel)
        if self._ylabel:
            painter.save()
            painter.translate(12, iy + ph / 2)
            painter.rotate(-90)
            painter.drawText(QtCore.QRectF(-50, -10, 100, 20),
                             QtCore.Qt.AlignCenter, self._ylabel)
            painter.restore()
        if self._title:
            font.setPointSize(11)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QtCore.QRectF(ix, 0, pw, self._margins.top + 5),
                             QtCore.Qt.AlignCenter, self._title)
            font.setBold(False)
            font.setPointSize(9)
            painter.setFont(font)

        # Grid lines
        if self._show_grid_x or self._show_grid_y:
            grid_color = QtGui.QColor(0, 0, 0, int(255 * self._grid_alpha))
            painter.setPen(grid_color)
            if self._show_grid_x:
                for tv in self._tick_values("bottom", ix, pw):
                    px = self._view.data_to_pixel(tv, 0, w, h, self._margins)[0]
                    painter.drawLine(QtCore.QPointF(px, iy), QtCore.QPointF(px, iy + ph))
            if self._show_grid_y:
                for tv in self._tick_values("left", iy, ph):
                    py = self._view.data_to_pixel(0, tv, w, h, self._margins)[1]
                    painter.drawLine(QtCore.QPointF(ix, py), QtCore.QPointF(ix + pw, py))

    def _tick_values(self, side: str, origin: float, extent: float) -> list[float]:
        if side in ("bottom", "top"):
            lo, hi = self._view.x_range
        else:
            lo, hi = self._view.y_range
        if self._view.log_x and side in ("bottom", "top"):
            lo = max(lo, 1e-10)
            hi = max(hi, lo * 10)
        if self._view.log_y and side in ("left", "right"):
            lo = max(lo, 1e-10)
            hi = max(hi, lo * 10)
        spacing = self._tick_spacing.get(side)
        if spacing and spacing[0] is not None:
            step = spacing[0]
            ticks = []
            v = math.ceil(lo / step) * step
            while v <= hi + step * 0.001:
                ticks.append(v)
                v += step
            return ticks
        target = max(int(extent / 60), 3)
        return _glcore.nice_ticks(lo, hi, target)

    def _paint_axis(self, painter: QtGui.QPainter, side: str,
                    ix: int, iy: int, pw: int, ph: int):
        fg = QtGui.QColor(200, 200, 200)
        w = self._widget.width()
        h = self._widget.height()
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)
        fm = painter.fontMetrics()
        if side == "bottom":
            ticks = self._tick_values("bottom", ix, pw)
            step = ticks[1] - ticks[0] if len(ticks) > 1 else 1.0
            painter.setPen(fg)
            for tv in ticks:
                px, _ = self._view.data_to_pixel(tv, self._view.y_range[0], w, h, self._margins)
                painter.drawLine(QtCore.QPointF(px, iy + ph), QtCore.QPointF(px, iy + ph + 4))
                label = _glcore.format_tick(tv, step)
                tw = fm.horizontalAdvance(label)
                painter.drawText(QtCore.QRectF(px - tw / 2, iy + ph + 6, max(tw, 1), 16),
                                 QtCore.Qt.AlignCenter, label)
        elif side == "left":
            ticks = self._tick_values("left", iy, ph)
            step = ticks[1] - ticks[0] if len(ticks) > 1 else 1.0
            painter.setPen(fg)
            for tv in ticks:
                _, py = self._view.data_to_pixel(self._view.x_range[0], tv, w, h, self._margins)
                painter.drawLine(QtCore.QPointF(ix - 4, py), QtCore.QPointF(ix, py))
                label = _glcore.format_tick(tv, step)
                tw = fm.horizontalAdvance(label)
                painter.drawText(QtCore.QRectF(ix - tw - 8, py - 8, tw + 6, 16),
                                 QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter, label)

    # -- auto range -----------------------------------------------------
    def _recompute_auto_range(self):
        all_x, all_y = [], []
        for hd in self._handles:
            if not getattr(hd, "_visible", True):
                continue
            xs, ys = self._handle_data_range(hd)
            if xs is not None:
                all_x.append(xs)
            if ys is not None:
                all_y.append(ys)
        if self._auto_range_x and all_x:
            xmin = min(r[0] for r in all_x)
            xmax = max(r[1] for r in all_x)
            if xmin < xmax:
                pad = (xmax - xmin) * 0.05
                self._view.x_range = [xmin - pad, xmax + pad]
        if self._auto_range_y and all_y:
            ymin = min(r[0] for r in all_y)
            ymax = max(r[1] for r in all_y)
            if ymin < ymax:
                pad = (ymax - ymin) * 0.05
                self._view.y_range = [ymin - pad, ymax + pad]

    def _handle_data_range(self, hd) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
        if isinstance(hd, (_handles._Curve, _handles._Scatter)):
            xs = hd._x
            ys = hd._y
            mask = np.isfinite(xs) & np.isfinite(ys)
            if mask.any():
                xm = (float(np.min(xs[mask])), float(np.max(xs[mask])))
                ym = (float(np.min(ys[mask])), float(np.max(ys[mask])))
                return xm, ym
        elif isinstance(hd, _handles._Bars):
            if len(hd._x):
                return ((float(np.min(hd._x - hd._width / 2)),
                         float(np.max(hd._x + hd._width / 2))),
                        (0.0, float(np.max(hd._height)) if len(hd._height) else 1.0))
        elif isinstance(hd, _handles._Image):
            x, y, w, h = hd._rect
            return (x, x + w), (y, y + h)
        return None, None

    def _y_baseline(self) -> float:
        return self._view.y_range[0]

    # -- interaction ----------------------------------------------------
    def _mouse_press(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._interactive_mouse:
            self._panning = True
            self._pan_start = (event.position().x(), event.position().y())
            self._pan_range_start = (list(self._view.x_range), list(self._view.y_range))
        elif event.button() == QtCore.Qt.LeftButton:
            w = self._widget.width()
            h = self._widget.height()
            dx, dy = self._view.pixel_to_data(
                event.position().x(), event.position().y(), w, h, self._margins)
            for cb in self._click_callbacks:
                cb(dx, dy, "left")

    def _mouse_release(self, event):
        if event.button() == QtCore.Qt.LeftButton and self._panning:
            self._panning = False
            # If minimal movement, treat as click
            if self._pan_start:
                dx = abs(event.position().x() - self._pan_start[0])
                dy = abs(event.position().y() - self._pan_start[1])
                if dx < 3 and dy < 3:
                    w = self._widget.width()
                    h = self._widget.height()
                    px, py = self._view.pixel_to_data(
                        event.position().x(), event.position().y(), w, h, self._margins)
                    for cb in self._click_callbacks:
                        cb(px, py, "left")

    def _mouse_move(self, event):
        w = self._widget.width()
        h = self._widget.height()
        px, py = self._view.pixel_to_data(
            event.position().x(), event.position().y(), w, h, self._margins)
        for cb in self._mouse_move_callbacks:
            cb(px, py)
        if self._panning and self._pan_start and self._interactive_mouse:
            sx, sy = self._pan_start
            dx_pix = event.position().x() - sx
            dy_pix = event.position().y() - sy
            _, _, pw, ph = self._margins.plot_rect(w, h)
            xr0, yr0 = self._pan_range_start
            xspan = xr0[1] - xr0[0]
            yspan = yr0[1] - yr0[0]
            self._view.x_range = [
                xr0[0] - dx_pix / max(pw, 1) * xspan,
                xr0[1] - dx_pix / max(pw, 1) * xspan]
            self._view.y_range = [
                yr0[0] + dy_pix / max(ph, 1) * yspan,
                yr0[1] + dy_pix / max(ph, 1) * yspan]
            self._auto_range_x = False
            self._auto_range_y = False
            self._fire_range_changed()
            self._widget.update()

    def _wheel(self, event):
        if not self._interactive_mouse:
            return
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 1 / 1.15
        w = self._widget.width()
        h = self._widget.height()
        mx, my = self._view.pixel_to_data(
            event.position().x(), event.position().y(), w, h, self._margins)
        xr = self._view.x_range
        yr = self._view.y_range
        self._view.x_range = [mx + (xr[0] - mx) * factor, mx + (xr[1] - mx) * factor]
        self._view.y_range = [my + (yr[0] - my) * factor, my + (yr[1] - my) * factor]
        self._auto_range_x = False
        self._auto_range_y = False
        self._fire_range_changed()
        self._widget.update()

    def _context_menu(self, event):
        if not self._menu_enabled:
            return
        menu = QtWidgets.QMenu(self._widget)
        for label, cb in self._menu_actions:
            act = menu.addAction(label)
            act.triggered.connect(cb)
        if self._menu_actions:
            menu.exec_(event.globalPos())

    def _fire_range_changed(self):
        for cb in self._range_callbacks:
            cb(tuple(self._view.x_range), tuple(self._view.y_range))
        if self._linked_x is not None:
            self._linked_x._view.x_range = list(self._view.x_range)
            self._linked_x._widget.update()
        if self._linked_y is not None:
            self._linked_y._view.y_range = list(self._view.y_range)
            self._linked_y._widget.update()

    # -- internal -------------------------------------------------------
    def _request_update(self):
        self._widget.update()

    def _remove_handle(self, handle):
        with self._lock:
            if handle in self._handles:
                self._handles.remove(handle)
        self._widget.update()

    # -- Canvas contract: widget ---------------------------------------
    def widget(self) -> QtWidgets.QWidget:
        return self._widget

    # -- Canvas contract: drawing --------------------------------------
    def add_curve(self, x, y, *, pen, name=None, fill=None, step=False,
                  symbol=None, symbol_size=7.0, symbol_brush=None,
                  symbol_pen=None, skip_missing=True) -> H.Curve:
        c = _handles._Curve(self, x, y, pen=pen, name=name, fill=fill, step=step,
                            symbol=symbol, symbol_size=symbol_size,
                            symbol_brush=symbol_brush, symbol_pen=symbol_pen,
                            skip_missing=skip_missing)
        with self._lock:
            self._handles.append(c)
        self._widget.update()
        return c

    def add_scatter(self, x, y, *, size, pen, brush, symbol, name=None) -> H.Scatter:
        s = _handles._Scatter(self, x, y, size=size, pen=pen, brush=brush,
                              symbol=symbol, name=name)
        with self._lock:
            self._handles.append(s)
        self._widget.update()
        return s

    def add_bars(self, x, height, *, width, pen, brush) -> H.Bars:
        b = _handles._Bars(self, x, height, width=width, pen=pen, brush=brush)
        with self._lock:
            self._handles.append(b)
        self._widget.update()
        return b

    def add_fill_between(self, lower, upper, *, brush) -> H.Handle:
        fb = _handles._FillBetween(self, lower, upper, brush=brush)
        with self._lock:
            self._handles.append(fb)
        self._widget.update()
        return fb

    def add_errorbars(self, x, y, *, height=None, top=None, bottom=None,
                      pen, beam=None) -> H.ErrorBars:
        eb = _handles._ErrorBars(self, x, y, height=height, top=top,
                                 bottom=bottom, pen=pen, beam=beam)
        with self._lock:
            self._handles.append(eb)
        self._widget.update()
        return eb

    def add_image(self, data, *, colormap=None, levels=None, rect=None,
                  axis_order="row-major") -> H.Image:
        img = _handles._Image(self, data, colormap=colormap, levels=levels,
                              rect=rect, axis_order=axis_order)
        with self._lock:
            self._handles.append(img)
        self._widget.update()
        return img

    def add_region(self, bounds, *, orientation, movable, brush, pen) -> H.Region:
        r = _handles._Region(self, bounds, orientation=orientation, movable=movable,
                             brush=brush, pen=pen)
        with self._lock:
            self._handles.append(r)
        self._widget.update()
        return r

    def add_roi(self, *, kind="rect", pos=(0.0, 0.0), size=(10.0, 10.0),
                pen: S.Pen, movable=True, rotatable=False,
                points=None) -> H.Roi:
        roi = _handles._Roi(self, kind=kind, pos=pos, size=size, pen=pen,
                            movable=movable, rotatable=rotatable, points=points)
        with self._lock:
            self._handles.append(roi)
        self._widget.update()
        return roi

    def add_marker(self, pos, *, orientation, movable, pen, label=None) -> H.Marker:
        m = _handles._Marker(self, pos, orientation=orientation, movable=movable,
                             pen=pen, label=label)
        with self._lock:
            self._handles.append(m)
        self._widget.update()
        return m

    def add_arrow(self, pos, *, angle, size=20.0, tip_angle=25.0,
                  head_width=None, tail_length=None, tail_width=2.0,
                  pen=None, brush=None) -> H.Arrow:
        a = _handles._Arrow(self, pos, angle=angle, size=size, tip_angle=tip_angle,
                            head_width=head_width, tail_length=tail_length,
                            tail_width=tail_width, pen=pen, brush=brush)
        with self._lock:
            self._handles.append(a)
        self._widget.update()
        return a

    def add_text(self, text, pos, *, color, anchor=(0.0, 0.0), draggable=False,
                 fill=None, border=None, anchored=False) -> H.Text:
        t = _handles._Text(self, text, pos, color=color, anchor=anchor,
                           draggable=draggable, fill=fill, border=border,
                           anchored=anchored)
        with self._lock:
            self._handles.append(t)
        self._widget.update()
        return t

    def add_legend(self, *, offset=(5, 5)) -> None:
        self._legend_offset = offset

    def readd(self, handle) -> None:
        with self._lock:
            if handle not in self._handles:
                self._handles.append(handle)
        self._widget.update()

    def remove(self, handle) -> None:
        self._remove_handle(handle)

    def clear(self) -> None:
        with self._lock:
            self._handles.clear()
        self._widget.update()

    # -- Canvas contract: axes / view ----------------------------------
    def set_labels(self, *, left=None, bottom=None, right=None, top=None) -> None:
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
        self._title = title
        self._widget.update()

    def set_log(self, *, x=None, y=None) -> None:
        if x is not None:
            self._log_x = x
            self._view.log_x = x
        if y is not None:
            self._log_y = y
            self._view.log_y = y
        self._widget.update()

    def set_tick_spacing(self, side, *, major=None, minor=None) -> None:
        self._tick_spacing[side] = (major, minor)
        self._widget.update()

    def on_range_changed(self, callback) -> None:
        self._range_callbacks.append(callback)

    def set_range(self, *, x=None, y=None, padding=None) -> None:
        if x is not None:
            self._view.x_range = list(x)
            self._auto_range_x = False
        if y is not None:
            self._view.y_range = list(y)
            self._auto_range_y = False
        self._fire_range_changed()
        self._widget.update()

    def get_range(self) -> tuple[tuple[float, float], tuple[float, float]]:
        return tuple(self._view.x_range), tuple(self._view.y_range)

    def auto_range(self) -> None:
        self._auto_range_x = True
        self._auto_range_y = True
        self._recompute_auto_range()
        self._widget.update()

    def enable_auto_range(self, *, x=True, y=True) -> None:
        self._auto_range_x = x
        self._auto_range_y = y

    def set_grid(self, *, x=False, y=False, alpha=0.3) -> None:
        self._show_grid_x = x
        self._show_grid_y = y
        self._grid_alpha = alpha
        self._widget.update()

    def set_background(self, color) -> None:
        self._bg = color if isinstance(color, S.Color) else S.to_color(color) if color is not None else S.Color(0, 0, 0, 0)
        self._widget.update()

    def set_aspect_locked(self, lock, ratio=1.0) -> None:
        self._aspect_locked = lock
        self._aspect_ratio = ratio

    def set_si_prefix(self, *, x=None, y=None) -> None:
        if x is not None:
            self._si_x = x
        if y is not None:
            self._si_y = y

    def invert_y(self, invert=True) -> None:
        self._invert_y = invert

    def set_axis_visible(self, side, visible) -> None:
        self._axis_visible[side] = visible
        self._widget.update()

    def link_x(self, other) -> None:
        if isinstance(other, _GlCanvas):
            self._linked_x = other
            other._linked_x = self

    def link_y(self, other) -> None:
        if isinstance(other, _GlCanvas):
            self._linked_y = other
            other._linked_y = self

    def set_downsampling(self, *, auto: bool = True, mode: str = "peak") -> None:
        """Enable/disable automatic downsampling of dense curves on this panel.

        The OpenGL backend renders every point; accepted for API compatibility.
        """

    def set_clip_to_view(self, clip: bool = True) -> None:
        """Hint the backend to skip drawing samples outside the visible range.

        The OpenGL backend clips via the scissor test; accepted for API
        compatibility.
        """

    def set_menu_enabled(self, enabled) -> None:
        self._menu_enabled = enabled

    def menu_enabled(self) -> bool:
        return self._menu_enabled

    def set_interactive(self, *, mouse=True, menu=True) -> None:
        self._interactive_mouse = mouse
        self._menu_enabled = menu

    def provides_native_menu(self) -> bool:
        return False

    def add_menu_action(self, label, callback) -> None:
        self._menu_actions.append((label, callback))

    def export_image(self, path, *, width=None) -> bool:
        try:
            self._widget.grabFramebuffer().save(path)
            return True
        except Exception:
            try:
                self._widget.grab().save(path)
                return True
            except Exception:
                return False

    # -- Canvas contract: events ---------------------------------------
    def on_click(self, callback) -> None:
        self._click_callbacks.append(callback)

    def on_mouse_move(self, callback) -> None:
        self._mouse_move_callbacks.append(callback)

    @property
    def native(self):
        return self._widget


# ---------------------------------------------------------------------------
# Grid canvas
# ---------------------------------------------------------------------------

class _GlGrid(base.GridCanvas):
    """OpenGL grid canvas: composes multiple :class:`_GlCanvas` panels."""

    def __init__(self, **opts):
        self._widget = QtWidgets.QWidget()
        self._layout = QtWidgets.QGridLayout(self._widget)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._panels: list[tuple[_GlCanvas, int, int, int, int]] = []
        self._row = 0
        self._colorbars: list[Any] = []

    def widget(self) -> QtWidgets.QWidget:
        return self._widget

    def add_panel(self, *, row=None, col=None, rowspan=1, colspan=1,
                  title=None) -> base.Canvas:
        r = row if row is not None else self._row
        c = col if col is not None else 0
        canvas = _GlCanvas()
        if title:
            canvas.set_title(title)
        self._layout.addWidget(canvas.widget(), r, c, rowspan, colspan)
        self._panels.append((canvas, r, c, rowspan, colspan))
        return canvas

    def add_colorbar(self, image, *, colormap=None, row=None, col=None,
                     rowspan=1, colspan=1) -> H.ColorBar:
        cb = _handles._ColorBar(self, image, colormap=colormap)
        self._colorbars.append(cb)
        return cb

    def next_row(self) -> None:
        self._row += 1

    def clear(self) -> None:
        for canvas, *_ in self._panels:
            canvas.clear()
        self._panels.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._row = 0

    def set_column_stretch(self, column, factor) -> None:
        self._layout.setColumnStretch(column, factor)

    def set_row_stretch(self, row, factor) -> None:
        self._layout.setRowStretch(row, factor)

    @property
    def native(self):
        return self._widget


# ---------------------------------------------------------------------------
# Image view canvas
# ---------------------------------------------------------------------------

class _GlImageView(base.ImageViewCanvas):
    """OpenGL image viewer: image + optional overlay + ROI."""

    def __init__(self, **opts):
        self._widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self._canvas = _GlCanvas()
        layout.addWidget(self._canvas.widget())
        self._image: _handles._Image | None = None
        self._overlays: list[_handles._Image] = []
        self._rois: list[_handles._Roi] = []
        self._histogram_width: int | None = None
        self._interactive = True
        self._menu_enabled = True
        self._click_callbacks: list[Callable] = []

    def widget(self) -> QtWidgets.QWidget:
        return self._widget

    def set_image(self, data, *, auto_levels=True, axes=None) -> None:
        levels = None
        if auto_levels:
            arr = np.asarray(data)
            if arr.ndim == 2:
                levels = (float(np.nanmin(arr)), float(np.nanmax(arr)))
        if self._image is None:
            self._image = self._canvas.add_image(data, levels=levels)
        else:
            self._image.set_image(data, levels=levels)

    def set_colormap(self, name, source="matplotlib") -> None:
        if self._image:
            self._image.set_colormap(name)

    def clear(self) -> None:
        self._canvas.clear()
        self._image = None
        self._overlays.clear()
        self._rois.clear()

    def set_histogram_width(self, width) -> None:
        self._histogram_width = width

    def set_interactive(self, *, mouse=True, menu=True) -> None:
        self._interactive = mouse
        self._menu_enabled = menu
        self._canvas.set_interactive(mouse=mouse, menu=menu)

    def add_overlay(self, data, *, colormap=None) -> H.Image:
        overlay = self._canvas.add_image(data, colormap=colormap)
        self._overlays.append(overlay)
        return overlay

    def add_roi(self, *, kind="rect", pos=(0.0, 0.0), size=(10.0, 10.0),
                pen: S.Pen, movable=True, rotatable=False) -> H.Roi:
        roi = self._canvas.add_roi(kind=kind, pos=pos, size=size, pen=pen,
                                   movable=movable, rotatable=rotatable)
        self._rois.append(roi)
        return roi

    def on_click(self, callback) -> None:
        self._click_callbacks.append(callback)
        self._canvas.on_click(lambda x, y, btn: callback(x, y))

    @property
    def native(self):
        return self._canvas._widget
