"""Handle implementations for the chiplot WebGPU backend.

Each handle conforms to the :mod:`chisurf.gui.chiplot.handles` protocols and
contributes **geometry**, not draw calls: :meth:`batches` returns clip-space
triangle lists, which the canvas hands to the renderer in one pass. Nothing
here touches the GPU, so a handle can be exercised — and its geometry asserted
on — with no device at all.

Text is the exception. It is painted in the canvas's ``QPainter`` overlay pass
(:meth:`paint_overlay`), because Qt already knows the application's fonts and a
glyph atlas would buy nothing at the scale a plot needs.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np

from chisurf.gui.chiplot import handles as H
from chisurf.gui.chiplot import style as S
from chisurf.gui.chiplot.backends.wgpu import _colormap, _gpu

#: Dash patterns in pixels, per :class:`~chisurf.gui.chiplot.style.LineStyle`.
_DASH_PATTERNS: dict[S.LineStyle, tuple[float, ...] | None] = {
    S.LineStyle.SOLID: None,
    S.LineStyle.DASH: (8.0, 5.0),
    S.LineStyle.DOT: (1.5, 3.5),
    S.LineStyle.DASH_DOT: (8.0, 4.0, 1.5, 4.0),
    S.LineStyle.NONE: None,
}


def _rgba(color: S.Color, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """Convert a chiplot colour to float RGBA in ``[0, 1]``."""
    r, g, b, a = color.as_tuple()
    return (r / 255.0, g / 255.0, b / 255.0, a / 255.0 * alpha)


def _dash_for(pen: S.Pen, scale: float) -> tuple[float, ...] | None:
    """Return the pixel dash pattern for *pen*, scaled to device pixels."""
    pattern = _DASH_PATTERNS.get(pen.style)
    if not pattern:
        return None
    unit = max(float(pen.width), 1.0) * scale
    return tuple(p * unit for p in pattern)


class _HandleBase:
    """Shared behaviour: visibility, z-order, removal, native."""

    def __init__(self, canvas):
        self._canvas = canvas
        self._visible = True
        self._z = 0.0
        self._name: str | None = None

    @property
    def visible(self) -> bool:
        """Whether the handle is drawn."""
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._visible = bool(value)
        self._canvas._request_update()

    @property
    def z(self) -> float:
        """Draw order; higher draws later (on top)."""
        return self._z

    @z.setter
    def z(self, value: float) -> None:
        self._z = float(value)
        self._canvas._request_update()

    def hide(self) -> None:
        """Stop drawing this handle."""
        self.visible = False

    def show(self) -> None:
        """Resume drawing this handle."""
        self.visible = True

    def remove(self) -> None:
        """Remove this handle from its canvas."""
        self._canvas._remove_handle(self)

    def is_alive(self) -> bool:
        """Whether this handle is still attached to a canvas that can draw it."""
        canvas = getattr(self, "_canvas", None)
        if canvas is None:
            return False
        try:
            return self in canvas._handles
        except Exception:
            return False

    @property
    def native(self):
        """The renderer-level object — this handle itself; there is no other."""
        return self

    def batches(self, ctx) -> list:
        """Return the draw batches for this handle (empty by default)."""
        return []

    # -- geometry helpers available to every handle ----------------------
    def _ndc(self, ctx, xs, ys) -> np.ndarray:
        """Map data arrays to an ``(N, 2)`` clip-space array."""
        nx, ny = ctx.to_ndc(np.asarray(xs, dtype=np.float64),
                            np.asarray(ys, dtype=np.float64))
        return np.column_stack([nx, ny])

    def _stroke(self, ctx, pts: np.ndarray, pen: S.Pen, *, alpha: float = 1.0,
                closed: bool = False) -> list:
        """Expand a clip-space polyline into one stroked batch."""
        if pen is None or pen.style is S.LineStyle.NONE or len(pts) < 2:
            return []
        if closed:
            pts = np.vstack([pts, pts[:1]])
        tris = _gpu.expand_polyline(
            pts, ctx.viewport, max(pen.width, 1.0) * ctx.scale,
            dash=_dash_for(pen, ctx.scale))
        if not len(tris):
            return []
        return [_gpu.solid(tris, _rgba(pen.color, alpha))]


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
        """Expand ``(x, y)`` into the corner points of a step curve."""
        mode = mode if isinstance(mode, str) else "center"
        if len(x) == len(y) + 1:
            cx = x
        else:
            if mode == "left":
                cx = x
            elif mode == "right":
                cx = np.concatenate([x[1:], [x[-1] + (x[-1] - x[-2])]])
            else:
                cx = (x[:-1] + x[1:]) / 2.0 if len(x) > 1 else x
        sx = np.empty(2 * len(cx))
        sy = np.empty(2 * len(cx))
        sx[0::2] = cx
        sx[1::2] = np.roll(cx, -1)
        sy[0::2] = y[:len(cx)]
        sy[1::2] = y[:len(cx)]
        if mode == "right":
            sx = np.roll(sx, 1)
        return sx, sy

    def _line_data(self):
        """Return the (possibly stepped) data arrays this curve draws."""
        xs, ys = self._x, self._y
        if self._step:
            xs, ys = self._make_step(xs, ys, self._step)
        n = min(len(xs), len(ys))
        return xs[:n], ys[:n]

    def batches(self, ctx) -> list:
        """Fill, stroke and markers for this curve."""
        if not self._visible:
            return []
        xs, ys = self._line_data()
        if len(xs) < 1:
            return []
        out: list = []

        if self._fill is not None:
            y0 = self._canvas._y_baseline()
            band = _gpu.fill_between_geometry(
                xs, np.full(len(xs), y0, dtype=np.float64), ys)
            if len(band):
                tris = self._ndc(ctx, band[:, 0], band[:, 1])
                brush = self._fill if isinstance(self._fill, S.Brush) else S.to_brush(self._fill)
                out.append(_gpu.solid(tris.astype(np.float32),
                                      _rgba(brush.color, self._opacity)))

        pts = self._ndc(ctx, xs, ys)
        if self._skip_missing:
            # A non-finite sample breaks the line rather than spanning the gap.
            bad = ~np.isfinite(pts).all(axis=1)
            if bad.any():
                pts = pts.copy()
                pts[bad] = np.nan
        out.extend(self._stroke(ctx, pts, self._pen, alpha=self._opacity))

        if self._symbol is not None:
            sym = self._symbol.value if isinstance(self._symbol, H.Symbol) else str(self._symbol)
            tris = _gpu.marker_geometry(
                pts, self._symbol_size * ctx.scale, sym, ctx.viewport)
            if len(tris):
                brush = self._symbol_brush or (
                    S.Brush(self._pen.color) if self._pen else S.Brush(S.Color(255, 255, 255)))
                out.append(_gpu.solid(tris, _rgba(brush.color, self._opacity)))
        return out

    def set_data(self, x, y) -> None:
        """Replace the curve's data."""
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)
        self._canvas._request_update()

    def get_data(self):
        """Return the ``(x, y)`` arrays this curve holds."""
        return self._x, self._y

    def set_pen(self, pen, **overrides) -> None:
        """Restyle the line."""
        self._pen = S.to_pen(pen, **overrides)
        self._canvas._request_update()

    def set_symbol(self, symbol) -> None:
        """Set the per-point marker symbol."""
        self._symbol = H.Symbol(symbol) if symbol else None
        self._canvas._request_update()

    def set_symbol_size(self, size: float) -> None:
        """Set the per-point marker size in pixels."""
        self._symbol_size = float(size)
        self._canvas._request_update()

    def set_symbol_brush(self, brush) -> None:
        """Set the per-point marker fill."""
        self._symbol_brush = S.to_brush(brush)
        self._canvas._request_update()

    def set_opacity(self, alpha: float) -> None:
        """Set the whole-curve opacity (0 transparent .. 1 opaque)."""
        self._opacity = float(alpha)
        self._canvas._request_update()

    def set_downsampling(self, *, auto: bool = True, mode: str = "peak") -> None:
        """Enable/disable automatic downsampling of dense curves.

        Accepted and ignored: this backend uploads the whole series once per
        change and lets the GPU rasterise it, which is cheaper than reducing it
        on the CPU every frame.
        """

    def set_clip_to_view(self, clip: bool = True) -> None:
        """Hint the backend to skip samples outside the visible range.

        Accepted and ignored: the render pass is scissored to the plot area, so
        off-view geometry costs no fill.
        """


# ---------------------------------------------------------------------------
# Scatter
# ---------------------------------------------------------------------------

class _Scatter(_HandleBase):
    """A cloud of point markers."""

    def __init__(self, canvas, x, y, *, size, pen, brush, symbol, name=None):
        super().__init__(canvas)
        self._name = name
        self._size = float(size)
        self._pen = pen
        self._brush = brush or S.Brush(S.Color(200, 200, 200))
        self._symbol = symbol
        self._opacity = 1.0
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)
        self._brushes = None

    def batches(self, ctx) -> list:
        """One batch of marker triangles, per-vertex coloured when needed."""
        if not self._visible or not len(self._x):
            return []
        pts = self._ndc(ctx, self._x, self._y)
        sym = self._symbol.value if isinstance(self._symbol, H.Symbol) else (self._symbol or "o")
        tris = _gpu.marker_geometry(pts, self._size * ctx.scale, str(sym), ctx.viewport)
        if not len(tris):
            return []
        if self._brushes is not None:
            # Per-point colours: every marker contributes the same number of
            # vertices, so the colour array tiles by that count.
            per = len(tris) // max(len(self._brushes), 1)
            cols = np.repeat(
                np.array([_rgba(b.color, self._opacity) for b in self._brushes],
                         dtype=np.float32), per, axis=0)
            if len(cols) == len(tris):
                return [_gpu.SolidBatch(tris, cols)]
        out = [_gpu.solid(tris, _rgba(self._brush.color, self._opacity))]
        if self._pen is not None and self._pen.style is not S.LineStyle.NONE:
            outline = _gpu.marker_geometry(
                pts, self._size * ctx.scale + max(self._pen.width, 1.0) * ctx.scale,
                str(sym), ctx.viewport)
            # Draw the outline underneath so the fill covers its interior.
            out.insert(0, _gpu.solid(outline, _rgba(self._pen.color, self._opacity)))
        return out

    def set_data(self, x, y) -> None:
        """Replace the point positions."""
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)
        self._canvas._request_update()

    def get_data(self):
        """Return the ``(x, y)`` arrays this scatter holds."""
        return self._x, self._y

    def set_brush(self, brush) -> None:
        """Set one fill colour for every point."""
        self._brush = S.to_brush(brush)
        self._brushes = None
        self._canvas._request_update()

    def set_brushes(self, brushes) -> None:
        """Set a per-point fill colour."""
        self._brushes = [S.to_brush(b) for b in brushes]
        self._canvas._request_update()

    def set_size(self, size) -> None:
        """Set the marker diameter in pixels."""
        self._size = float(size)
        self._canvas._request_update()

    def set_opacity(self, alpha: float) -> None:
        """Set the whole-scatter opacity."""
        self._opacity = float(alpha)
        self._canvas._request_update()


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

    def batches(self, ctx) -> list:
        """Return filled quads, plus one stroked outline batch per bar edge."""
        if not self._visible or not len(self._x):
            return []
        w = np.broadcast_to(np.asarray(self._width, dtype=np.float64),
                            self._x.shape)
        y0 = self._canvas._y_baseline()
        xl, xr = self._x - w / 2.0, self._x + w / 2.0
        h = self._height
        base = np.full_like(h, y0)
        quads = np.stack([
            np.column_stack([xl, base]), np.column_stack([xr, base]),
            np.column_stack([xr, h]),
            np.column_stack([xl, base]), np.column_stack([xr, h]),
            np.column_stack([xl, h]),
        ], axis=1).reshape(-1, 2)
        tris = self._ndc(ctx, quads[:, 0], quads[:, 1]).astype(np.float32)
        out = [_gpu.solid(tris, _rgba(self._brush.color))]

        if self._pen is not None and self._pen.style is not S.LineStyle.NONE:
            # One stroke per bar; break the polyline between bars with NaN so
            # the outlines do not join into a comb.
            n = len(self._x)
            ring = np.empty((n * 6, 2))
            ring[0::6] = np.column_stack([xl, base])
            ring[1::6] = np.column_stack([xl, h])
            ring[2::6] = np.column_stack([xr, h])
            ring[3::6] = np.column_stack([xr, base])
            ring[4::6] = np.column_stack([xl, base])
            ring[5::6] = np.nan
            pts = self._ndc(ctx, ring[:, 0], ring[:, 1])
            out.extend(self._stroke(ctx, pts, self._pen))
        return out

    def set_data(self, x, height) -> None:
        """Replace the bar positions and heights."""
        self._x = np.asarray(x, dtype=np.float64)
        self._height = np.asarray(height, dtype=np.float64)
        self._canvas._request_update()

    def get_data(self):
        """Return the ``(x, height)`` arrays this bar graph holds."""
        return self._x, self._height


# ---------------------------------------------------------------------------
# Error bars
# ---------------------------------------------------------------------------

class _ErrorBars(_HandleBase):
    """Vertical error bars with end beams."""

    def __init__(self, canvas, x, y, *, height=None, top=None, bottom=None,
                 pen, beam=None):
        super().__init__(canvas)
        self._pen = pen or S.Pen(S.Color(200, 200, 200))
        # No beam unless one was asked for. ``beam`` is a *data*-unit width, so
        # a non-zero default draws caps as wide as several channels — which is
        # what the other backend does not do, and looks like a rendering fault.
        self._beam = float(beam) if beam else None
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)
        self._set_extent(height, top, bottom)

    def _set_extent(self, height, top, bottom):
        """Resolve the top/bottom arrays from the three accepted spellings."""
        if height is not None:
            half = np.asarray(height, dtype=np.float64) / 2.0
            self._top, self._bottom = self._y + half, self._y - half
        else:
            self._top = self._y + (np.asarray(top, dtype=np.float64) if top is not None else 0.0)
            self._bottom = self._y - (
                np.asarray(bottom, dtype=np.float64) if bottom is not None else 0.0)

    def batches(self, ctx) -> list:
        """Stems and beams as one stroked, NaN-broken polyline."""
        if not self._visible or not len(self._x):
            return []
        n = len(self._x)
        if self._beam:
            bw = self._beam / 2.0
            # stem, beam-low, beam-high — 2-point runs separated by a break.
            seq = np.full((n * 9, 2), np.nan)
            seq[0::9] = np.column_stack([self._x, self._bottom])
            seq[1::9] = np.column_stack([self._x, self._top])
            seq[3::9] = np.column_stack([self._x - bw, self._bottom])
            seq[4::9] = np.column_stack([self._x + bw, self._bottom])
            seq[6::9] = np.column_stack([self._x - bw, self._top])
            seq[7::9] = np.column_stack([self._x + bw, self._top])
        else:
            seq = np.full((n * 3, 2), np.nan)
            seq[0::3] = np.column_stack([self._x, self._bottom])
            seq[1::3] = np.column_stack([self._x, self._top])
        pts = self._ndc(ctx, seq[:, 0], seq[:, 1])
        return self._stroke(ctx, pts, self._pen)

    def set_data(self, x, y, *, height=None, top=None, bottom=None) -> None:
        """Replace the error-bar positions and extents."""
        self._x = np.asarray(x, dtype=np.float64)
        self._y = np.asarray(y, dtype=np.float64)
        self._set_extent(height, top, bottom)
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
        self._brush = brush or S.Brush(S.Color(120, 120, 120, 100))

    def batches(self, ctx) -> list:
        """Return the band between the two curves, as paired quads."""
        if not self._visible:
            return []
        lx, ly = self._lower.get_data()
        ux, uy = self._upper.get_data()
        band = _gpu.fill_between_geometry(lx, ly, uy[:len(lx)] if len(uy) >= len(lx) else uy)
        if not len(band):
            return []
        tris = self._ndc(ctx, band[:, 0], band[:, 1]).astype(np.float32)
        return [_gpu.solid(tris, _rgba(self._brush.color))]


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------

class _Image(_HandleBase):
    """A 2-D image / heatmap drawn as a textured quad."""

    def __init__(self, canvas, data, *, colormap=None, levels=None, rect=None,
                 axis_order="row-major"):
        super().__init__(canvas)
        self._colormap = colormap
        self._levels = levels
        self._axis_order = axis_order
        self._version = 0
        self._rgba_cache: np.ndarray | None = None
        self._set_data(data)
        self._rect = rect or (0, 0, self._data.shape[1], self._data.shape[0])

    def _set_data(self, data):
        """Store *data* as a 2-D scalar field or an RGB(A) image."""
        arr = np.asarray(data)
        if arr.ndim == 3 and arr.shape[-1] == 1:
            arr = arr[..., 0]
        self._data = arr
        self._rgba_cache = None
        self._version += 1

    def _rgba(self) -> np.ndarray:
        """Return the ``(H, W, 4)`` uint8 texture for the current data.

        The colour map is applied here rather than in the shader: it keeps one
        code path for "scalar field plus a map" and "the caller handed us RGBA",
        and a 256-entry lookup on the CPU is not what makes a heatmap slow.
        """
        if self._rgba_cache is not None:
            return self._rgba_cache
        d = self._data
        if d.ndim == 3 and d.shape[-1] in (3, 4):
            rgba = np.zeros(d.shape[:2] + (4,), dtype=np.uint8)
            rgba[..., :d.shape[-1]] = np.clip(d, 0, 255).astype(np.uint8)
            if d.shape[-1] == 3:
                rgba[..., 3] = 255
            self._rgba_cache = rgba
            return rgba
        d = np.asarray(d, dtype=np.float64)
        if self._levels is not None:
            lo, hi = float(self._levels[0]), float(self._levels[1])
        else:
            finite = d[np.isfinite(d)]
            lo, hi = (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
        norm = np.clip((d - lo) / max(hi - lo, 1e-12), 0.0, 1.0)
        norm[~np.isfinite(norm)] = 0.0
        idx = (norm * 255).astype(np.uint8)
        lut = _colormap.lookup_table(self._colormap, 256)
        if lut is not None:
            rgba = lut[idx]
        else:
            g = idx
            rgba = np.dstack([g, g, g, np.full_like(g, 255)])
        self._rgba_cache = np.ascontiguousarray(rgba)
        return self._rgba_cache

    def batches(self, ctx) -> list:
        """One textured quad covering the image's data rectangle."""
        if not self._visible or self._data.size == 0:
            return []
        x, y, w, h = self._rect
        corners = _gpu.quad_geometry(x, y, x + w, y + h)
        tris = self._ndc(ctx, corners[:, 0], corners[:, 1]).astype(np.float32)
        # Row 0 of the array is the *lowest* y of the rect, matching how a
        # heatmap's data is indexed; the v coordinate therefore runs with y.
        uv = np.array([
            [0.0, 1.0], [1.0, 1.0], [1.0, 0.0],
            [0.0, 1.0], [1.0, 0.0], [0.0, 0.0],
        ], dtype=np.float32)
        return [_gpu.ImageBatch(tris, uv, self._rgba(), key=self,
                                version=self._version)]

    def set_image(self, data, *, levels=None) -> None:
        """Replace the image data."""
        self._set_data(data)
        if levels is not None:
            self._levels = levels
        self._canvas._request_update()

    def set_levels(self, low, high) -> None:
        """Set the value range mapped across the colour map."""
        self._levels = (low, high)
        self._rgba_cache = None
        self._version += 1
        self._canvas._request_update()

    def get_levels(self):
        """Return the current ``(low, high)`` levels."""
        return self._levels

    def set_colormap(self, colormap) -> None:
        """Set the colour map applied to a scalar field."""
        self._colormap = colormap
        self._rgba_cache = None
        self._version += 1
        self._canvas._request_update()

    def set_rect(self, x, y, w, h) -> None:
        """Place the image in data coordinates."""
        self._rect = (x, y, w, h)
        self._canvas._request_update()

    def clear(self) -> None:
        """Drop the image contents."""
        self._set_data(np.zeros((1, 1), dtype=np.float32))
        self._canvas._request_update()


# ---------------------------------------------------------------------------
# Region (draggable interval)
# ---------------------------------------------------------------------------

class _Region(_HandleBase):
    """A draggable vertical or horizontal interval band."""

    def __init__(self, canvas, bounds, *, orientation, movable, brush, pen):
        super().__init__(canvas)
        self._bounds = [float(bounds[0]), float(bounds[1])]
        self._orientation = orientation
        self._movable = movable
        self._brush = brush or S.Brush(S.Color(100, 200, 200, 50))
        self._pen = pen or S.Pen(S.Color(100, 200, 200))
        self._limits = None
        self._callbacks_final: list[Callable] = []
        self._callbacks_live: list[Callable] = []

    @property
    def bounds(self):
        """The ``(low, high)`` interval in data units."""
        return tuple(self._bounds)

    def set_bounds(self, low, high) -> None:
        """Move the interval."""
        self._bounds = [float(low), float(high)]
        self._canvas._request_update()

    def set_limits(self, low, high) -> None:
        """Constrain how far the interval may be dragged."""
        self._limits = (low, high)

    def on_change(self, callback, *, final=True) -> None:
        """Register a callback for interval changes."""
        (self._callbacks_final if final else self._callbacks_live).append(callback)

    def _fire(self, final):
        """Invoke the registered callbacks."""
        for cb in (self._callbacks_final if final else self._callbacks_live):
            cb(*self._bounds)

    def _corners(self):
        """Return the band's rectangle in data coordinates."""
        vr = self._canvas._view
        lo, hi = sorted(self._bounds)
        if self._orientation is H.Orientation.VERTICAL:
            y0, y1 = vr.y_range
            return lo, y0, hi, y1
        x0, x1 = vr.x_range
        return x0, lo, x1, hi

    def batches(self, ctx) -> list:
        """Return the filled band and its two edges."""
        if not self._visible:
            return []
        x0, y0, x1, y1 = self._corners()
        quad = _gpu.quad_geometry(x0, y0, x1, y1)
        tris = self._ndc(ctx, quad[:, 0], quad[:, 1]).astype(np.float32)
        out = [_gpu.solid(tris, _rgba(self._brush.color))]
        ring = np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        pts = self._ndc(ctx, ring[:, 0], ring[:, 1])
        out.extend(self._stroke(ctx, pts, self._pen, closed=True))
        return out


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
        """The line's position in data units."""
        return self._value

    def set_value(self, value) -> None:
        """Move the line."""
        self._value = float(value)
        self._canvas._request_update()

    def on_change(self, callback, *, final=True) -> None:
        """Register a callback for position changes."""
        (self._callbacks_final if final else self._callbacks_live).append(callback)

    def _fire(self, final):
        """Invoke the registered callbacks."""
        for cb in (self._callbacks_final if final else self._callbacks_live):
            cb(self._value)

    def batches(self, ctx) -> list:
        """Return the line, spanning the full visible range of the other axis."""
        if not self._visible:
            return []
        vr = self._canvas._view
        if self._orientation is H.Orientation.VERTICAL:
            xs = np.array([self._value, self._value])
            ys = np.array(vr.y_range, dtype=np.float64)
        else:
            xs = np.array(vr.x_range, dtype=np.float64)
            ys = np.array([self._value, self._value])
        return self._stroke(ctx, self._ndc(ctx, xs, ys), self._pen)


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
        self._pen = pen or S.Pen(S.Color(255, 255, 0))
        self._movable = movable
        self._rotatable = rotatable
        self._points = points
        self._callbacks_final: list[Callable] = []
        self._callbacks_live: list[Callable] = []

    @property
    def pos(self):
        """The ROI's origin in data units."""
        return tuple(self._pos)

    @property
    def size(self):
        """The ROI's ``(width, height)`` in data units."""
        return tuple(self._size)

    @property
    def points(self):
        """The ROI outline as a list of data-coordinate corners."""
        if self._points is not None:
            return list(self._points)
        x, y = self._pos
        w, h = self._size
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]

    def set_pos(self, x, y) -> None:
        """Move the ROI."""
        self._pos = [x, y]
        self._canvas._request_update()

    def set_size(self, w, h) -> None:
        """Resize the ROI."""
        self._size = [w, h]
        self._canvas._request_update()

    def set_pen(self, pen, **overrides) -> None:
        """Restyle the ROI outline."""
        self._pen = S.to_pen(pen, **overrides)
        self._canvas._request_update()

    def on_change(self, callback, *, final=True) -> None:
        """Register a callback for ROI changes."""
        (self._callbacks_final if final else self._callbacks_live).append(callback)

    def _fire(self, final):
        """Invoke the registered callbacks."""
        for cb in (self._callbacks_final if final else self._callbacks_live):
            cb()

    def batches(self, ctx) -> list:
        """Return the ROI outline as a closed stroke."""
        if not self._visible:
            return []
        pts = np.array(self.points, dtype=np.float64)
        return self._stroke(ctx, self._ndc(ctx, pts[:, 0], pts[:, 1]),
                            self._pen, closed=True)


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
        self._tail_length = tail_length
        self._tail_width = float(tail_width)
        self._pen = pen or S.Pen(S.Color(220, 220, 220))
        self._brush = brush or S.Brush(self._pen.color)

    @property
    def position(self):
        """The arrow tip in data units."""
        return tuple(self._pos)

    @property
    def angle(self):
        """Degrees counter-clockwise from ``+x``, measured at the tip."""
        return self._angle

    def set_position(self, x, y) -> None:
        """Move the arrow tip."""
        self._pos = [x, y]
        self._canvas._request_update()

    def set_angle(self, angle) -> None:
        """Rotate the arrow."""
        self._angle = float(angle)
        self._canvas._request_update()

    def batches(self, ctx) -> list:
        """Return a filled head, plus a tail when one was asked for.

        The arrow is sized in **pixels** and so is built in pixel space: an
        arrow whose head grew when the user zoomed would be a different symbol
        at every zoom level.
        """
        if not self._visible:
            return []
        tip_ndc = self._ndc(ctx, [self._pos[0]], [self._pos[1]])
        if not np.isfinite(tip_ndc).all():
            return []
        tip = _gpu.to_pixel(tip_ndc, ctx.viewport)[0]
        rad = math.radians(self._angle)
        s = self._size * ctx.scale
        half = math.radians(self._tip_angle)
        back = np.array([-math.cos(rad), -math.sin(rad)])
        side = np.array([-math.sin(rad), math.cos(rad)])
        base = tip + back * (s * math.cos(half))
        w1 = base + side * (s * math.sin(half))
        w2 = base - side * (s * math.sin(half))
        head = np.array([tip, w1, w2])
        out = [_gpu.solid(_gpu.to_clip(head, ctx.viewport), _rgba(self._brush.color))]
        if self._tail_length:
            tail_end = base + back * (float(self._tail_length) * ctx.scale)
            tail = _gpu.expand_polyline(
                _gpu.to_clip(np.array([base, tail_end]), ctx.viewport),
                ctx.viewport, self._tail_width * ctx.scale)
            if len(tail):
                out.append(_gpu.solid(tail, _rgba(self._pen.color)))
        return out


# ---------------------------------------------------------------------------
# Text (painted by the canvas QPainter overlay)
# ---------------------------------------------------------------------------

class _Text(_HandleBase):
    """A text label drawn in the canvas's QPainter overlay pass."""

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
        """The label's string."""
        return self._text

    @text.setter
    def text(self, value):
        self._text = str(value)
        self._canvas._request_update()

    def set_text(self, value) -> None:
        """Replace the label's string."""
        self.text = value

    def set_position(self, x, y) -> None:
        """Move the label."""
        self._pos = [x, y]
        self._canvas._request_update()

    def paint_overlay(self, painter, view, w, h, margins):
        """Draw the label with QPainter, in widget pixel coordinates."""
        from qtpy import QtCore, QtGui

        if not self._visible:
            return
        if self._anchored:
            # A screen-pinned label is offset from the **plot rectangle's**
            # top-left, not the widget's: the other backend parents it to the
            # plot item, and the fit-quality overlay's (100, 0) means "just
            # inside the top of the data area". Measured from the widget it
            # lands in the axis margin and is clipped away entirely.
            ix, iy, _, _ = margins.plot_rect(w, h)
            px, py = ix + self._pos[0], iy + self._pos[1]
        else:
            px, py = view.data_to_pixel(self._pos[0], self._pos[1], w, h, margins)
        if not (math.isfinite(px) and math.isfinite(py)):
            return
        c = self._color if isinstance(self._color, S.Color) else S.to_color(self._color)
        r, g, b, a = c.as_tuple()
        painter.setFont(S.chrome_font("label"))
        fm = painter.fontMetrics()
        # Multi-line, because the labels that matter are: the fit-quality
        # overlay is three lines of range / chi2r / Durbin-Watson, and
        # ``drawText(QPointF, ...)`` runs them together on one.
        lines = str(self._text).splitlines() or [""]
        tw = max((fm.horizontalAdvance(line) for line in lines), default=0)
        th = fm.height() * len(lines)
        # Anchor (0, 0) is the text's top-left at the position and (1, 1) its
        # bottom-right, matching the other backend. Subtracting ``1 - ay``
        # flipped the vertical sense, so every default-anchored label sat a
        # whole line above where it was asked for.
        ax, ay = self._anchor
        tx = px - ax * tw
        ty = py - ay * th
        box = QtCore.QRectF(tx - 3, ty - 2, tw + 6, th + 4)
        if self._fill is not None:
            brush = self._fill if isinstance(self._fill, S.Brush) else S.to_brush(self._fill)
            fr, fg, fb, fa = brush.color.as_tuple()
            painter.fillRect(box, QtGui.QColor(fr, fg, fb, fa))
        if self._border is not None:
            pen = self._border if isinstance(self._border, S.Pen) else S.to_pen(self._border)
            br, bg, bb, ba = pen.color.as_tuple()
            painter.setPen(QtGui.QColor(br, bg, bb, ba))
            painter.drawRect(box)
        painter.setPen(QtGui.QColor(r, g, b, a))
        for i, line in enumerate(lines):
            painter.drawText(
                QtCore.QPointF(tx, ty + i * fm.height() + fm.ascent()), line)


# ---------------------------------------------------------------------------
# ColorBar
# ---------------------------------------------------------------------------

class _ColorBar(_HandleBase):
    """A colour bar bound to an image handle."""

    def __init__(self, canvas, image, *, colormap=None):
        super().__init__(canvas)
        self._image = image
        self._colormap = colormap
        self._levels = image.get_levels() or (0.0, 1.0)
        self._hist_visible = True
        self._callbacks: list[Callable] = []

    def set_colormap(self, colormap) -> None:
        """Set the colour map on the bar and its image."""
        self._colormap = colormap
        self._image.set_colormap(colormap)

    def set_levels(self, low, high) -> None:
        """Set the levels on the bar and its image."""
        self._levels = (low, high)
        self._image.set_levels(low, high)
        for cb in self._callbacks:
            cb(low, high)

    def get_levels(self):
        """Return the current ``(low, high)`` levels."""
        return self._levels

    def set_histogram_visible(self, visible) -> None:
        """Show or hide the level histogram."""
        self._hist_visible = bool(visible)

    def on_levels_changed(self, callback) -> None:
        """Register a callback for level changes."""
        self._callbacks.append(callback)
