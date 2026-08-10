"""Handle implementations for the chiplot OpenGL backend.

Each handle conforms to the :mod:`chisurf.gui.chiplot.handles` protocols.
Data items (curves, scatters, bars, images) render themselves in
:meth:`paint` using Qt GL wrappers (QOpenGLShaderProgram.setAttributeArray)
matching chimol's proven pattern; text overlays are painted by the canvas's
QPainter pass.
"""

from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
from OpenGL import GL

from chisurf.gui.chiplot import handles as H
from chisurf.gui.chiplot import style as S


def _rgba(color: S.Color, alpha: float = 1.0) -> tuple[float, float, float, float]:
    r, g, b, a = color.as_tuple()
    return (r / 255.0, g / 255.0, b / 255.0, a / 255.0 * alpha)


def _to_ndc(canvas, xs, ys):
    """Transform data coordinates to NDC via the canvas view (handles log)."""
    return canvas._view.transform_array(
        np.asarray(xs, dtype=np.float64),
        np.asarray(ys, dtype=np.float64),
    )


class _HandleBase:
    """Shared behaviour: visibility, z-order, removal, native."""

    def __init__(self, canvas):
        self._canvas = canvas
        self._visible = True
        self._z = 0.0
        self._name: str | None = None

    @property
    def visible(self) -> bool:
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._visible = bool(value)
        self._canvas._request_update()

    @property
    def z(self) -> float:
        return self._z

    @z.setter
    def z(self, value: float) -> None:
        self._z = float(value)

    def hide(self) -> None:
        self.visible = False

    def show(self) -> None:
        self.visible = True

    def remove(self) -> None:
        self._canvas._remove_handle(self)

    @property
    def native(self):
        return self

    def __getattr__(self, name: str):
        raise AttributeError(name)


# ---------------------------------------------------------------------------
# Curve
# ---------------------------------------------------------------------------

class _Curve(_HandleBase):
    """A line / step curve optionally carrying per-point markers."""

    def __init__(self, canvas, x, y, *, pen, name=None, fill=None, step=False,
                 symbol=None, symbol_size=7.0, symbol_brush=None,
                 symbol_pen=None, skip_missing=True):
        super().__init__(canvas)
        self._name = name
        self._pen = pen
        self._fill = fill
        self._step = step
        self._symbol = symbol
        self._symbol_size = symbol_size
        self._symbol_brush = symbol_brush
        self._symbol_pen = symbol_pen
        self._skip_missing = skip_missing
        self._opacity = 1.0
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)

    @staticmethod
    def _make_step(x, y, mode):
        mode = mode if isinstance(mode, str) else "center"
        if len(x) == len(y) + 1:
            cx = x
        else:
            if mode == "left":
                cx = x
            elif mode == "right":
                cx = np.concatenate([x[1:], [x[-1] + (x[-1] - x[-2])]])
            else:
                cx = (x[:-1] + x[1:]) / 2.0
        sx = np.empty(2 * len(cx))
        sy = np.empty(2 * len(cx))
        sx[0::2] = cx
        sx[1::2] = np.roll(cx, -1)
        sy[0::2] = y
        sy[1::2] = y
        if mode == "right":
            sx = np.roll(sx, 1)
        return sx, sy

    @staticmethod
    def _insert_breaks(x, y):
        mask = np.isfinite(x) & np.isfinite(y)
        if mask.all():
            return x, y
        xs, ys = [], []
        for i in range(len(x)):
            if mask[i]:
                xs.append(x[i])
                ys.append(y[i])
            else:
                xs.extend([x[i], x[i], x[i]])
                ys.extend([y[i], np.nan, y[i]])
        return np.array(xs, dtype=np.float64), np.array(ys, dtype=np.float64)

    def _line_data(self):
        xs, ys = self._x, self._y
        if self._step:
            xs, ys = self._make_step(xs, ys, self._step)
        if self._skip_missing:
            xs, ys = self._insert_breaks(xs, ys)
        nx, ny = _to_ndc(self._canvas, xs, ys)
        return nx.astype(np.float32), ny.astype(np.float32)

    def paint(self, prog, mvp):
        if not self._visible:
            return
        nx, ny = self._line_data()
        if len(nx) == 0:
            return
        verts = np.column_stack([nx, ny])
        prog.use()
        prog.set_matrix4("u_mvp", mvp)
        prog.set_int("u_use_vertex_color", 0)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        if self._fill is not None:
            y0 = self._canvas._y_baseline()
            _, ny0 = self._canvas._view.transform_array(np.array([nx[0]]), np.array([y0]))
            fill_x = np.concatenate([[nx[0]], nx, [nx[-1]]])
            fill_y = np.concatenate([[ny0[0]], ny, [ny0[0]]])
            fill_verts = np.column_stack([fill_x, fill_y]).astype(np.float32)
            c = _rgba(self._fill.color, self._opacity)
            prog.set_vec4("u_color", c)
            prog.set_attribute("a_pos", fill_verts)
            GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, len(fill_verts))

        pen = self._pen
        if pen is not None and pen.style is not S.LineStyle.NONE:
            c = _rgba(pen.color, self._opacity)
            prog.set_vec4("u_color", c)
            GL.glLineWidth(max(pen.width, 1.0))
            prog.set_attribute("a_pos", verts)
            GL.glDrawArrays(GL.GL_LINE_STRIP, 0, len(verts))

        GL.glDisable(GL.GL_BLEND)
        prog.disable_attribute("a_pos")

    def set_data(self, x, y) -> None:
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)
        self._canvas._request_update()

    def get_data(self):
        return self._x, self._y

    def set_pen(self, pen) -> None:
        self._pen = S.to_pen(pen)
        self._canvas._request_update()

    def set_symbol(self, symbol) -> None:
        self._symbol = H.Symbol(symbol) if symbol else None

    def set_symbol_size(self, size: float) -> None:
        self._symbol_size = float(size)

    def set_symbol_brush(self, brush) -> None:
        self._symbol_brush = S.to_brush(brush)

    def set_opacity(self, alpha: float) -> None:
        self._opacity = float(alpha)
        self._canvas._request_update()

    def set_downsampling(self, *, auto: bool = True, mode: str = "peak") -> None:
        """Enable/disable automatic downsampling of dense curves.

        The OpenGL backend renders every point; downsampling is a no-op
        accepted for API compatibility.
        """

    def set_clip_to_view(self, clip: bool = True) -> None:
        """Hint the backend to skip drawing samples outside the visible range.

        The OpenGL backend clips via the scissor test; this is a no-op
        accepted for API compatibility.
        """


# ---------------------------------------------------------------------------
# Scatter
# ---------------------------------------------------------------------------

class _Scatter(_HandleBase):
    """A cloud of point markers rendered as GL points."""

    def __init__(self, canvas, x, y, *, size, pen, brush, symbol, name=None):
        super().__init__(canvas)
        self._name = name
        self._size = size
        self._pen = pen
        self._brush = brush or S.Brush(S.Color(200, 200, 200))
        self._symbol = symbol
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)

    def paint(self, point_prog, mvp):
        if not self._visible:
            return
        nx, ny = _to_ndc(self._canvas, self._x, self._y)
        verts = np.column_stack([nx.astype(np.float32), ny.astype(np.float32)])
        point_prog.use()
        point_prog.set_matrix4("u_mvp", mvp)
        point_prog.set_float("u_point_size", self._size)
        c = _rgba(self._brush.color)
        point_prog.set_vec4("u_color", c)
        point_prog.set_int("u_use_vertex_color", 0)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)
        point_prog.set_attribute("a_pos", verts)
        GL.glDrawArrays(GL.GL_POINTS, 0, len(verts))
        GL.glDisable(GL.GL_BLEND)
        point_prog.disable_attribute("a_pos")

    def set_data(self, x, y) -> None:
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)
        self._canvas._request_update()

    def get_data(self):
        return self._x, self._y


# ---------------------------------------------------------------------------
# Bars
# ---------------------------------------------------------------------------

class _Bars(_HandleBase):
    """A bar graph rendered as filled rectangles."""

    def __init__(self, canvas, x, height, *, width, pen, brush):
        super().__init__(canvas)
        self._width = width
        self._pen = pen
        self._brush = brush or S.Brush(S.Color(100, 150, 255))
        self._x = np.asarray(x, dtype=np.float64)
        self._height = np.asarray(height, dtype=np.float64)

    def paint(self, prog, mvp):
        if not self._visible:
            return
        w = self._width
        y0 = self._canvas._y_baseline()
        verts_data = []
        for cx, h in zip(self._x, self._height):
            xl, xr = cx - w / 2, cx + w / 2
            quad = [(xl, y0), (xr, y0), (xr, h), (xl, h)]
            tris = [quad[0], quad[1], quad[2], quad[0], quad[2], quad[3]]
            verts_data.extend(tris)
        if not verts_data:
            return
        vx = np.array([v[0] for v in verts_data])
        vy = np.array([v[1] for v in verts_data])
        nx, ny = _to_ndc(self._canvas, vx, vy)
        verts = np.column_stack([nx.astype(np.float32), ny.astype(np.float32)])
        prog.use()
        prog.set_matrix4("u_mvp", mvp)
        prog.set_int("u_use_vertex_color", 0)
        c = _rgba(self._brush.color)
        prog.set_vec4("u_color", c)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        prog.set_attribute("a_pos", verts)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(verts))
        GL.glDisable(GL.GL_BLEND)
        prog.disable_attribute("a_pos")

    def set_data(self, x, height) -> None:
        self._x = np.asarray(x, dtype=np.float64)
        self._height = np.asarray(height, dtype=np.float64)
        self._canvas._request_update()


# ---------------------------------------------------------------------------
# Error bars
# ---------------------------------------------------------------------------

class _ErrorBars(_HandleBase):
    """Vertical error bars rendered as line segments."""

    def __init__(self, canvas, x, y, *, height=None, top=None, bottom=None,
                 pen, beam=None):
        super().__init__(canvas)
        self._pen = pen
        self._beam = beam or 6.0
        if height is not None:
            self._top = np.asarray(y) + np.asarray(height) / 2
            self._bottom = np.asarray(y) - np.asarray(height) / 2
        else:
            self._top = np.asarray(y) + (np.asarray(top) if top is not None else 0)
            self._bottom = np.asarray(y) - (np.asarray(bottom) if bottom is not None else 0)
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)

    def paint(self, prog, mvp):
        if not self._visible:
            return
        verts_data = []
        for xi, lo, hi in zip(self._x, self._bottom, self._top):
            bw = self._beam / 2.0
            verts_data.extend([(xi, lo), (xi, hi),
                               (xi - bw, lo), (xi + bw, lo),
                               (xi - bw, hi), (xi + bw, hi)])
        if not verts_data:
            return
        vx = np.array([v[0] for v in verts_data])
        vy = np.array([v[1] for v in verts_data])
        nx, ny = _to_ndc(self._canvas, vx, vy)
        verts = np.column_stack([nx.astype(np.float32), ny.astype(np.float32)])
        prog.use()
        prog.set_matrix4("u_mvp", mvp)
        prog.set_int("u_use_vertex_color", 0)
        c = _rgba(self._pen.color)
        prog.set_vec4("u_color", c)
        GL.glLineWidth(max(self._pen.width, 1.0))
        prog.set_attribute("a_pos", verts)
        GL.glDrawArrays(GL.GL_LINES, 0, len(verts))
        prog.disable_attribute("a_pos")

    def set_data(self, x, y, *, height=None, top=None, bottom=None) -> None:
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)
        if height is not None:
            self._top = self._y + np.asarray(height) / 2
            self._bottom = self._y - np.asarray(height) / 2
        else:
            self._top = self._y + (np.asarray(top) if top is not None else 0)
            self._bottom = self._y - (np.asarray(bottom) if bottom is not None else 0)
        self._canvas._request_update()


# ---------------------------------------------------------------------------
# FillBetween
# ---------------------------------------------------------------------------

class _FillBetween(_HandleBase):
    """Filled area between two existing curves."""

    def __init__(self, canvas, lower, upper, *, brush):
        super().__init__(canvas)
        self._lower = lower
        self._upper = upper
        self._brush = brush

    def paint(self, prog, mvp):
        if not self._visible:
            return
        lx, ly = self._lower.get_data()
        ux, uy = self._upper.get_data()
        n = min(len(lx), len(ux))
        xs = np.concatenate([lx[:n], ux[:n][::-1]])
        ys = np.concatenate([ly[:n], uy[:n][::-1]])
        nx, ny = _to_ndc(self._canvas, xs, ys)
        verts = np.column_stack([nx.astype(np.float32), ny.astype(np.float32)])
        prog.use()
        prog.set_matrix4("u_mvp", mvp)
        prog.set_int("u_use_vertex_color", 0)
        c = _rgba(self._brush.color)
        prog.set_vec4("u_color", c)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        prog.set_attribute("a_pos", verts)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, len(verts))
        GL.glDisable(GL.GL_BLEND)
        prog.disable_attribute("a_pos")


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

class _Image(_HandleBase):
    """A 2-D image / heatmap rendered as a textured quad."""

    def __init__(self, canvas, data, *, colormap=None, levels=None, rect=None,
                 axis_order="row-major"):
        super().__init__(canvas)
        self._data = np.asarray(data, dtype=np.float32)
        if self._data.ndim == 3 and self._data.shape[-1] == 1:
            self._data = self._data[..., 0]
        self._colormap = colormap
        self._levels = levels
        self._rect = rect or (0, 0, self._data.shape[1], self._data.shape[0])
        self._axis_order = axis_order

    def paint(self, img_prog, mvp):
        if not self._visible:
            return
        from qtpy import QtGui
        x, y, w, h = self._rect
        corners = np.array([
            [x, y], [x + w, y], [x + w, y + h],
            [x, y], [x + w, y + h], [x, y + h],
        ], dtype=np.float64)
        uvs = np.array([
            [0.0, 0.0], [1.0, 0.0], [1.0, 1.0],
            [0.0, 0.0], [1.0, 1.0], [0.0, 1.0],
        ], dtype=np.float32)
        nx, ny = _to_ndc(self._canvas, corners[:, 0], corners[:, 1])
        verts = np.column_stack([nx.astype(np.float32), ny.astype(np.float32)])

        # Create texture from data
        d = self._data
        if self._levels is not None:
            lo, hi = self._levels
        else:
            lo, hi = float(np.nanmin(d)), float(np.nanmax(d))
        norm = np.clip((d - lo) / max(hi - lo, 1e-12), 0, 1)
        if self._colormap is not None:
            try:
                lut = S.to_colormap(self._colormap).lut(256)
                lut = np.asarray(lut, dtype=np.float32)
                if lut.ndim == 1:
                    rgba = np.column_stack([lut, lut, lut, np.ones_like(lut)])
                elif lut.shape[1] == 3:
                    rgba = np.column_stack([lut, np.ones(lut.shape[0])])
                else:
                    rgba = lut
                colors = rgba[(norm * 255).astype(int).clip(0, 255)]
            except Exception:
                colors = np.column_stack([norm, norm, norm, np.ones_like(norm)])
        else:
            colors = np.column_stack([norm, norm, norm, np.ones_like(norm)])
        colors = (colors * 255).clip(0, 255).astype(np.uint8)

        img_prog.use()
        img_prog.set_matrix4("u_mvp", mvp)
        img_prog.set_attribute("a_pos", verts)
        img_prog.set_attribute("a_uv", uvs)
        img_prog.set_vec2("u_levels", (0.0, 1.0))
        img_prog.set_int("u_use_lut", 0)

        # Upload texture
        tex = QtGui.QOpenGLTexture(QtGui.QImage(
            colors.tobytes(), colors.shape[1], colors.shape[0],
            3 * colors.shape[1], QtGui.QImage.Format_RGB888
        ))
        tex.setMinificationFilter(QtGui.QOpenGLTexture.Linear)
        tex.setMagnificationFilter(QtGui.QOpenGLTexture.Linear)
        tex.bind(0)
        img_prog._prog.setUniformValue(
            img_prog.uniform_loc("u_texture"), 0)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, len(verts))
        tex.release(0)
        tex.destroy()
        img_prog.disable_attribute("a_pos")
        img_prog.disable_attribute("a_uv")

    def set_image(self, data, *, levels=None) -> None:
        self._data = np.asarray(data, dtype=np.float32)
        if self._data.ndim == 3 and self._data.shape[-1] == 1:
            self._data = self._data[..., 0]
        if levels is not None:
            self._levels = levels
        self._canvas._request_update()

    def set_levels(self, low, high) -> None:
        self._levels = (low, high)
        self._canvas._request_update()

    def set_colormap(self, colormap) -> None:
        self._colormap = colormap
        self._canvas._request_update()

    def set_rect(self, x, y, w, h) -> None:
        self._rect = (x, y, w, h)
        self._canvas._request_update()

    def clear(self) -> None:
        self._data = np.zeros((1, 1), dtype=np.float32)
        self._canvas._request_update()


# ---------------------------------------------------------------------------
# Region (draggable interval)
# ---------------------------------------------------------------------------

class _Region(_HandleBase):
    """A draggable vertical or horizontal interval band."""

    def __init__(self, canvas, bounds, *, orientation, movable, brush, pen):
        super().__init__(canvas)
        self._bounds = list(bounds)
        self._orientation = orientation
        self._movable = movable
        self._brush = brush or S.Brush(S.Color(100, 200, 200, 50))
        self._pen = pen or S.Pen(S.Color(100, 200, 200))
        self._limits = None
        self._callbacks_final: list[Callable] = []
        self._callbacks_live: list[Callable] = []

    @property
    def bounds(self):
        return tuple(self._bounds)

    def set_bounds(self, low, high) -> None:
        self._bounds = [low, high]
        self._canvas._request_update()

    def set_limits(self, low, high) -> None:
        self._limits = (low, high)

    def on_change(self, callback, *, final=True) -> None:
        (self._callbacks_final if final else self._callbacks_live).append(callback)

    def _fire(self, final):
        for cb in (self._callbacks_final if final else self._callbacks_live):
            cb(*self._bounds)

    def paint(self, prog, mvp):
        if not self._visible:
            return
        vr = self._canvas._view
        lo, hi = self._bounds
        if self._orientation is H.Orientation.VERTICAL:
            y0, y1 = vr.y_range
            corners = [(lo, y0), (hi, y0), (hi, y1), (lo, y1)]
        else:
            x0, x1 = vr.x_range
            corners = [(x0, lo), (x1, lo), (x1, hi), (x0, hi)]
        cx = np.array([c[0] for c in corners])
        cy = np.array([c[1] for c in corners])
        nx, ny = _to_ndc(self._canvas, cx, cy)
        verts = np.column_stack([nx.astype(np.float32), ny.astype(np.float32)])

        prog.use()
        prog.set_matrix4("u_mvp", mvp)
        prog.set_int("u_use_vertex_color", 0)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

        c = _rgba(self._brush.color)
        prog.set_vec4("u_color", c)
        prog.set_attribute("a_pos", verts)
        GL.glDrawArrays(GL.GL_TRIANGLE_FAN, 0, 4)

        outline = np.empty((8, 2), dtype=np.float32)
        outline[0] = verts[0]; outline[1] = verts[1]
        outline[2] = verts[1]; outline[3] = verts[2]
        outline[4] = verts[2]; outline[5] = verts[3]
        outline[6] = verts[3]; outline[7] = verts[0]
        pc = _rgba(self._pen.color)
        prog.set_vec4("u_color", pc)
        GL.glLineWidth(max(self._pen.width, 1.0))
        prog.set_attribute("a_pos", outline)
        GL.glDrawArrays(GL.GL_LINES, 0, 8)
        GL.glDisable(GL.GL_BLEND)
        prog.disable_attribute("a_pos")


# ---------------------------------------------------------------------------
# Marker (movable infinite line)
# ---------------------------------------------------------------------------

class _Marker(_HandleBase):
    """A movable vertical or horizontal infinite line."""

    def __init__(self, canvas, pos, *, orientation, movable, pen, label=None):
        super().__init__(canvas)
        self._value = float(pos)
        self._orientation = orientation
        self._movable = movable
        self._pen = pen or S.Pen(S.Color(255, 255, 0))
        self._label = label
        self._callbacks_final: list[Callable] = []
        self._callbacks_live: list[Callable] = []

    @property
    def value(self):
        return self._value

    def set_value(self, value) -> None:
        self._value = float(value)
        self._canvas._request_update()

    def on_change(self, callback, *, final=True) -> None:
        (self._callbacks_final if final else self._callbacks_live).append(callback)

    def _fire(self, final):
        for cb in (self._callbacks_final if final else self._callbacks_live):
            cb(self._value)

    def paint(self, prog, mvp):
        if not self._visible:
            return
        vr = self._canvas._view
        if self._orientation is H.Orientation.VERTICAL:
            xs = np.array([self._value, self._value])
            ys = np.array(vr.y_range)
        else:
            xs = np.array(vr.x_range)
            ys = np.array([self._value, self._value])
        nx, ny = _to_ndc(self._canvas, xs, ys)
        verts = np.column_stack([nx.astype(np.float32), ny.astype(np.float32)])
        prog.use()
        prog.set_matrix4("u_mvp", mvp)
        prog.set_int("u_use_vertex_color", 0)
        c = _rgba(self._pen.color)
        prog.set_vec4("u_color", c)
        GL.glLineWidth(max(self._pen.width, 1.0))
        prog.set_attribute("a_pos", verts)
        GL.glDrawArrays(GL.GL_LINES, 0, 2)
        prog.disable_attribute("a_pos")


# ---------------------------------------------------------------------------
# Roi
# ---------------------------------------------------------------------------

class _Roi(_HandleBase):
    """A draggable/resizable region of interest."""

    def __init__(self, canvas, *, kind="rect", pos=(0, 0), size=(10, 10),
                 pen, movable=True, rotatable=False, points=None):
        super().__init__(canvas)
        self._kind = kind
        self._pos = list(pos)
        self._size = list(size)
        self._pen = pen
        self._movable = movable
        self._rotatable = rotatable
        self._points = points
        self._callbacks_final: list[Callable] = []
        self._callbacks_live: list[Callable] = []

    @property
    def pos(self):
        return tuple(self._pos)

    @property
    def size(self):
        return tuple(self._size)

    @property
    def points(self):
        x, y = self._pos
        w, h = self._size
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    def set_pos(self, x, y) -> None:
        self._pos = [x, y]
        self._canvas._request_update()

    def set_size(self, w, h) -> None:
        self._size = [w, h]
        self._canvas._request_update()

    def set_pen(self, pen, **overrides) -> None:
        self._pen = S.to_pen(pen, **overrides)
        self._canvas._request_update()

    def on_change(self, callback, *, final=True) -> None:
        (self._callbacks_final if final else self._callbacks_live).append(callback)

    def _fire(self, final):
        for cb in (self._callbacks_final if final else self._callbacks_live):
            cb()

    def paint(self, prog, mvp):
        if not self._visible:
            return
        pts = self.points
        n = len(pts)
        outline_data = []
        for i in range(n):
            outline_data.extend([pts[i], pts[(i + 1) % n]])
        vx = np.array([v[0] for v in outline_data])
        vy = np.array([v[1] for v in outline_data])
        nx, ny = _to_ndc(self._canvas, vx, vy)
        verts = np.column_stack([nx.astype(np.float32), ny.astype(np.float32)])
        prog.use()
        prog.set_matrix4("u_mvp", mvp)
        prog.set_int("u_use_vertex_color", 0)
        c = _rgba(self._pen.color)
        prog.set_vec4("u_color", c)
        GL.glLineWidth(max(self._pen.width, 1.0))
        prog.set_attribute("a_pos", verts)
        GL.glDrawArrays(GL.GL_LINES, 0, len(verts))
        prog.disable_attribute("a_pos")


# ---------------------------------------------------------------------------
# Arrow
# ---------------------------------------------------------------------------

class _Arrow(_HandleBase):
    """A scale-invariant arrow head at a data coordinate."""

    def __init__(self, canvas, pos, *, angle, size=20.0, tip_angle=25.0,
                 head_width=None, tail_length=None, tail_width=2.0,
                 pen=None, brush=None):
        super().__init__(canvas)
        self._pos = list(pos)
        self._angle = float(angle)
        self._size = float(size)
        self._tip_angle = float(tip_angle)
        self._pen = pen or S.Pen(S.Color(0, 0, 0))
        self._brush = brush or S.Brush(S.Color(0, 0, 0))

    @property
    def position(self):
        return tuple(self._pos)

    @property
    def angle(self):
        return self._angle

    def set_position(self, x, y) -> None:
        self._pos = [x, y]
        self._canvas._request_update()

    def set_angle(self, angle) -> None:
        self._angle = float(angle)
        self._canvas._request_update()

    def paint(self, prog, mvp):
        if not self._visible:
            return
        tip = self._pos
        rad = math.radians(self._angle)
        s = self._size
        half_tip = math.radians(self._tip_angle)
        bw = s * math.cos(half_tip)
        bh = s * math.sin(half_tip)
        w1 = (tip[0] - bw * math.cos(rad) - bh * math.sin(rad),
              tip[1] - bw * math.sin(rad) + bh * math.cos(rad))
        w2 = (tip[0] - bw * math.cos(rad) + bh * math.sin(rad),
              tip[1] - bw * math.sin(rad) - bh * math.cos(rad))
        tail = (tip[0] - s * math.cos(rad), tip[1] - s * math.sin(rad))
        pts = [(tip[0], tip[1]), w1, (tip[0], tip[1]), w2,
               (tip[0], tip[1]), tail]
        vx = np.array([p[0] for p in pts])
        vy = np.array([p[1] for p in pts])
        nx, ny = _to_ndc(self._canvas, vx, vy)
        verts = np.column_stack([nx.astype(np.float32), ny.astype(np.float32)])
        prog.use()
        prog.set_matrix4("u_mvp", mvp)
        prog.set_int("u_use_vertex_color", 0)
        c = _rgba(self._pen.color)
        prog.set_vec4("u_color", c)
        GL.glLineWidth(max(self._pen.width, 1.0))
        prog.set_attribute("a_pos", verts)
        GL.glDrawArrays(GL.GL_LINES, 0, len(verts))
        prog.disable_attribute("a_pos")


# ---------------------------------------------------------------------------
# Text (painted by canvas QPainter overlay)
# ---------------------------------------------------------------------------

class _Text(_HandleBase):
    """A text label rendered via the canvas QPainter overlay pass."""

    def __init__(self, canvas, text, pos, *, color, anchor=(0, 0),
                 draggable=False, fill=None, border=None, anchored=False):
        super().__init__(canvas)
        self._text = str(text)
        self._pos = list(pos)
        self._color = color
        self._anchor = anchor
        self._draggable = draggable
        self._fill = fill
        self._border = border
        self._anchored = anchored

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = str(value)
        self._canvas._request_update()

    def set_position(self, x, y) -> None:
        self._pos = [x, y]
        self._canvas._request_update()

    def paint_overlay(self, painter, view, w, h, margins):
        from qtpy import QtGui, QtCore
        if not self._visible:
            return
        if self._anchored:
            px, py = self._pos[0], self._pos[1]
        else:
            px, py = view.data_to_pixel(self._pos[0], self._pos[1], w, h, margins)
        c = self._color if isinstance(self._color, S.Color) else S.to_color(self._color)
        r, g, b, a = c.as_tuple()
        painter.setPen(QtGui.QColor(r, g, b, a))
        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(self._text)
        th = fm.height()
        ax, ay = self._anchor
        tx = px - ax * tw
        ty = py - (1 - ay) * th
        if self._fill is not None:
            fc = self._fill.color if isinstance(self._fill, S.Brush) else S.to_brush(self._fill).color
            fr, fg, fb, fa = fc.as_tuple()
            painter.fillRect(QtCore.QRectF(tx - 2, ty - 2, tw + 4, th + 4),
                             QtGui.QColor(fr, fg, fb, fa))
        if self._border is not None:
            bc = self._border.color if isinstance(self._border, S.Pen) else S.to_pen(self._border).color
            br, bg, bb, ba = bc.as_tuple()
            painter.setPen(QtGui.QColor(br, bg, bb, ba))
            painter.drawRect(QtCore.QRectF(tx - 2, ty - 2, tw + 4, th + 4))
            painter.setPen(QtGui.QColor(r, g, b, a))
        painter.drawText(QtCore.QPointF(tx, ty + fm.ascent()), self._text)


# ---------------------------------------------------------------------------
# ColorBar
# ---------------------------------------------------------------------------

class _ColorBar(_HandleBase):
    """A colour bar bound to an image handle."""

    def __init__(self, canvas, image, *, colormap=None):
        super().__init__(canvas)
        self._image = image
        self._colormap = colormap
        self._levels = (0.0, 1.0)
        self._hist_visible = True
        self._callbacks: list[Callable] = []

    def set_colormap(self, colormap) -> None:
        self._colormap = colormap
        self._image.set_colormap(colormap)

    def set_levels(self, low, high) -> None:
        self._levels = (low, high)
        self._image.set_levels(low, high)

    def get_levels(self):
        return self._levels

    def set_histogram_visible(self, visible) -> None:
        self._hist_visible = visible

    def on_levels_changed(self, callback) -> None:
        self._callbacks.append(callback)
