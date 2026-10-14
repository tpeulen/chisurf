"""chiplot over emtk, the toolkit chimol draws its own interface with.

emtk is an immediate-mode toolkit: a control is handed a painter and draws
itself, frame by frame, and nothing persists between frames. chiplot is the
opposite -- ``plot.line(...)`` hands back a handle the caller keeps and mutates
later. This module is the bridge: the canvas owns a **display list** of series,
the handles edit entries in that list, and the control redraws the whole list
whenever its host asks for a repaint.

The module imports no toolkit. Whatever shows a panel -- an emtk surface that
draws the canvas as a control, or a host widget built by
:mod:`chisurf.gui.chiplot` -- attaches itself with :meth:`EmtkCanvas.attach_host`;
a host is any object with ``update()`` (and optionally ``size()`` and
``set_background(rgb)``), so nothing here knows which toolkit made it.

That shape is also why this backend cannot crash the way the pyqtgraph one
does. There are no per-item scene items to outlive their scene and no
Python slots connected to C++ destructors: a discarded plot is a Python list
that the garbage collector frees like any other.

What is drawn here today: curves (with symbols), scatter clouds, images and
heatmaps, draggable regions in both orientations (the fit range is one), markers in both
orientations, the legend, axis labels and title, ranges (explicit, queried and
auto), log scaling, grid and background, bar graphs, filled bands, error bars
and text labels, rectangle/ellipse/polygon ROIs, an inverted y-axis, the colour
bar, arrows, the multi-panel grid and the image view. What is left -- filled
curves -- raises :class:`NotImplementedError` naming what is
missing, because a plot that silently omits half of what it was asked to draw
is worse than one that says so. Those are the open front recorded in okf/subsystems/chiplot.md.

It is the only backend (the pyqtgraph one was removed); ``CHISURF_PLOT_BACKEND=pyqtgraph``
fails with a message saying so.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from chisurf.chiplot import handles as H
from chisurf.chiplot import style as S
from chisurf.chiplot.backends import base


def _rgb(color: Any, default: tuple[int, int, int] = (200, 200, 200)) -> tuple[int, int, int]:
    """Return ``color`` as an ``(r, g, b)`` triple emtk understands."""
    if color is None:
        return default
    for attribute in ("color", "colour"):
        inner = getattr(color, attribute, None)
        if inner is not None and inner is not color:
            return _rgb(inner, default)
    if all(hasattr(color, channel) for channel in ("r", "g", "b")):
        return (int(color.r), int(color.g), int(color.b))
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        r, g, b = (int(component) for component in color[:3])
        return (r, g, b)
    try:
        parsed = S.to_color(color)
    except Exception:
        return default
    return default if parsed is None else (int(parsed.r), int(parsed.g), int(parsed.b))


def _rgba(color: Any, default: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Return ``color`` as ``(r, g, b, a)``, keeping the alpha it was given."""
    if color is None:
        return default
    inner = getattr(color, "color", None)
    if inner is not None and inner is not color:
        return _rgba(inner, default)
    if all(hasattr(color, channel) for channel in ("r", "g", "b")):
        return (int(color.r), int(color.g), int(color.b), int(getattr(color, "a", 255)))
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        alpha = int(color[3]) if len(color) > 3 else 255
        r, g, b = (int(component) for component in color[:3])
        return (r, g, b, alpha)
    try:
        parsed = S.to_color(color)
    except Exception:
        return default
    return default if parsed is None else (parsed.r, parsed.g, parsed.b, parsed.a)


def _faded(colour, opacity: float) -> tuple[int, ...]:
    """``colour`` with its alpha scaled by ``opacity``; unchanged when opaque."""
    if colour is None or opacity >= 1.0:
        return colour
    r, g, b, *alpha = colour
    return (r, g, b, int(round((alpha[0] if alpha else 255) * max(opacity, 0.0))))


_SUPERSCRIPT = str.maketrans(
    "-0123456789", "\u207b\u2070\u00b9\u00b2\u00b3\u2074\u2075\u2076\u2077\u2078\u2079"
)


def _tick_labels(ticks: list[float], log: bool) -> list[str]:
    """Spell the tick values of one axis.

    A log axis holds exponents: whole decades read as the number while it is
    short (``1``, ``10``, ``1000``) and as a power of ten beyond that, and a
    tick between decades as its value. A linear axis gets as many decimals as
    its step needs, so ``0.30000000000000004`` is never printed and a column of
    ticks shares one precision.
    """
    if log:
        out = []
        for v in ticks:
            if abs(v - round(v)) < 1e-9:
                n = int(round(v))
                out.append(
                    f"{10.0**n:g}" if -2 <= n <= 4 else "10" + str(n).translate(_SUPERSCRIPT)
                )
            else:
                out.append(f"{10.0**v:.3g}")
        return out
    step = min((abs(b - a) for a, b in zip(ticks, ticks[1:]) if b != a), default=0.0)
    decimals = max(0, -math.floor(math.log10(step))) if 0.0 < step < 1.0 else 0
    labels = []
    for v in ticks:
        text = f"{v:.{decimals}f}"
        labels.append("0" if text.strip("-0.") == "" else text)
    return labels


#: Chrome colours for the axes, matched to emtk's plot frame.
_TICK_TEXT = (170, 175, 186)
_LABEL_TEXT = (196, 201, 212)
#: The width reserved for y tick numbers. Fixed rather than measured, so panels
#: stacked in one column put their left axes on one line whatever their values.
_Y_TICK_WIDTH = 44.0


def _chrome_scale() -> float:
    """Factor on the axis text: the plot font size (``gui.plot.font_size``) over the interface's.

    ``1.0`` while the setting is ``0`` (follow the interface font) or the sizes
    cannot be read. Read per frame, so *Settings ▸ Plots* reaches open plots.
    """
    try:
        from emtk import fonts

        from chisurf.core.plotting.appearance import font_size

        size = font_size()
        if size <= 0:
            return 1.0
        base = float(fonts.role_size_pt("ui"))
        return size / base if base > 0.0 else 1.0
    except Exception:  # noqa: BLE001 - an unreadable setting draws at the interface size
        return 1.0


def _orientation(value) -> str:
    """Return ``"vertical"`` or ``"horizontal"`` from a string or the enum.

    The facade hands down ``handles.Orientation``; ``str()`` on an enum is
    ``"Orientation.VERTICAL"``, which matches neither.
    """
    return str(getattr(value, "value", value)).lower()


def _finite_pairs(x, y, gaps: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(x, y)`` as float arrays without their non-finite samples.

    Dropped, or with ``gaps`` kept as NaN in both arrays: a curve that skips
    missing samples breaks there, and dropping them would join the neighbours
    across data that is not there.
    """
    xs = np.asarray(x, dtype=float).ravel()
    ys = np.asarray(y, dtype=float).ravel()
    if xs.size and ys.size and xs.size != ys.size:
        size = min(xs.size, ys.size)
        xs, ys = xs[:size], ys[:size]
    if xs.size == 0:
        return xs, ys
    keep = np.isfinite(xs) & np.isfinite(ys)
    if gaps:
        return np.where(keep, xs, np.nan), np.where(keep, ys, np.nan)
    return xs[keep], ys[keep]


def _whiskers(xs, height=None, top=None, bottom=None) -> tuple[np.ndarray, np.ndarray]:
    """Return per-sample ``(top, bottom)`` extents sized like ``xs``."""
    if height is not None and top is None and bottom is None:
        tops = bottoms = np.asarray(height, dtype=float).ravel() / 2.0
    else:
        tops = np.asarray(top if top is not None else 0.0, dtype=float).ravel()
        bottoms = np.asarray(bottom if bottom is not None else 0.0, dtype=float).ravel()
    tops = np.resize(tops, xs.shape) if tops.size else np.zeros_like(xs)
    bottoms = np.resize(bottoms, xs.shape) if bottoms.size else np.zeros_like(xs)
    return tops, bottoms


def _stroke_segment(painter, a, b, width: float, colour) -> None:
    """A straight line of *width* pixels between *a* and *b*, as two triangles."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return
    nx, ny = -dy / length * width / 2.0, dx / length * width / 2.0
    p0, p1 = (a[0] + nx, a[1] + ny), (a[0] - nx, a[1] - ny)
    p2, p3 = (b[0] - nx, b[1] - ny), (b[0] + nx, b[1] + ny)
    painter.fill_triangle(p0, p1, p2, colour)
    painter.fill_triangle(p0, p2, p3, colour)


def _draw_symbol(painter, x, y, symbol, size, brush, pen, width) -> None:
    """One marker centred on ``(x, y)``: filled with *brush*, outlined with *pen*.

    The painter draws rectangles and triangles, so a circle is a fan and an
    outline is a ring of thin quads. Either colour may be ``None`` (a hollow
    marker has no brush, a flat one no pen).
    """
    half = size / 2.0
    if symbol in ("+", "x"):
        colour = pen or brush
        if colour is None:
            return
        if symbol == "+":
            spans = [((x - half, y), (x + half, y)), ((x, y - half), (x, y + half))]
        else:
            spans = [
                ((x - half, y - half), (x + half, y + half)),
                ((x - half, y + half), (x + half, y - half)),
            ]
        for a, b in spans:
            _stroke_segment(painter, a, b, max(width, 1.0), colour)
        return
    if symbol == "s":
        outline = [
            (x - half, y - half),
            (x + half, y - half),
            (x + half, y + half),
            (x - half, y + half),
        ]
    elif symbol == "t":
        outline = [(x, y - half), (x + half, y + half), (x - half, y + half)]
    elif symbol == "d":
        outline = [(x, y - half), (x + half, y), (x, y + half), (x - half, y)]
    else:  # "o" and anything unknown: a circle
        steps = 20
        outline = [
            (
                x + half * math.cos(2.0 * math.pi * k / steps),
                y + half * math.sin(2.0 * math.pi * k / steps),
            )
            for k in range(steps)
        ]
    if brush is not None:
        for index in range(1, len(outline) - 1):
            painter.fill_triangle(outline[0], outline[index], outline[index + 1], brush)
    if pen is not None:
        for index, point in enumerate(outline):
            _stroke_segment(
                painter, point, outline[(index + 1) % len(outline)], max(width, 1.0), pen
            )


def _lut(colormap, size: int = 256) -> np.ndarray:
    """Return ``colormap`` as an ``(size, 4)`` uint8 RGBA lookup table.

    The tables are emtk's (:mod:`emtk.colormaps`); an unknown name draws a
    grey ramp: a heatmap in the wrong colours still shows the data, and
    refusing to draw one over a colormap name would not.
    """
    from emtk import colormaps

    if isinstance(colormap, np.ndarray) and colormap.ndim == 2 and colormap.shape[1] == 4:
        # A table handed over as-is: how an overlay gets a transparent low end.
        return np.asarray(colormap, dtype=np.uint8)
    name = getattr(colormap, "name", colormap)
    try:
        return np.asarray(colormaps.lookup_table(str(name), size), dtype=np.uint8)
    except KeyError:
        table = np.linspace(0.0, 1.0, size)
        grey = (table * 255.0).astype(np.uint8)
        return np.stack([grey, grey, grey, np.full(size, 255, np.uint8)], axis=1)


def _texture(data: np.ndarray, colormap, levels) -> tuple[Any, int, int]:
    """Map *data* through *colormap* into an emtk texture.

    Returns ``(texture, rows, columns)``. ``levels`` is the ``(low, high)``
    the colours span; without one the data's own finite extent is used, which
    is what makes a heatmap of an unfamiliar array show something rather than
    one flat colour.
    """
    from emtk.texture import Texture

    if np.ndim(data) == 3 and np.shape(data)[-1] in (3, 4):
        # Colours already: RGB(A) as bytes, or as floats in 0..1 (or 0..255).
        colours = np.asarray(data)
        if colours.dtype != np.uint8:
            colours = np.asarray(colours, dtype=float)
            scale = 255.0 if np.nanmax(colours, initial=0.0) <= 1.0 else 1.0
            colours = np.clip(colours * scale, 0.0, 255.0).astype(np.uint8)
        if colours.shape[-1] == 3:
            alpha = np.full(colours.shape[:2] + (1,), 255, np.uint8)
            colours = np.concatenate([colours, alpha], axis=2)
        rows, columns = colours.shape[:2]
        return Texture(columns, rows, np.ascontiguousarray(colours).tobytes()), rows, columns
    values = np.asarray(data, dtype=float)
    if values.ndim != 2:
        raise ValueError(f"an image is 2-D (or RGB/RGBA); got shape {values.shape}")
    finite = values[np.isfinite(values)]
    if levels is not None:
        low, high = float(levels[0]), float(levels[1])
    elif finite.size:
        low, high = float(finite.min()), float(finite.max())
    else:
        low, high = 0.0, 1.0
    span = (high - low) or 1.0

    table = _lut(colormap)
    scaled = np.clip((values - low) / span, 0.0, 1.0)
    scaled[~np.isfinite(values)] = 0.0
    indices = (scaled * (table.shape[0] - 1)).astype(np.intp)
    rgba = table[indices]  # (rows, columns, 4)
    rows, columns = rgba.shape[0], rgba.shape[1]
    return Texture(columns, rows, rgba.tobytes()), rows, columns


#: How far below the largest drawn value a log axis autoscales, in decades.
#: Wider than any counting experiment (a TCSPC decay spans ~5); narrower than the
#: denormal tails numerical curves underflow to.
LOG_AUTOSCALE_DECADES = 12.0


def _on_screen(pixel: float, start: float, size: float) -> float:
    """A pixel coordinate kept on the plot area's edge when the axis sends it off to infinity.

    A region bound of 0 on a log axis (a fit range starting at the first lag of
    a correlation curve) maps to −∞; the region then reaches the left edge, it
    does not stop being drawn -- and an infinite rectangle is not something a
    painter can fill.
    """
    pixel = float(pixel)
    if pixel != pixel:  # NaN: the bound is meaningless here; sit on the near edge
        return float(start)
    return min(max(pixel, float(start) - 1.0), float(start) + float(size) + 1.0)


class _Entry:
    """One item in a canvas's display list, and the handle the caller holds."""

    def __init__(self, canvas: EmtkCanvas, kind: str, **state: Any) -> None:
        self._canvas = canvas
        self.kind = kind
        self.state = state
        self.state.setdefault("visible", True)
        self.state.setdefault("z", 0.0)
        self._alive = True

    # -- Handle -------------------------------------------------------
    @property
    def visible(self) -> bool:
        """Whether the element is currently drawn."""
        return bool(self.state["visible"])

    @visible.setter
    def visible(self, value: bool) -> None:
        self.state["visible"] = bool(value)
        self._canvas.refresh()

    @property
    def z(self) -> float:
        """Stacking order; higher draws on top."""
        return float(self.state["z"])

    @z.setter
    def z(self, value: float) -> None:
        self.state["z"] = float(value)
        self._canvas.refresh()

    def hide(self) -> None:
        """Stop drawing this element."""
        self.visible = False

    def show(self) -> None:
        """Draw this element again."""
        self.visible = True

    def remove(self) -> None:
        """Take this element out of its panel."""
        self._canvas.remove(self)

    def is_alive(self) -> bool:
        """Whether the element still belongs to a panel.

        Always answerable here: an entry is a Python object, so unlike a
        wrapped graphics item it cannot be half-destroyed.
        """
        return self._alive

    @property
    def native(self) -> Any:
        """The display-list entry itself; emtk has no per-series object.

        A property, as in every other backend: a handle's ``native`` is read,
        not called.
        """
        return self.state

    # -- Curve / Scatter ----------------------------------------------
    def set_data(self, x, y=None, **kwargs: Any) -> None:
        """Replace the series' samples (and an error bar's extents)."""
        if y is None and x is not None and len(np.shape(x)) == 2:
            data = np.asarray(x, dtype=float)
            x, y = data[:, 0], data[:, 1]
        self.state["x"], self.state["y"] = _finite_pairs(x, y, gaps=self.state.get("gaps", False))
        if self.kind == "errorbars":
            # Error bars carry per-sample extents; replacing x/y alone left
            # them the old length and the painter indexed past their end.
            self.state["top"], self.state["bottom"] = _whiskers(
                self.state["x"],
                kwargs.get("height"),
                kwargs.get("top"),
                kwargs.get("bottom"),
            )
        self._canvas.refresh()

    def get_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the samples as ``(x, y)``."""
        return self.state["x"], self.state["y"]

    def set_pen(self, pen, **overrides: Any) -> None:
        """Set the line or outline colour and width."""
        pen = S.to_pen(pen, **overrides) if overrides or not isinstance(pen, S.Pen) else pen
        self.state["color"] = _rgb(pen)
        self.state["width"] = float(getattr(pen, "width", 1.0) or 1.0)
        self._canvas.refresh()

    def set_fill(self, brush) -> None:
        """Fill down to zero with *brush* (``None``: no fill)."""
        colour = self.state.get("color", (200, 200, 200))
        self.state["fill"] = None if brush is None else _rgba(brush, (*colour, 90))
        self._canvas.refresh()

    def set_symbol(self, symbol) -> None:
        """Set the marker drawn at each sample (``None`` for a bare line)."""
        self.state["symbol"] = symbol
        self._canvas.refresh()

    def set_symbol_size(self, size: float) -> None:
        """Set the marker size in pixels."""
        self.state["symbol_size"] = float(size)
        self._canvas.refresh()

    def set_symbol_brush(self, brush) -> None:
        """Set the marker fill."""
        self.state["symbol_color"] = _rgb(brush, self.state.get("color", (200, 200, 200)))
        self._canvas.refresh()

    def set_opacity(self, alpha: float) -> None:
        """Set the series' opacity, 0 to 1."""
        self.state["opacity"] = float(alpha)
        self._canvas.refresh()

    def set_downsampling(self, *_args: Any, **_kwargs: Any) -> None:
        """No-op: emtk draws the samples it is given."""

    def set_clip_to_view(self, *_args: Any, **_kwargs: Any) -> None:
        """No-op: emtk clips to the plot box already."""

    # -- Image ---------------------------------------------------------
    def set_image(self, data, **_: Any) -> None:
        """Replace the image's samples, keeping its colours and levels."""
        colours = np.ndim(data) == 3 and np.shape(data)[-1] in (3, 4)
        self.state["data"] = np.asarray(data) if colours else np.asarray(data, dtype=float)
        self.state["texture"] = None
        self._canvas.refresh()

    def set_levels(self, low: float, high: float) -> None:
        """Set the ``(low, high)`` the colours span."""
        self.state["levels"] = (float(low), float(high))
        self.state["texture"] = None
        self._canvas.refresh()

    def auto_levels(self) -> None:
        """Span the colours over the data's own finite range again."""
        self.state["levels"] = None
        self.state["texture"] = None
        self._canvas.refresh()

    def get_image(self) -> np.ndarray:
        """The image data as last set."""
        return self.state["data"]

    def get_levels(self) -> tuple[float, float]:
        """The ``(low, high)`` the colours span: the set levels, or the data's range."""
        levels = self.state.get("levels")
        if levels is not None:
            return (float(levels[0]), float(levels[1]))
        values = np.asarray(self.state.get("data", []), dtype=float)
        finite = values[np.isfinite(values)]
        return (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)

    def set_colormap(self, colormap) -> None:
        """Set the colormap the samples are mapped through."""
        self.state["colormap"] = colormap
        self.state["texture"] = None
        self._canvas.refresh()

    def set_rect(self, x: float, y: float, w: float, h: float) -> None:
        """Place the image in data coordinates."""
        self.state["rect"] = (float(x), float(y), float(w), float(h))
        self._canvas.refresh()

    def clear(self) -> None:
        """Show nothing until the next :meth:`set_image`."""
        self.state["data"] = np.zeros((0, 0))
        self.state["texture"] = None
        self._canvas.refresh()

    # -- Roi -----------------------------------------------------------
    @property
    def pos(self) -> tuple[float, float]:
        """The shape's origin in data coordinates."""
        x, y = self.state.get("pos", (0.0, 0.0))
        return (float(x), float(y))

    @property
    def size(self) -> tuple[float, float]:
        """The shape's ``(width, height)`` in data coordinates."""
        w, h = self.state.get("size", (1.0, 1.0))
        return (float(w), float(h))

    @property
    def angle(self) -> float:
        """Degrees counter-clockwise: an arrow's direction, or a shape's turn."""
        return float(self.state.get("angle", 0.0))

    @property
    def movable(self) -> bool:
        """Whether the user can drag the shape."""
        return bool(self.state.get("movable", True))

    @property
    def pen_color(self) -> str:
        """The outline colour as ``"#rrggbb"``."""
        return "#{:02x}{:02x}{:02x}".format(*tuple(self.state.get("color", (200, 200, 200))))

    @property
    def points(self) -> list[tuple[float, float]]:
        """The vertices of a polygon or polyline, in data coordinates."""
        return [(float(x), float(y)) for x, y in self.state.get("points", [])]

    def set_pos(self, x, y=None) -> None:
        """Move the shape's origin, as ``(x, y)`` or as one pair."""
        if y is None:
            x, y = x
        previous = self.pos
        self.state["pos"] = (float(x), float(y))
        if self.state.get("points"):
            dx = self.state["pos"][0] - previous[0]
            dy = self.state["pos"][1] - previous[1]
            self.state["points"] = [(x + dx, y + dy) for x, y in self.state["points"]]
        self._canvas.refresh()

    def set_size(self, width, height=None) -> None:
        """Resize the shape, as ``(width, height)`` or as one pair."""
        if height is None:
            width, height = width
        self.state["size"] = (float(width), float(height))
        self._canvas.refresh()

    # -- Bars / error bars / text --------------------------------------
    def set_bar_data(self, x, height) -> None:
        """Replace a bar graph's samples."""
        self.state["x"], self.state["height"] = _finite_pairs(x, height)
        self._canvas.refresh()

    @property
    def text(self) -> str:
        """The label's text."""
        return str(self.state.get("text", ""))

    @text.setter
    def text(self, value: str) -> None:
        self.state["text"] = str(value)
        self._canvas.refresh()

    @property
    def position(self) -> tuple[float, float]:
        """Where the label or arrow tip is, in data coordinates."""
        x, y = self.state.get("pos", (0.0, 0.0))
        return (float(x), float(y))

    def set_angle(self, angle: float) -> None:
        """Turn the arrow (degrees counter-clockwise from ``+x``) or the shape."""
        self.state["angle"] = float(angle)
        self._canvas.refresh()

    def set_position(self, x, y=None) -> None:
        """Move the label or arrow tip, as ``(x, y)`` or as one pair."""
        if y is None:
            x, y = x
        self.state["pos"] = (float(x), float(y))
        self._canvas.refresh()

    # -- Region --------------------------------------------------------
    @property
    def bounds(self) -> tuple[float, float]:
        """The ``(low, high)`` edges in data coordinates."""
        low, high = self.state.get("bounds", (0.0, 1.0))
        return (float(low), float(high))

    def set_brush(self, brush) -> None:
        """Restyle the band's fill, keeping its alpha."""
        self.state["brush"] = _rgba(brush, self.state.get("brush", (70, 110, 160, 50)))
        self._canvas.refresh()

    def set_bounds(self, low: float, high: float) -> None:
        """Move the region, keeping it inside its limits."""
        low, high = float(min(low, high)), float(max(low, high))
        limits = self.state.get("limits")
        if limits is not None:
            span = high - low
            low = max(low, float(limits[0]))
            high = min(max(low + span, high), float(limits[1]))
            low = min(low, high)
        self.state["bounds"] = (low, high)
        self._canvas.refresh()

    def set_limits(self, low: float, high: float) -> None:
        """Constrain where the region may be dragged."""
        self.state["limits"] = (float(low), float(high))
        self.set_bounds(*self.bounds)

    def _notify(self, final: bool) -> None:
        """Tell the drag listeners where this element is now."""
        for callback, wants_final in self.state.get("callbacks", []):
            if wants_final and not final:
                continue
            if self.kind == "region":
                callback(*self.bounds)
            else:
                callback(self.value)

    # -- Marker --------------------------------------------------------
    @property
    def value(self) -> float:
        """The marker's position along its axis."""
        return float(self.state.get("value", 0.0))

    def set_value(self, value: float) -> None:
        """Move the marker."""
        self.state["value"] = float(value)
        self._canvas.refresh()

    def on_change(self, callback, *, final: bool = True, **_: Any) -> None:
        """Fire ``callback`` while (``final=False``) or after a drag."""
        self.state.setdefault("callbacks", []).append((callback, bool(final)))


class _BarsEntry(_Entry):
    """A bar graph's entry: its samples are bar positions and *heights*.

    The generic :meth:`_Entry.set_data` writes ``x``/``y``, which a bar graph
    never draws (it reads ``height``), so replacing a histogram's bars through
    the :class:`~chisurf.chiplot.handles.Bars` handle left the old bars on
    screen.
    """

    def set_data(self, x, y=None, height=None, **kwargs: Any) -> None:
        """Replace the bar positions and heights (positionally, or ``height=``)."""
        heights = y if height is None else height
        self.state["x"], self.state["height"] = _finite_pairs(x, heights)
        self._canvas.refresh()

    def get_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the bars as ``(x, height)``."""
        return self.state["x"], self.state["height"]


@dataclass
class _Grab:
    """What a press picked up, and where the gesture was last seen.

    ``mode`` says which of the payload fields matter:

    * ``"text"`` -- a label; ``point`` is the last pointer position in pixels.
    * ``"roi"`` -- a whole region of interest; ``point`` in data coordinates.
    * ``"grip"`` -- a ROI corner; ``point`` is the *opposite*, fixed corner.
    * ``"edge"`` -- one edge (``edge`` is ``"low"``/``"high"``) of an interval
      region; ``value`` is where it was last put.
    * ``"move"`` -- a whole interval region or a marker; ``value`` is the last
      pointer position along its axis.
    """

    entry: _Entry
    mode: str
    point: tuple[float, float] = (0.0, 0.0)
    edge: str = ""
    value: float = 0.0


class EmtkCanvas(base.Canvas):
    """A chiplot panel drawn by emtk from a display list."""

    #: The press's catch while a drag is under way.
    _dragging: _Grab | None = None
    #: Where a pan was grabbed, in data coordinates.
    _panning: tuple[float, float] | None = None

    def __init__(self, *, title: str | None = None, background=None, **_: Any) -> None:
        self._entries: list[_Entry] = []
        self._title = title or ""
        self._labels: dict[str, str] = {}
        self._units: dict[str, str] = {}
        self._si_prefix = {"x": False, "y": False}
        self._log = {"x": False, "y": False}
        self._range: dict[str, tuple[float, float] | None] = {"x": None, "y": None}
        self._grid = True
        #: Factor on the theme's gridlines (``grid(alpha=...)`` relative to chiplot's default).
        self._grid_strength = 1.0
        self._tick_width = _Y_TICK_WIDTH
        self._legend = False
        self._background = _rgb(background, (30, 32, 38))
        self._interactive = True
        self._y_inverted = False
        self._axis_visible = {"left": True, "bottom": True}
        self._tick_text = _TICK_TEXT
        self._label_text = _LABEL_TEXT
        self._axis_line: tuple[int, int, int] | None = None
        self._legend_text: tuple[int, int, int] | None = None
        self._custom_ticks: dict[str, list[tuple[float, str]]] = {}
        #: Panels whose x axes move together (see :meth:`link_x`); every member
        #: holds the same list, so linking a third panel reaches all of them.
        self._x_group: list[EmtkCanvas] = [self]
        #: The ranges the last frame was drawn with, in axis units (exponents on
        #: a log axis) -- what a pan or zoom starts from. ``_range`` holds what a
        #: caller set, in data units, as chiplot's contract has it.
        self._drawn = {"x": None, "y": None}
        self._click_callbacks: list[Callable] = []
        self._move_callbacks: list[Callable] = []
        self._range_callbacks: list[Callable] = []
        #: ``(ratio)`` while the axes keep equal pixels per unit, else ``None``.
        self._aspect: float | None = None
        #: ``handler(phase, x, y)`` taking over the left drag (painting), else ``None``.
        self._paint: Callable | None = None
        self._painting = False
        #: What shows this panel, if anything attached itself (:meth:`attach_host`).
        #: A panel drawn as a control by an emtk surface has none.
        self._host: Any = None
        #: The "A" button (:mod:`emtk.widgets.auto_range`): shown while an axis
        #: is not auto-ranged unless a caller opted out; where the last frame
        #: drew it (``None`` when hidden) and whether the pointer is on it.
        self._auto_button = True
        self._auto_button_rect: tuple[float, float, float, float] | None = None
        self._auto_button_hovered = False

    # -- the host ------------------------------------------------------
    def attach_host(self, host: Any) -> None:
        """Let *host* show this panel; ``None`` detaches the current one.

        A host is duck-typed: ``update()`` repaints it, and the optional
        ``size()`` (``(width, height)`` in pixels) and ``set_background(rgb)``
        let an export match what it shows and a background change reach it.
        """
        self._host = host
        if host is not None:
            setter = getattr(host, "set_background", None)
            if callable(setter):
                setter(self._background)

    @property
    def host(self) -> Any:
        """The attached host, or ``None``."""
        return self._host

    def set_refresh_target(self, callback: Callable[[], None] | None) -> None:
        """Send repaint requests to *callback* instead of this panel's own widget.

        A panel drawn as a control inside a larger emtk surface (a fit window's
        page) is not shown in its own host widget, so repainting that widget
        shows nothing: a new curve would wait for the next mouse move. The
        surface that draws the panel installs its frame request here.
        ``None`` restores the panel's own widget.
        """
        self._refresh_target = callback

    def refresh(self) -> None:
        """Ask whatever shows this panel to repaint."""
        target = getattr(self, "_refresh_target", None)
        if target is not None:
            target()
            return
        update = getattr(self._host, "update", None)
        if callable(update):
            update()

    # -- what emtk's host calls ---------------------------------------
    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        """Draw the whole display list, with its axes, into the box emtk gives us.

        The box is split into gutters and a plot area: the y tick numbers and
        the rotated y title on the left, the x tick numbers and title below,
        the title above. The left gutter has a fixed width, so the residual
        strips stacked over a decay keep their axes on one vertical line.
        """
        scale = _chrome_scale()
        scaled = scale != 1.0 and callable(getattr(painter, "set_font_scale", None))
        if scaled:
            painter.set_font_scale(scale)
        try:
            self._draw_scaled(painter, x, y, w, h, scale if scaled else 1.0)
        finally:
            if scaled:
                painter.set_font_scale(1.0)

    def _draw_scaled(self, painter, x: float, y: float, w: float, h: float, scale: float) -> None:
        """:meth:`draw` with the axis text already at the plot font size (*scale* of the UI's)."""
        from emtk.widgets.plot import Plot as EmtkPlot

        self._last_box = (x, y, w, h)
        self._tick_width = _Y_TICK_WIDTH * scale
        row = float(painter.line_height())
        left_axis, bottom_axis = self._axis_visible["left"], self._axis_visible["bottom"]
        gutter_left = (row + 2.0 + self._tick_width + 6.0) if left_axis else 4.0
        gutter_bottom = 4.0
        if bottom_axis:
            gutter_bottom += row + 2.0
            if self._labels.get("bottom") or self._units.get("bottom"):
                gutter_bottom += row
        gutter_top = row + 2.0 if self._title else 6.0
        gutter_right = 10.0
        bx, by = x + gutter_left, y + gutter_top
        bw = max(w - gutter_left - gutter_right, 8.0)
        bh = max(h - gutter_top - gutter_bottom, 8.0)

        x_range = self._to_axis("x", self._range["x"]) or self._group_x_extent()
        y_range = self._to_axis("y", self._range["y"]) or self._fitted(1, 0.04)
        if self._aspect is not None and x_range and y_range:
            # Equal pixels per unit on both axes: the box shrinks to the range's
            # proportions and sits in the middle of what the panel was given.
            span_x, span_y = abs(x_range[1] - x_range[0]), abs(y_range[1] - y_range[0])
            if span_x > 0.0 and span_y > 0.0:
                unit = min(bw / span_x, bh / (span_y * self._aspect))
                fitted_w, fitted_h = span_x * unit, span_y * unit * self._aspect
                bx, by = bx + (bw - fitted_w) / 2.0, by + (bh - fitted_h) / 2.0
                bw, bh = max(fitted_w, 8.0), max(fitted_h, 8.0)
        plot = EmtkPlot(
            bx,
            by,
            bw,
            bh,
            x_range=x_range,
            y_range=y_range,
            show_ticks=self._grid,
            show_legend=self._legend,
        )
        plot.y_inverted = self._y_inverted
        plot.grid_opacity = self._grid_strength
        plot.show_y_tick_labels = False
        plot.x_tick_target = max(2, int(bw // 90))
        plot.y_tick_target = max(3, int(bh // 36))
        plot._x_axis.log_decades = self._log["x"]
        plot._y_axis.log_decades = self._log["y"]
        # The pictures go down first, so what is drawn over them -- curves,
        # markers, shapes -- is not hidden by them.
        plot.underlays.append(self._draw_images)
        plot.underlays.append(self._draw_regions)
        for entry in sorted(self._entries, key=lambda e: e.z):
            if not entry.visible:
                continue
            self._draw_entry(plot, entry)
        plot.draw(painter)
        self._drawn = {"x": plot._x_axis.range, "y": plot._y_axis.range}
        # After the axes exist: the plot places its own box and axis ranges in
        # draw(), and bands, shapes and marks are positioned in data
        # coordinates, so they cannot be drawn before that mapping is known.
        painter.push_clip(plot.x, plot.y, plot.w, plot.h)
        try:
            self._draw_bands(painter, plot)
            self._draw_marks(painter, plot)
        finally:
            painter.pop_clip()
        self._draw_axes(painter, plot, x, y, w, h, row)
        self._draw_texts(painter, plot)
        self._draw_auto_range_button(painter, plot, (x, y, w, h))

    def _auto_button_shown(self) -> bool:
        """Whether the "A" button shows: an axis left auto-range and the user can pan."""
        return self._auto_button and self._interactive and not all(self.is_auto_range())

    def _draw_auto_range_button(self, painter, plot, box) -> None:
        """The "A" in the plot area's lower-left while the view is not auto-ranged."""
        if not self._auto_button_shown():
            self._auto_button_rect = None
            self._auto_button_hovered = False
            return
        from emtk.widgets import auto_range

        rect = auto_range.button_rect(plot.x, plot.y, plot.w, plot.h)
        self._auto_button_rect = rect
        auto_range.draw(painter, rect, self._auto_button_hovered)
        if self._auto_button_hovered:
            auto_range.draw_tooltip(painter, rect, box)

    def _on_auto_button(self, px: float, py: float) -> bool:
        """Whether ``(px, py)`` is on the "A" button drawn last frame."""
        from emtk.widgets import auto_range

        return self._auto_button_shown() and auto_range.contains(self._auto_button_rect, px, py)

    def set_auto_range_button(self, shown: bool) -> None:
        """Show (default) or never show the "A" auto-range button on this panel."""
        self._auto_button = bool(shown)
        self.refresh()

    def _draw_images(self, painter, plot) -> None:
        """Blit the images ``_draw_entry`` collected, under the series."""
        for texture, x0, y0, width, height in getattr(plot, "_images", []):
            left = plot._x_axis.to_pixels(x0)
            right = plot._x_axis.to_pixels(x0 + width)
            top = plot._y_axis.to_pixels(y0 + height)
            bottom = plot._y_axis.to_pixels(y0)
            painter.image(
                min(left, right), min(top, bottom), abs(right - left), abs(bottom - top), texture
            )

    def _draw_marks(self, painter, plot) -> None:
        """Draw the symbol sets over everything else in the plot area."""
        for entry in sorted(self._entries, key=lambda e: e.z):
            if not entry.visible or entry.kind != "marks":
                continue
            state = entry.state
            xs, ys = state["x"], state["y"]
            pixels = [
                (plot._x_axis.to_pixels(float(px)), plot._y_axis.to_pixels(float(py)))
                for px, py in zip(xs, ys)
            ]
            for px, py in pixels:
                _draw_symbol(
                    painter,
                    px,
                    py,
                    str(state.get("symbol", "o")),
                    float(state.get("size", 7.0)),
                    state.get("brush"),
                    state.get("pen"),
                    float(state.get("width", 1.0)),
                )

    def _axis_display(
        self,
        side: str,
        ticks: list[float],
        span: tuple[float, float],
    ) -> tuple[list[str], str]:
        """Format ticks and units together without changing their coordinates."""
        axis = "y" if side == "left" else "x"
        title, units = self._labels.get(side, ""), self._units.get(side, "")
        exponent = 0
        if self._si_prefix[axis] and (title or units):
            magnitude = max(span) if self._log[axis] else max(abs(v) for v in span)
            order = magnitude if self._log[axis] else math.log10(magnitude) if magnitude > 0 else 0
            exponent = max(-24, min(24, 3 * math.floor(order / 3)))
            # Match AxisItem: unitless thousand/milli prefixes are distracting.
            if not units and exponent in (-3, 3):
                exponent = 0
        prefix = "yzafpnµm kMGTPEZY"[exponent // 3 + 8].strip()
        display_ticks = (
            [v - exponent for v in ticks]
            if self._log[axis]
            else [v / 10.0**exponent for v in ticks]
        )
        suffix = f" ({prefix}{units})" if units else f" (×{10.0**exponent:g})" if exponent else ""
        return _tick_labels(display_ticks, self._log[axis]), (title + suffix).strip()

    def _draw_axes(self, painter, plot, x, y, w, h, row) -> None:
        """Tick numbers, axis titles and the panel title, around the plot area."""
        from emtk.painter import ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER

        bx, by, bw, bh = plot.x, plot.y, plot.w, plot.h
        if self._axis_visible["left"]:
            ticks = plot._y_axis.ticks(plot.y_tick_target)
            tick_text, label = self._axis_display("left", ticks, plot._y_axis.range)
            if "left" in self._custom_ticks:
                ticks = [t for t, _ in self._custom_ticks["left"]]
                tick_text = [text for _, text in self._custom_ticks["left"]]
            for value, text in zip(ticks, tick_text):
                py = plot._y_axis.to_pixels(value)
                if by - 1.0 <= py <= by + bh + 1.0:
                    painter.text(
                        bx - self._tick_width - 6.0,
                        py - row * 0.5,
                        self._tick_width,
                        row,
                        ALIGN_RIGHT | ALIGN_VCENTER,
                        text,
                        self._tick_text,
                    )
            if label:
                if hasattr(painter, "text_rotated"):
                    cx = x + 2.0 + row * 0.5
                    cy = by + bh * 0.5
                    painter.text_rotated(
                        cx - bh * 0.5,
                        cy - row * 0.5,
                        bh,
                        row,
                        ALIGN_HCENTER | ALIGN_VCENTER,
                        label,
                        self._label_text,
                        -90.0,
                    )
                else:
                    painter.text(
                        x + 2.0, by, bx - x - 4.0, row, ALIGN_VCENTER, label, self._label_text
                    )
        if self._axis_visible["bottom"]:
            ticks = plot._x_axis.ticks(plot.x_tick_target)
            tick_text, label = self._axis_display("bottom", ticks, plot._x_axis.range)
            if "bottom" in self._custom_ticks:
                ticks = [t for t, _ in self._custom_ticks["bottom"]]
                tick_text = [text for _, text in self._custom_ticks["bottom"]]
            for value, text in zip(ticks, tick_text):
                px = plot._x_axis.to_pixels(value)
                if bx - 1.0 <= px <= bx + bw + 1.0:
                    painter.text(
                        min(max(px - 40.0, x), x + w - 80.0),
                        by + bh + 2.0,
                        80.0,
                        row,
                        ALIGN_HCENTER | ALIGN_VCENTER,
                        text,
                        self._tick_text,
                    )
            if label:
                painter.text(
                    bx,
                    by + bh + 2.0 + row,
                    bw,
                    row,
                    ALIGN_HCENTER | ALIGN_VCENTER,
                    label,
                    self._label_text,
                )
        if self._title:
            painter.text(
                bx, y + 1.0, bw, row, ALIGN_HCENTER | ALIGN_VCENTER, self._title, self._label_text
            )

    def _extent(self, axis: int) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
        """What is drawn along *axis*, in axis coordinates (log10 on a log axis).

        Two spans: the samples of curves and scatter clouds, which get padding
        so no point sits on the frame, and what is placed exactly (an image's
        rect, a region), which does not -- a heatmap fills its panel. Either is
        ``None`` when there is nothing of that kind.
        """
        low, high = math.inf, -math.inf
        exact_low, exact_high = math.inf, -math.inf
        for entry in self._entries:
            if not entry.visible:
                continue
            state = entry.state
            if entry.kind in ("curve", "scatter"):
                xs, ys = self._scaled(state["x"], state["y"])
                values = np.asarray(xs if axis == 0 else ys, dtype=float)
                values = values[np.isfinite(values)]
                if values.size:
                    low, high = min(low, float(values.min())), max(high, float(values.max()))
            elif entry.kind == "bars":
                values = self._bar_values(state, axis)
                if self._log["x" if axis == 0 else "y"]:
                    values = np.log10(values[values > 0.0])
                values = values[np.isfinite(values)]
                if values.size:
                    low, high = min(low, float(values.min())), max(high, float(values.max()))
            elif entry.kind == "image":
                x0, y0, width, height = state["rect"]
                start, extent = (x0, width) if axis == 0 else (y0, height)
                exact_low = min(exact_low, float(start))
                exact_high = max(exact_high, float(start + extent))
            elif entry.kind == "region" and (axis == 1) == (
                entry.state.get("orientation") == "horizontal"
            ):
                a, b = entry.bounds
                exact_low, exact_high = min(exact_low, a), max(exact_high, b)
        if high >= low and self._log["x" if axis == 0 else "y"]:
            # Positive and finite is not the same as meaningful: an underflowed
            # tail (a Gaussian IRF reaches 1e-313) would stretch the axis over
            # hundreds of decades and its padding far above the data.
            low = max(low, high - LOG_AUTOSCALE_DECADES)
        return (
            (low, high) if high >= low else None,
            (exact_low, exact_high) if exact_high >= exact_low else None,
        )

    def _fitted(self, axis: int, fraction: float, members=None) -> tuple[float, float] | None:
        """The auto-fitted range of *axis* over *members* (default: this panel)."""
        series: list[tuple[float, float]] = []
        exact: list[tuple[float, float]] = []
        for member in members or (self,):
            data, placed = member._extent(axis)
            if data is not None:
                series.append(data)
            if placed is not None:
                exact.append(placed)
        spans: list[tuple[float, float]] = []
        if series:
            padded = self._padded(
                (min(a for a, _ in series), max(b for _, b in series)), fraction
            )
            if padded is not None:
                spans.append(padded)
        spans.extend(exact)
        if not spans:
            return None
        return (min(a for a, _ in spans), max(b for _, b in spans))

    @staticmethod
    def _padded(span, fraction: float) -> tuple[float, float] | None:
        """*span* widened by *fraction* of itself each side, so no sample sits on the frame."""
        if span is None:
            return None
        low, high = span
        margin = (high - low) * fraction if high > low else max(abs(low) * 0.05, 0.5)
        return (low - margin, high + margin)

    def _group_x_extent(self) -> tuple[float, float] | None:
        """The x range every linked panel auto-fits to: the union of their data."""
        return self._fitted(0, 0.01, self._x_group)

    def _draw_entry(self, plot, entry: _Entry) -> None:
        """Add one display-list entry to *plot*."""
        state = entry.state
        label = state.get("name") or ""
        opacity = float(state.get("opacity", 1.0))
        if entry.kind == "curve":
            xs, ys = self._scaled(state["x"], state["y"], gaps=state.get("gaps", False))
            if xs.size and state.get("line", True):
                plot.line(
                    label,
                    xs,
                    ys,
                    colour=_faded(state.get("color"), opacity),
                    width=state.get("width", 1.5),
                )
            if state.get("symbol") is not None and xs.size:
                marked = np.isfinite(xs) & np.isfinite(ys)
                plot.scatter(
                    label,
                    xs[marked],
                    ys[marked],
                    colour=_faded(state.get("symbol_color", state.get("color")), opacity),
                    radius=max(1.0, float(state.get("symbol_size", 7.0)) / 2.0),
                )
        elif entry.kind == "scatter":
            xs, ys = self._scaled(state["x"], state["y"])
            if xs.size:
                plot.scatter(
                    label,
                    xs,
                    ys,
                    colour=_faded(state.get("color"), opacity),
                    radius=max(1.0, float(state.get("symbol_size", 7.0)) / 2.0),
                )
        elif entry.kind == "image":
            self._draw_image(plot, entry)
        elif entry.kind == "marker":
            if state.get("orientation") == "horizontal":
                plot.hline(
                    float(state.get("value", 0.0)),
                    state.get("color", (200, 200, 200)),
                    label or None,
                )
            else:
                # A vertical guide: emtk's Plot draws horizontal ones, so this
                # is a one-pixel band drawn with the regions below.
                plot._x_axis.fit((entry.value, entry.value))
        elif entry.kind == "region":
            pass  # counted by `_extent`, drawn under the series by `_draw_regions`
        elif entry.kind == "arrow":
            x, y = entry.position
            plot._x_axis.fit((x,))
            plot._y_axis.fit((y,))

    def _draw_bands(self, painter, plot) -> None:
        """Draw the regions and vertical markers, and record where they are.

        Both are placed in data coordinates, so this runs after ``plot.draw``
        has mapped the axes onto the box -- and the pixel span each one landed
        at is kept, because that is what a press has to hit to start a drag.
        """
        top, height = plot.y, plot.h
        for entry in self._entries:
            if not entry.visible:
                continue
            if entry.kind == "marker" and entry.state.get("orientation") != "horizontal":
                at = plot._x_axis.to_pixels(entry.value)
                painter.fill_rect(at, top, 1.0, height, entry.state.get("color", (200, 200, 200)))
                entry.state["_pixels"] = (at - 4.0, at + 4.0)
            elif entry.kind == "roi":
                self._draw_roi(painter, plot, entry)
            elif entry.kind == "arrow":
                self._draw_arrow(painter, plot, entry)
            elif entry.kind == "bars":
                self._draw_bars(painter, plot, entry)
            elif entry.kind == "band":
                self._draw_band(painter, plot, entry)
            elif entry.kind == "errorbars":
                self._draw_errorbars(painter, plot, entry)
        self._axis = plot._x_axis
        self._y_axis_cache = plot._y_axis

    def _draw_regions(self, painter, plot) -> None:
        """Shade each region under the series, with a line on either edge.

        Called by the plot between its gridlines and its series: a fit range
        is a statement about where the data is read, and drawn over the data
        it tinted every curve the colour of the selector. The edges are what
        a press grabs, so they are drawn where the eye can find them.
        """
        top, height = plot.y, plot.h
        for entry in self._entries:
            if entry.visible and entry.kind == "curve" and entry.state.get("fill") is not None:
                self._draw_curve_fill(painter, plot, entry)
        for entry in self._entries:
            if not entry.visible or entry.kind != "region":
                continue
            low, high = entry.bounds
            fill = entry.state.get("brush", (70, 110, 160, 50))
            edge = (*fill[:3], 220)
            if entry.state.get("orientation") == "horizontal":
                upper, lower = sorted(
                    _on_screen(plot._y_axis.to_pixels(v), plot.y, plot.h) for v in (low, high)
                )
                painter.fill_rect(plot.x, upper, plot.w, lower - upper, fill)
                for at in (upper, lower):
                    painter.fill_rect(plot.x, at - 0.75, plot.w, 1.5, edge)
                entry.state["_pixels"] = (upper, lower)
                continue
            left, right = sorted(
                _on_screen(plot._x_axis.to_pixels(v), plot.x, plot.w) for v in (low, high)
            )
            painter.fill_rect(left, top, right - left, height, fill)
            for at in (left, right):
                painter.fill_rect(at - 0.75, top, 1.5, height, edge)
            entry.state["_pixels"] = (left, right)

    def _draw_texts(self, painter, plot) -> None:
        """Draw the text labels last, over everything, each in its own box.

        An ``anchored`` label sits at a pixel offset from the plot area's
        top-left and stays put when the view moves; any other is placed at a
        data coordinate. A label may span lines, and a box is sized to them.
        """
        from emtk.painter import ALIGN_LEFT, ALIGN_VCENTER

        row = float(painter.line_height())
        pad = 5.0
        for entry in self._entries:
            if not entry.visible or entry.kind != "text" or not entry.text:
                continue
            state = entry.state
            if state.get("anchored"):
                ox, oy = state["pos"]
                left, top = plot.x + ox, plot.y + oy
            else:
                px, py = state["pos"]
                left, top = plot._x_axis.to_pixels(px), plot._y_axis.to_pixels(py)
            lines = entry.text.split("\n")
            width = max(painter.text_width(line) for line in lines) + 2.0 * pad
            height = row * len(lines) + 2.0 * pad
            anchor_x, anchor_y = state.get("anchor") or (0.0, 0.0)
            left -= width * anchor_x
            top -= height * anchor_y
            if state.get("anchored"):
                # Kept inside the plot area, so a label dragged to an edge or
                # left behind by a resize is never lost off the panel.
                left = min(max(left, plot.x), plot.x + max(plot.w - width, 0.0))
                top = min(max(top, plot.y), plot.y + max(plot.h - height, 0.0))
            fill, border = state.get("fill"), state.get("border")
            if fill is not None:
                painter.fill_rect(left, top, width, height, fill)
            if border is not None:
                painter.stroke_rect(left, top, width, height, border)
            colour = state.get("color", (220, 220, 220))
            for index, line in enumerate(lines):
                painter.text(
                    left + pad,
                    top + pad + index * row,
                    width - 2.0 * pad,
                    row,
                    ALIGN_LEFT | ALIGN_VCENTER,
                    line,
                    colour,
                )
            state["_box"] = (left, top, left + width, top + height)

    def _draw_roi(self, painter, plot, entry: _Entry) -> None:
        """Draw a region of interest and record the box a press has to hit."""
        colour = entry.state.get("color", (240, 200, 90))
        kind = entry.state.get("roi_kind", "rect")
        if kind in ("polygon", "polyline") and entry.points:
            xs = [plot._x_axis.to_pixels(x) for x, _ in entry.points]
            ys = [plot._y_axis.to_pixels(y) for _, y in entry.points]
            for index in range(len(xs) - (0 if kind == "polygon" else 1)):
                nxt = (index + 1) % len(xs)
                painter.fill_triangle(
                    (xs[index], ys[index]), (xs[nxt], ys[nxt]), (xs[index], ys[nxt]), (*colour, 60)
                )
                _stroke_segment(
                    painter, (xs[index], ys[index]), (xs[nxt], ys[nxt]), 1.5, (*colour, 255)
                )
            entry.state["_box"] = (min(xs), min(ys), max(xs), max(ys))
            return

        x, y = entry.pos
        width, height = entry.size
        if entry.angle:
            self._draw_rotated_roi(painter, plot, entry, kind, colour)
            return
        left = plot._x_axis.to_pixels(x)
        right = plot._x_axis.to_pixels(x + width)
        top = plot._y_axis.to_pixels(y + height)
        bottom = plot._y_axis.to_pixels(y)
        box = (min(left, right), min(top, bottom), abs(right - left), abs(bottom - top))
        if kind == "ellipse":
            # A fan of triangles: the painter draws rectangles and triangles,
            # and an ellipse is neither.
            cx, cy = box[0] + box[2] / 2.0, box[1] + box[3] / 2.0
            rx, ry = box[2] / 2.0, box[3] / 2.0
            steps = 24
            previous = (cx + rx, cy)
            for step in range(1, steps + 1):
                angle = 2.0 * math.pi * step / steps
                point = (cx + rx * math.cos(angle), cy + ry * math.sin(angle))
                painter.fill_triangle((cx, cy), previous, point, (*colour, 40))
                _stroke_segment(painter, previous, point, 1.5, (*colour, 255))
                previous = point
        else:
            painter.stroke_rect(*box, colour, (*colour, 40))
        entry.state["_box"] = (box[0], box[1], box[0] + box[2], box[1] + box[3])
        self._draw_grips(painter, plot, entry, colour)

    #: Half the side of a resize grip, in pixels.
    GRIP = 4.0

    def _grip_at(self, entry: _Entry, px: float, py: float) -> str | None:
        """``"lo"`` or ``"hi"`` when the press is on a resize grip of *entry*."""
        grips = entry.state.get("_grips")
        if not entry.state.get("resizable") or not entry.state.get("movable", True) or not grips:
            return None
        for name, (gx, gy) in grips.items():
            if abs(px - gx) <= self.GRIP + 2.0 and abs(py - gy) <= self.GRIP + 2.0:
                return name
        return None

    def _draw_grips(self, painter, plot, entry: _Entry, colour) -> None:
        """Square grips on the low and high corners of a resizable shape."""
        if not entry.state.get("resizable") or not entry.state.get("movable", True):
            entry.state.pop("_grips", None)
            return
        x, y = entry.pos
        width, height = entry.size
        grips = {
            "lo": (plot._x_axis.to_pixels(x), plot._y_axis.to_pixels(y)),
            "hi": (plot._x_axis.to_pixels(x + width), plot._y_axis.to_pixels(y + height)),
        }
        entry.state["_grips"] = grips
        for gx, gy in grips.values():
            painter.fill_rect(
                gx - self.GRIP, gy - self.GRIP, 2 * self.GRIP, 2 * self.GRIP, (*colour, 255)
            )
            painter.stroke_rect(
                gx - self.GRIP, gy - self.GRIP, 2 * self.GRIP, 2 * self.GRIP, (20, 22, 28, 255)
            )

    def _draw_arrow(self, painter, plot, entry: _Entry) -> None:
        """A filled head with its tip at ``pos``, sized in pixels.

        The direction is a data-space angle, so it is mapped through both axes:
        an inverted or anisotropic panel still points the arrow along the data.
        """
        state = entry.state
        x, y = state["pos"]
        theta = math.radians(state["angle"])
        tip = (plot._x_axis.to_pixels(x), plot._y_axis.to_pixels(y))
        (x_lo, x_hi), (y_lo, y_hi) = plot._x_axis.range, plot._y_axis.range
        step = 1e-3 * max(abs(x_hi - x_lo), abs(y_hi - y_lo), 1e-12)
        ahead = (
            plot._x_axis.to_pixels(x + step * math.cos(theta)),
            plot._y_axis.to_pixels(y + step * math.sin(theta)),
        )
        ux, uy = ahead[0] - tip[0], ahead[1] - tip[1]
        norm = math.hypot(ux, uy)
        if not math.isfinite(norm) or norm == 0.0:
            return
        ux, uy = ux / norm, uy / norm
        nx, ny = -uy, ux
        size = state["size"]
        half = (
            state["head_width"] / 2.0
            if state["head_width"] is not None
            else size * math.tan(math.radians(state["tip_angle"]) / 2.0)
        )
        base = (tip[0] - ux * size, tip[1] - uy * size)
        colour = (*state.get("color", (220, 220, 220)), 255)
        painter.fill_triangle(
            tip,
            (base[0] + nx * half, base[1] + ny * half),
            (base[0] - nx * half, base[1] - ny * half),
            colour,
        )
        if state["tail_length"]:
            w = state["tail_width"] / 2.0
            end = (base[0] - ux * state["tail_length"], base[1] - uy * state["tail_length"])
            a, b = (base[0] + nx * w, base[1] + ny * w), (base[0] - nx * w, base[1] - ny * w)
            c, d = (end[0] - nx * w, end[1] - ny * w), (end[0] + nx * w, end[1] + ny * w)
            painter.fill_triangle(a, b, c, colour)
            painter.fill_triangle(a, c, d, colour)

    def _draw_rotated_roi(self, painter, plot, entry: _Entry, kind: str, colour) -> None:
        """A rectangle or ellipse turned about its centre, as pyqtgraph turns one.

        Rotated in data coordinates and only then mapped to pixels, so an
        inverted or non-square axis shows the same gate the data describes.
        """
        x, y = entry.pos
        width, height = entry.size
        cx, cy = x + width / 2.0, y + height / 2.0
        theta = math.radians(entry.angle)
        cos, sin = math.cos(theta), math.sin(theta)
        if kind == "ellipse":
            steps = 36
            local = [
                (
                    width / 2.0 * math.cos(2.0 * math.pi * k / steps),
                    height / 2.0 * math.sin(2.0 * math.pi * k / steps),
                )
                for k in range(steps)
            ]
        else:
            local = [
                (-width / 2.0, -height / 2.0),
                (width / 2.0, -height / 2.0),
                (width / 2.0, height / 2.0),
                (-width / 2.0, height / 2.0),
            ]
        outline = [
            (
                plot._x_axis.to_pixels(cx + u * cos - v * sin),
                plot._y_axis.to_pixels(cy + u * sin + v * cos),
            )
            for u, v in local
        ]
        centre = (plot._x_axis.to_pixels(cx), plot._y_axis.to_pixels(cy))
        alpha = 40
        for index, point in enumerate(outline):
            following = outline[(index + 1) % len(outline)]
            painter.fill_triangle(centre, point, following, (*colour, alpha))
            _stroke_segment(painter, point, following, 1.5, (*colour, 255))
        xs, ys = [p[0] for p in outline], [p[1] for p in outline]
        entry.state["_box"] = (min(xs), min(ys), max(xs), max(ys))

    def _draw_bars(self, painter, plot, entry: _Entry) -> None:
        """A bar per sample, from the axis floor up to its height."""
        xs, heights = entry.state["x"], entry.state["height"]
        if not len(xs):
            return
        width = self._bar_width(entry.state)
        floor = plot.y + plot.h if self._log["y"] else plot._y_axis.to_pixels(0.0)
        for centre, height in zip(xs, heights):
            lo, hi = centre - width / 2.0, centre + width / 2.0
            if self._log["x"]:
                if hi <= 0.0:
                    continue
                left = plot.x if lo <= 0.0 else plot._x_axis.to_pixels(math.log10(lo))
                right = plot._x_axis.to_pixels(math.log10(hi))
            else:
                left, right = plot._x_axis.to_pixels(lo), plot._x_axis.to_pixels(hi)
            if self._log["y"] and height <= 0.0:
                continue
            top = plot._y_axis.to_pixels(math.log10(height) if self._log["y"] else height)
            painter.fill_rect(
                min(left, right),
                min(top, floor),
                abs(right - left),
                abs(floor - top),
                entry.state.get("brush", (120, 150, 200)),
            )

    def _draw_curve_fill(self, painter, plot, entry: _Entry) -> None:
        """The area between a filled curve and zero (the axis floor on a log axis).

        pyqtgraph's ``fillLevel=0``: a distribution drawn as a filled histogram.
        One column per sample, under the series, so the line stays on top.
        """
        state = entry.state
        xs, ys = self._scaled(state["x"], state["y"], gaps=state.get("gaps", False))
        if xs.size < 2:
            return
        colour = _faded(state["fill"], float(state.get("opacity", 1.0)))
        bottom = plot.y + plot.h
        floor = bottom if self._log["y"] else min(max(plot._y_axis.to_pixels(0.0), plot.y), bottom)
        for index in range(xs.size - 1):
            x0, x1, y0 = xs[index], xs[index + 1], ys[index]
            if not (np.isfinite(x0) and np.isfinite(x1) and np.isfinite(y0)):
                continue
            left, right = plot._x_axis.to_pixels(x0), plot._x_axis.to_pixels(x1)
            at = plot._y_axis.to_pixels(y0)
            painter.fill_rect(
                min(left, right),
                min(at, floor),
                max(abs(right - left), 1.0),
                abs(floor - at),
                colour,
            )

    def _draw_band(self, painter, plot, entry: _Entry) -> None:
        """The area between two curves, as one column per sample."""
        xs, lower = entry.state["x"], entry.state["lower"]
        upper = entry.state["upper"]
        if not len(xs):
            return
        colour = entry.state.get("brush", (120, 150, 200, 70))
        for index in range(len(xs) - 1):
            left = plot._x_axis.to_pixels(xs[index])
            right = plot._x_axis.to_pixels(xs[index + 1])
            top = plot._y_axis.to_pixels(max(lower[index], upper[index]))
            bottom = plot._y_axis.to_pixels(min(lower[index], upper[index]))
            painter.fill_rect(
                min(left, right),
                min(top, bottom),
                max(abs(right - left), 1.0),
                abs(bottom - top),
                colour,
            )

    def _draw_errorbars(self, painter, plot, entry: _Entry) -> None:
        """A whisker per sample, with a beam at each end."""
        xs, ys = entry.state["x"], entry.state["y"]
        top_values = entry.state["top"]
        bottom_values = entry.state["bottom"]
        colour = entry.state.get("color", (200, 200, 200))
        beam = float(entry.state.get("beam", 3.0))
        for index in range(min(len(xs), len(top_values), len(bottom_values))):
            at = plot._x_axis.to_pixels(xs[index])
            high = plot._y_axis.to_pixels(ys[index] + top_values[index])
            low = plot._y_axis.to_pixels(ys[index] - bottom_values[index])
            painter.fill_rect(at, min(high, low), 1.0, abs(low - high), colour)
            for edge in (high, low):
                painter.fill_rect(at - beam, edge, 2.0 * beam, 1.0, colour)

    # -- dragging, which emtk's host feeds us ---------------------------
    def _from_pixels(self, px: float) -> float:
        """Turn a pixel x back into a data x, using the last frame's axis."""
        axis = getattr(self, "_axis", None)
        if axis is None:
            return float(px)
        low, high = axis.range
        span_px = (axis.pixel_max - axis.pixel_min) or 1.0
        return low + (high - low) * (px - axis.pixel_min) / span_px

    def _from_pixels_y(self, py: float) -> float:
        """Turn a pixel y back into a data y, using the last frame's axis."""
        axis = getattr(self, "_y_axis_cache", None)
        if axis is None:
            return float(py)
        low, high = axis.range
        span_px = (axis.pixel_max - axis.pixel_min) or 1.0
        return low + (high - low) * (py - axis.pixel_min) / span_px

    def press(self, px: float, py: float, *_args: Any) -> None:
        """Start a drag on whatever the press landed on, or a pan on nothing."""
        self._dragging = None
        self._panning = None
        if self._on_auto_button(px, py):
            # The "A": every axis follows its data again; the press starts nothing.
            self._auto_button_hovered = False
            self.auto_range()
            return
        for entry in reversed(self._entries):
            if not entry.visible or not entry.state.get("movable", True):
                continue
            if entry.kind == "text":
                box = entry.state.get("_box")
                if box and box[0] <= px <= box[2] and box[1] <= py <= box[3]:
                    self._dragging = _Grab(entry, "text", point=(px, py))
                    break
                continue
            if entry.kind == "roi":
                grip = self._grip_at(entry, px, py)
                if grip is not None:
                    x0, y0 = entry.pos
                    w0, h0 = entry.size
                    fixed = (x0 + w0, y0 + h0) if grip == "lo" else (x0, y0)
                    self._dragging = _Grab(entry, "grip", point=fixed)
                    break
                box = entry.state.get("_box")
                if box and box[0] <= px <= box[2] and box[1] <= py <= box[3]:
                    self._dragging = _Grab(
                        entry, "roi", point=(self._from_pixels(px), self._from_pixels_y(py))
                    )
                    break
                continue
            span = entry.state.get("_pixels")
            if span is None or entry.kind not in ("region", "marker"):
                continue
            horizontal = entry.kind == "region" and entry.state.get("orientation") == "horizontal"
            along, convert = (py, self._from_pixels_y) if horizontal else (px, self._from_pixels)
            if entry.kind == "region":
                # An edge moves on its own, as pyqtgraph's region does; the
                # inside moves the whole range. ``_pixels`` holds the edges in
                # pixel order, which on a y axis runs top to bottom, i.e. from
                # the high value to the low one.
                low_at, high_at = (span[1], span[0]) if horizontal else (span[0], span[1])
                if horizontal and self._y_inverted:
                    low_at, high_at = high_at, low_at
                for edge, at in (("low", low_at), ("high", high_at)):
                    if abs(along - at) <= 5.0:
                        self._dragging = _Grab(entry, "edge", edge=edge, value=convert(along))
                        break
                if self._dragging is not None:
                    break
            if span[0] - 3.0 <= along <= span[1] + 3.0:
                self._dragging = _Grab(entry, "move", value=convert(along))
                break
        if self._dragging is None and (self._interactive or self._paint is not None):
            x, y = self._from_pixels(px), self._from_pixels_y(py)
            if self._paint is not None:
                # Nothing under the pointer and a brush is armed: the gesture
                # paints instead of panning.
                self._painting = True
                self._paint_last = (x, y)
                self._paint("start", x, y)
            else:
                # The gesture pans the view, which is what dragging a plot
                # does everywhere else.
                self._panning = (x, y)
            for callback in self._click_callbacks:
                callback(x, y, 1)

    def drag(self, px: float, py: float, *_args: Any) -> None:
        """Move whatever the press picked up, or pan the view."""
        if self._painting and self._paint is not None:
            self._paint_last = (self._from_pixels(px), self._from_pixels_y(py))
            self._paint("move", *self._paint_last)
            return
        if self._panning is not None:
            grabbed_x, grabbed_y = self._panning
            (x0, x1), (y0, y1) = self._view()
            dx = grabbed_x - self._from_pixels(px)
            dy = grabbed_y - self._from_pixels_y(py)
            self._set_view(x=(x0 + dx, x1 + dx), y=(y0 + dy, y1 + dy))
            return
        grab = self._dragging
        if grab is None:
            return
        entry = grab.entry
        if grab.mode == "text":
            grabbed_x, grabbed_y = grab.point
            x, y = entry.state["pos"]
            if entry.state.get("anchored"):
                entry.set_position(x + px - grabbed_x, y + py - grabbed_y)
            else:
                entry.set_position(
                    x + self._from_pixels(px) - self._from_pixels(grabbed_x),
                    y + self._from_pixels_y(py) - self._from_pixels_y(grabbed_y),
                )
            grab.point = (px, py)
            return
        if grab.mode == "edge":
            low, high = entry.bounds
            horizontal = entry.state.get("orientation") == "horizontal"
            at = self._from_pixels_y(py) if horizontal else self._from_pixels(px)
            if grab.edge == "low":
                entry.set_bounds(min(at, high), high)
            else:
                entry.set_bounds(low, max(at, low))
            grab.value = at
            entry._notify(final=False)
            return
        if grab.mode == "grip":
            # A corner follows the pointer; the opposite one stays where it was
            # when the grip was taken, even if the pointer crosses it.
            fixed_x, fixed_y = grab.point
            now_x, now_y = self._from_pixels(px), self._from_pixels_y(py)
            entry.set_pos((min(fixed_x, now_x), min(fixed_y, now_y)))
            entry.set_size((max(abs(now_x - fixed_x), 1e-9), max(abs(now_y - fixed_y), 1e-9)))
            entry._notify(final=False)
            return
        if grab.mode == "roi":
            grabbed_x, grabbed_y = grab.point
            now_x, now_y = self._from_pixels(px), self._from_pixels_y(py)
            x, y = entry.pos
            entry.set_pos((x + now_x - grabbed_x, y + now_y - grabbed_y))
            grab.point = (now_x, now_y)
            entry._notify(final=False)
            return
        horizontal = entry.kind == "region" and entry.state.get("orientation") == "horizontal"
        now = self._from_pixels_y(py) if horizontal else self._from_pixels(px)
        moved = now - grab.value
        if entry.kind == "region":
            low, high = entry.bounds
            entry.set_bounds(low + moved, high + moved)
        else:
            entry.set_value(entry.value + moved)
        grab.value = now
        entry._notify(final=False)

    def release(self, *_args: Any) -> None:
        """Finish the drag and tell the listeners where it ended."""
        if self._painting:
            self._painting = False
            if self._paint is not None:
                self._paint("end", *getattr(self, "_paint_last", (0.0, 0.0)))
            self._dragging = None
            self._panning = None
            return
        if self._dragging is not None:
            if self._dragging.mode != "text":
                self._dragging.entry._notify(final=True)
        self._dragging = None
        self._panning = None

    def hover(self, px: float, py: float, *_args: Any) -> None:
        """Report the pointer in data coordinates."""
        on_button = self._on_auto_button(px, py)
        if on_button != self._auto_button_hovered:
            self._auto_button_hovered = on_button
            self.refresh()
        for callback in self._move_callbacks:
            callback(self._from_pixels(px), self._from_pixels_y(py))

    def scroll(self, rows: float, *_args: Any) -> None:
        """Zoom about the middle of the view, a notch at a time."""
        if not self._interactive:
            return
        factor = 1.1 ** float(rows)
        (x0, x1), (y0, y1) = self._view()
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        half_x, half_y = (x1 - x0) / 2.0 * factor, (y1 - y0) / 2.0 * factor
        self._set_view(x=(cx - half_x, cx + half_x), y=(cy - half_y, cy + half_y))

    def _draw_image(self, plot, entry: _Entry) -> None:
        """Place an image in the plot's data space.

        The texture is built once and kept until the data, levels or colormap
        change: a frame is drawn on every repaint, and re-mapping a megapixel
        array through a colormap each time would make panning the plot a
        slideshow.
        """
        state = entry.state
        if np.asarray(state["data"]).size == 0:
            return
        # A texture's first row is painted at the top of its rectangle, and an
        # image's row 0 belongs at y0 -- the bottom of an upright panel, the top
        # of an inverted one. Upright, the rows are handed over reversed.
        upright = not self._y_inverted
        if state.get("texture") is None or state.get("_upright") != upright:
            data = np.asarray(state["data"])
            if state.get("col_major"):
                data = data.T if data.ndim == 2 else np.transpose(data, (1, 0, 2))
            state["texture"], rows, columns = _texture(
                data[::-1] if upright else data, state.get("colormap"), state.get("levels")
            )
            state["_upright"] = upright
            state.setdefault("rect", (0.0, 0.0, float(columns), float(rows)))
        # The axes have to know the image is there, or a panel holding nothing
        # else auto-fits to an empty range and the image lands outside it.
        x0, y0, width, height = state["rect"]
        plot._x_axis.fit((x0, x0 + width))
        plot._y_axis.fit((y0, y0 + height))
        entry.state["_placed"] = (x0, y0, width, height)
        plot._images = getattr(plot, "_images", [])
        plot._images.append((state["texture"], x0, y0, width, height))

    def _scaled(self, xs, ys, gaps: bool = False) -> tuple[np.ndarray, np.ndarray]:
        """Apply the log scaling the panel is set to, dropping what it kills.

        With ``gaps`` a killed sample becomes a NaN instead, so a curve breaks
        there rather than joining across it.
        """
        if not (self._log["x"] or self._log["y"]):
            return xs, ys
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        keep = np.ones(xs.shape, dtype=bool)
        if self._log["x"]:
            keep &= ~(xs <= 0)
        if self._log["y"]:
            keep &= ~(ys <= 0)
        if gaps:
            xs, ys = np.where(keep, xs, np.nan), np.where(keep, ys, np.nan)
        else:
            xs, ys = xs[keep], ys[keep]
        if self._log["x"]:
            xs = np.log10(xs)
        if self._log["y"]:
            ys = np.log10(ys)
        return xs, ys

    # -- drawing -------------------------------------------------------
    def _add(self, kind: str, **state: Any) -> _Entry:
        entry = _Entry(self, kind, **state)
        self._entries.append(entry)
        self.refresh()
        return entry

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
        """Draw a line curve (optionally with markers, or filled down to zero) and return its handle."""
        gaps = bool(skip_missing)
        xs, ys = _finite_pairs(x, y, gaps=gaps)
        return self._add(
            "curve",
            x=xs,
            y=ys,
            gaps=gaps,
            name=name,
            color=_rgb(pen),
            width=float(getattr(pen, "width", 1.0) or 1.0),
            # A fully transparent pen means markers only. emtk colours are
            # RGB, so the alpha has to be read here or the points are joined
            # by an opaque black line (and the legend swatch turns black).
            line=symbol is None or _rgba(pen, (0, 0, 0, 255))[3] > 0,
            symbol=symbol,
            symbol_size=symbol_size,
            symbol_color=_rgb(symbol_brush, _rgb(pen)) if symbol is not None else None,
            step=step,
            fill=None if fill is None else _rgba(fill, (*_rgb(pen), 90)),
        )

    def add_scatter(
        self, x, y, *, size=7.0, pen=None, brush=None, symbol=None, name=None
    ) -> H.Scatter:
        """Draw a scatter cloud and return its handle."""
        xs, ys = _finite_pairs(x, y)
        return self._add(
            "scatter",
            x=xs,
            y=ys,
            name=name,
            color=_rgb(brush, _rgb(pen)),
            symbol_size=size,
            symbol=symbol,
        )

    def add_marks(
        self, x, y, *, symbol="o", size=7.0, pen=None, brush=None, width=1.0
    ) -> H.Scatter:
        """Draw a set of symbols over the plot area and return its handle.

        Unlike :meth:`add_scatter` these are drawn after the images, shapes and
        bands, so they are never hidden by a picture, and each symbol has its own
        fill and outline (``brush`` / ``pen`` of ``None`` = hollow / flat).
        """
        xs, ys = _finite_pairs(x, y)
        symbol = getattr(symbol, "value", symbol)
        return self._add(
            "marks",
            x=xs,
            y=ys,
            symbol=str(symbol),
            size=float(size),
            pen=None if pen is None else _rgba(pen, (255, 255, 255, 255)),
            brush=None if brush is None else _rgba(brush, (255, 255, 255, 255)),
            width=float(width),
        )

    def add_marker(
        self, pos, *, orientation="vertical", movable=False, pen=None, label=None
    ) -> H.Marker:
        """Draw a cursor line and return its handle."""
        return self._add(
            "marker",
            value=float(pos),
            orientation=_orientation(orientation),
            color=_rgb(pen),
            name=label,
            movable=bool(movable),
        )

    def add_legend(self, *, offset=(30, 30)) -> None:
        """Show a legend collecting the named series."""
        self._legend = True
        self.refresh()

    def remove_legend(self) -> None:
        """Stop showing the legend."""
        self._legend = False
        self.refresh()

    def readd(self, handle) -> None:
        """Re-attach a previously removed handle."""
        if handle not in self._entries:
            self._entries.append(handle)
            handle._alive = True
            self.refresh()

    def remove(self, handle) -> None:
        """Remove a handle from this panel."""
        if handle in self._entries:
            self._entries.remove(handle)
            handle._alive = False
            self.refresh()

    def clear(self) -> None:
        """Remove every handle from this panel."""
        for entry in self._entries:
            entry._alive = False
        self._entries.clear()
        self.refresh()

    # -- axes and view -------------------------------------------------
    def set_labels(
        self,
        *,
        left=None,
        bottom=None,
        right=None,
        top=None,
        left_units=None,
        bottom_units=None,
        right_units=None,
        top_units=None,
    ) -> None:
        """Store axis text/unit metadata; only left and bottom are rendered today."""
        for side, text, units in (
            ("left", left, left_units),
            ("bottom", bottom, bottom_units),
            ("right", right, right_units),
            ("top", top, top_units),
        ):
            if text is not None:
                self._labels[side] = str(text)
            if units is not None:
                self._units[side] = str(units)
        self.refresh()

    def set_title(self, title: str | None) -> None:
        """Set the panel title."""
        self._title = str(title or "")
        self.refresh()

    def set_log(self, *, x=None, y=None) -> None:
        """Toggle logarithmic scaling per axis."""
        if x is not None:
            self._log["x"] = bool(x)
        if y is not None:
            self._log["y"] = bool(y)
        self.refresh()

    def set_range(self, *, x=None, y=None, padding=None) -> None:
        """Set the visible range, in data units -- on a log axis too.

        ``(1, 10000)``, not ``(0, 4)``: the axis converts. An x range reaches
        every panel linked to this one.
        """
        if x is not None:
            for member in self._x_group:
                member._range["x"] = (float(x[0]), float(x[1]))
                if member is not self:
                    member.refresh()
        if y is not None:
            self._range["y"] = (float(y[0]), float(y[1]))
        self.refresh()
        self._announce_range()

    def get_range(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Return the visible ``((x0, x1), (y0, y1))`` range.

        What the last frame showed when it was fitted automatically -- padding
        included, in the axis' own coordinates -- so a pan starts from what is
        on screen rather than from the raw data.
        """
        return (
            self._range["x"] or self._from_axis("x", self._drawn["x"]) or self._data_range(0),
            self._range["y"] or self._from_axis("y", self._drawn["y"]) or self._data_range(1),
        )

    def _to_axis(self, axis: str, span):
        """A data-unit range in the units the axis holds: exponents on a log axis.

        ``None`` for no range, and for a log range with nothing positive in it,
        which no log axis can show -- the axis then fits its data instead.
        """
        if span is None or not self._log[axis]:
            return span
        low, high = float(span[0]), float(span[1])
        if high <= 0.0:
            return None
        if low <= 0.0:
            low = high * 1e-6
        return (math.log10(low), math.log10(high))

    def _from_axis(self, axis: str, span):
        """Inverse of :meth:`_to_axis`."""
        if span is None or not self._log[axis]:
            return span
        return (10.0 ** span[0], 10.0 ** span[1])

    def _view(self):
        """The visible range in axis units, what a pan or zoom moves."""
        return tuple(
            self._to_axis(axis, self._range[axis])
            or self._drawn[axis]
            or self._to_axis(axis, self._data_range(index))
            or (0.0, 1.0)
            for index, axis in enumerate(("x", "y"))
        )

    def _set_view(self, *, x, y) -> None:
        """Set the visible range from axis units."""
        self.set_range(x=self._from_axis("x", x), y=self._from_axis("y", y))

    def set_axis_style(self, *, line=None, text=None) -> None:
        """Colour the axis text (tick numbers and titles); ``line`` is kept for the frame."""
        if line is not None:
            self._axis_line = _rgb(line)
        if text is not None:
            self._tick_text = self._label_text = _rgb(text)
        self.refresh()

    def set_tick_labels(self, side: str, ticks) -> None:
        """Label the left or bottom axis with ``[(position, text), ...]``; ``None`` clears."""
        if ticks is None:
            self._custom_ticks.pop(side, None)
        else:
            self._custom_ticks[side] = [(float(p), str(t)) for p, t in ticks]
        self.refresh()

    def set_legend_style(self, *, text=None) -> None:
        """Remember the legend text colour (the emtk legend draws in the theme colour)."""
        if text is not None:
            self._legend_text = _rgb(text)

    def set_axis_visible(self, side: str, visible: bool) -> None:
        """Show or hide the left or bottom axis (tick numbers and title)."""
        if side in self._axis_visible:
            self._axis_visible[side] = bool(visible)
            self.refresh()

    def link_x(self, other) -> None:
        """Share the x axis with *other*: auto-fit to the union, pan and zoom together."""
        if not isinstance(other, EmtkCanvas) or other._x_group is self._x_group:
            return
        merged = self._x_group + [m for m in other._x_group if m not in self._x_group]
        for member in merged:
            member._x_group = merged
            member.refresh()

    @staticmethod
    def _bar_width(state) -> float:
        """Return the declared bin width or the existing spacing-derived default."""
        if state.get("width") is not None:
            return float(state["width"])
        xs = state["x"]
        return float(np.min(np.diff(xs))) * 0.8 if len(xs) > 1 else 1.0

    @staticmethod
    def _bar_values(state, axis: int) -> np.ndarray:
        """Return rectangle edge coordinates for fitting, including the zero baseline."""
        if axis == 0:
            half = EmtkCanvas._bar_width(state) / 2.0
            return np.concatenate((state["x"] - half, state["x"] + half))
        return np.concatenate((np.zeros_like(state["height"]), state["height"]))

    def _data_range(self, axis: int) -> tuple[float, float]:
        """The extent of the drawn data along *axis*, or ``(0, 1)`` when empty.

        An image counts as data: its rect is where it sits, so a panel holding
        only a heatmap fits the heatmap rather than the unit square. On a log axis
        it is the range drawing would use (positive samples, capped at
        :data:`LOG_AUTOSCALE_DECADES`), so a panel not drawn yet reports the same.
        """
        name = "x" if axis == 0 else "y"
        if self._log[name]:
            fitted = self._group_x_extent() if axis == 0 else self._fitted(1, 0.04)
            in_data = self._from_axis(name, fitted) if fitted is not None else None
            if in_data is not None:
                return in_data
        spans: list[tuple[float, float]] = []
        for entry in self._entries:
            if not entry.visible:
                continue
            if entry.kind in ("curve", "scatter"):
                samples = entry.state["x" if axis == 0 else "y"]
                if samples is not None and len(samples):
                    spans.append((float(np.min(samples)), float(np.max(samples))))
            elif entry.kind == "bars":
                values = self._bar_values(entry.state, axis)
                if values.size:
                    spans.append((float(values.min()), float(values.max())))
            elif entry.kind == "image":
                x0, y0, width, height = entry.state["rect"]
                start, extent = (x0, width) if axis == 0 else (y0, height)
                spans.append((float(start), float(start + extent)))
        if not spans:
            return (0.0, 1.0)
        low = min(start for start, _ in spans)
        high = max(end for _, end in spans)
        return (low, high) if high > low else (low, low + 1.0)

    def is_auto_range(self) -> tuple[bool, bool]:
        """Whether x and y follow the data: a set or zoomed axis stores its range."""
        return (self._range.get("x") is None, self._range.get("y") is None)

    def auto_range(self) -> None:
        """Fit the view to its contents."""
        for member in self._x_group:
            member._range["x"] = None
            member.refresh()
        self._range["y"] = None
        self.refresh()
        self._announce_range()

    def enable_auto_range(self, *, x=None, y=None) -> None:
        """Keep the view fitted to contents as data changes."""
        if x:
            for member in self._x_group:
                member._range["x"] = None
                member.refresh()
        if y:
            self._range["y"] = None
        self.refresh()

    def _announce_range(self) -> None:
        """Tell the range listeners where the view is now."""
        x_range, y_range = self.get_range()
        for callback in list(self._range_callbacks):
            callback(x_range, y_range)

    def on_range_changed(self, callback) -> None:
        """Register ``callback(x_range, y_range)`` for view changes."""
        self._range_callbacks.append(callback)

    def set_grid(self, *, x=None, y=None, alpha=None) -> None:
        """Toggle the axis grid; *alpha* sets its strength (chiplot's default 0.3 is the theme's)."""
        if x is not None or y is not None:
            self._grid = bool(x or y)
        if alpha is not None:
            from chisurf.core.plotting.appearance import grid_strength

            self._grid_strength = grid_strength(alpha)
        self.refresh()

    def set_background(self, color) -> None:
        """Set the panel background colour."""
        self._background = _rgb(color, self._background)
        setter = getattr(self._host, "set_background", None)
        if callable(setter):
            setter(self._background)
        self.refresh()

    def set_tick_spacing(self, side, *, major=None, minor=None) -> None:
        """Not offered: emtk chooses its own tick interval."""

    def set_aspect_locked(self, lock: bool, ratio: float = 1.0) -> None:
        """Keep equal pixels per unit on both axes (``ratio`` is y-over-x), or free them."""
        self._aspect = float(ratio) if lock else None
        self.refresh()

    def set_si_prefix(self, *, x=None, y=None) -> None:
        """Toggle SI scaling of tick text and unit prefixes, keeping data unchanged."""
        for axis, enabled in (("x", x), ("y", y)):
            if enabled is not None:
                self._si_prefix[axis] = bool(enabled)
        self.refresh()

    def invert_y(self, invert: bool = True) -> None:
        """Run the y-axis downwards, as image rows do."""
        self._y_inverted = bool(invert)
        self.refresh()

    # -- input ---------------------------------------------------------
    def on_click(self, callback) -> None:
        """Register ``callback(x, y, button)`` for clicks in data coordinates."""
        self._click_callbacks.append(callback)

    def on_mouse_move(self, callback) -> None:
        """Register ``callback(x, y)`` for pointer motion in data coordinates."""
        self._move_callbacks.append(callback)

    def set_paint_handler(self, handler: Callable | None) -> None:
        """Give the left drag to ``handler(phase, x, y)`` instead of panning.

        ``phase`` is ``"start"``, ``"move"`` or ``"end"`` and ``x``, ``y`` are in
        data coordinates (``"end"`` repeats the last position). A drag that
        starts on a shape, region or label still moves that, so painting never
        steals a handle. ``None`` restores panning.
        """
        self._paint = handler
        self._painting = False

    def set_interactive(self, *, mouse=None, menu=None) -> None:
        """Enable or disable mouse pan and zoom."""
        if mouse is not None:
            self._interactive = bool(mouse)

    def export_size(self) -> tuple[int, int]:
        """The size an export is drawn at: the host's, else the last drawn box, else 800 x 500."""
        size = getattr(self._host, "size", None)
        if callable(size):
            w, h = size()
            if w > 0 and h > 0:
                return int(w), int(h)
        box = getattr(self, "_last_box", None)
        if box is not None and box[2] > 0 and box[3] > 0:
            return int(box[2]), int(box[3])
        return 800, 500

    def export_image(self, path, *, width=None) -> bool:
        """Render the panel to an image file; ``True`` when it was written.

        Drawn on emtk's CPU rasteriser (:class:`emtk.pil_painter.PilPainter`, the
        one :mod:`chisurf.emtk.fit_report` draws the report with) at the size the
        panel is shown at (:meth:`export_size`), so it needs no window, no GPU
        and no toolkit. *width* scales the picture, text included
        (:class:`emtk.scaled_painter.ScaledPainter`). The format follows the
        suffix (anything Pillow writes; ``.svg`` is not one).
        """
        from emtk.pil_painter import PilPainter
        from emtk.scaled_painter import ScaledPainter

        w, h = self.export_size()
        scale = float(width) / max(w, 1) if width else 1.0
        painter = PilPainter(
            max(int(w * scale), 1), max(int(h * scale), 1), background=(*self._background, 255)
        )
        target = painter if scale == 1.0 else ScaledPainter(painter, scale)
        self.draw(target, 0.0, 0.0, float(w), float(h))
        frame = painter.frame
        if str(path).lower().endswith((".jpg", ".jpeg", ".bmp")):
            frame = frame.convert("RGB")
        frame.save(str(path))
        return True

    def native(self) -> Any:
        """The display list; emtk keeps no plot object between frames."""
        return self._entries

    # -- the families this backend does not draw yet -------------------
    def _unsupported(self, what: str):
        raise NotImplementedError(
            f"emtk: {what} is not drawn yet (open front: okf/subsystems/chiplot.md)"
        )

    def add_bars(self, x, height, *, width=None, pen=None, brush=None) -> H.Bars:
        """Draw a bar graph and return its handle."""
        xs, heights = _finite_pairs(x, height)
        entry = _BarsEntry(
            self,
            "bars",
            x=xs,
            height=heights,
            width=None if width is None else float(width),
            brush=_rgb(brush, (120, 150, 200)),
        )
        self._entries.append(entry)
        self.refresh()
        return entry

    def add_fill_between(self, lower, upper, *, brush=None) -> H.Handle:
        """Fill the area between two curve handles and return its handle."""
        low_x, low_y = lower.get_data()
        _, high_y = upper.get_data()
        size = min(len(low_x), len(low_y), len(high_y))
        fill = _rgb(brush, (120, 150, 200))
        return self._add(
            "band", x=low_x[:size], lower=low_y[:size], upper=high_y[:size], brush=(*fill, 70)
        )

    def add_errorbars(
        self, x, y, *, height=None, top=None, bottom=None, pen=None, beam=None
    ) -> H.ErrorBars:
        """Draw error bars and return their handle."""
        xs, ys = _finite_pairs(x, y)
        if top is None and bottom is None and height is None:
            raise ValueError("error bars need height, or top and bottom")
        tops, bottoms = _whiskers(xs, height, top, bottom)
        return self._add(
            "errorbars",
            x=xs,
            y=ys,
            top=tops,
            bottom=bottoms,
            color=_rgb(pen),
            beam=float(beam or 3.0),
        )

    def add_image(self, data, *, colormap=None, levels=None, rect=None, axis_order=None) -> _Entry:
        """Draw an image or heatmap and return its handle."""
        rgb = np.ndim(data) == 3 and np.shape(data)[-1] in (3, 4)
        values = np.asarray(data) if rgb else np.asarray(data, dtype=float)
        if values.ndim != 2 and not rgb:
            raise ValueError(f"an image is 2-D (or RGB/RGBA); got shape {values.shape}")
        if str(axis_order or "row-major") not in ("row-major", "col-major"):
            raise ValueError(f"unknown axis order {axis_order!r}")
        col_major = str(axis_order) == "col-major"
        rows, columns = values.shape[:2][::-1] if col_major else values.shape[:2]
        return self._add(
            "image",
            data=values,
            col_major=col_major,
            colormap=colormap,
            levels=None if levels is None else (float(levels[0]), float(levels[1])),
            rect=tuple(float(v) for v in rect)
            if rect is not None
            else (0.0, 0.0, float(columns), float(rows)),
            texture=None,
        )

    def add_region(
        self, bounds, *, orientation="vertical", movable=True, brush=None, pen=None
    ) -> H.Region:
        """Draw a draggable interval selector and return its handle."""
        low, high = (float(bounds[0]), float(bounds[1]))
        fill = _rgba(brush, (70, 110, 160, 50))
        return self._add(
            "region",
            bounds=(min(low, high), max(low, high)),
            movable=bool(movable),
            brush=fill,
            orientation=_orientation(orientation),
        )

    def add_roi(
        self,
        *,
        kind="rect",
        pos=None,
        size=None,
        pen=None,
        movable=True,
        rotatable=False,
        points=None,
        angle=0.0,
        resizable=False,
    ) -> H.Roi:
        """Draw a region of interest and return its handle.

        Rectangles, ellipses, polygons and polylines are drawn and can be
        dragged; a rectangle or ellipse is turned ``angle`` degrees about its
        centre. A shape is moved whole; ``resizable`` adds a grip on two opposite
        corners of an upright rectangle or ellipse that resizes it. Rotation
        grips are not drawn: the angle is set programmatically.
        """
        shape = str(getattr(kind, "value", kind)).lower()
        if shape not in ("rect", "rectangle", "ellipse", "circle", "polygon", "polyline"):
            raise NotImplementedError(f"emtk: a {shape!r} region of interest is not drawn yet")
        shape = {"rectangle": "rect", "circle": "ellipse"}.get(shape, shape)
        vertices = [(float(x), float(y)) for x, y in (points or [])]
        origin = (
            (float(pos[0]), float(pos[1]))
            if pos is not None
            else (vertices[0] if vertices else (0.0, 0.0))
        )
        return self._add(
            "roi",
            roi_kind=shape,
            pos=origin,
            angle=float(angle),
            size=(float(size[0]), float(size[1])) if size is not None else (1.0, 1.0),
            points=vertices,
            movable=bool(movable),
            resizable=bool(resizable) and shape in ("rect", "ellipse") and not angle,
            color=_rgb(pen, (240, 200, 90)),
        )

    def add_arrow(
        self,
        pos,
        *,
        angle=0.0,
        size=None,
        tip_angle=None,
        head_width=None,
        tail_length=None,
        tail_width=None,
        pen=None,
        brush=None,
    ) -> H.Arrow:
        """Draw an arrow head (and optional tail) at a data coordinate."""
        return self._add(
            "arrow",
            pos=(float(pos[0]), float(pos[1])),
            angle=float(angle),
            size=float(20.0 if size is None else size),
            tip_angle=float(25.0 if tip_angle is None else tip_angle),
            head_width=None if head_width is None else float(head_width),
            tail_length=None if tail_length is None else float(tail_length),
            tail_width=float(3.0 if tail_width is None else tail_width),
            color=_rgb(brush if brush is not None else pen, (220, 220, 220)),
        )

    def add_text(
        self,
        text,
        pos,
        *,
        color=None,
        anchor=None,
        draggable=False,
        fill=None,
        border=None,
        anchored=False,
    ) -> H.Text:
        """Draw a text label and return its handle.

        ``anchored`` pins it to the plot area (``pos`` is a pixel offset from
        its top-left), otherwise ``pos`` is a data coordinate; ``draggable``
        lets a press move it.
        """
        return self._add(
            "text",
            text=str(text),
            pos=(float(pos[0]), float(pos[1])),
            color=_rgba(color, (220, 220, 220, 255)),
            anchor=tuple(anchor) if anchor is not None else (0.0, 0.0),
            fill=None if fill is None else _rgba(fill, (20, 22, 28, 200)),
            border=None if border is None else _rgba(border, (90, 95, 105, 255)),
            anchored=bool(anchored),
            movable=bool(draggable),
        )


class EmtkImageView(base.ImageViewCanvas):
    """An image view: one canvas showing a picture, with a frame stepper.

    The canvas already draws images with axes, pan and zoom; the view adds
    what makes it an *image* viewer -- a stack it can step through (the
    slider belongs to whatever hosts the view), the picture
    placed on real axes, square pixels, image row order, and clicks reported
    in image coordinates.
    """

    def __init__(self, **opts: Any) -> None:
        self._canvas = EmtkCanvas(**opts)
        self._canvas.set_axis_visible("left", False)
        self._canvas.set_axis_visible("bottom", False)
        self._canvas.set_grid(x=False, y=False)
        self._canvas.invert_y(True)
        self._canvas.set_aspect_locked(True)
        self._stack: np.ndarray | None = None
        self._frame = 0
        self._image: _Entry | None = None
        self._colormap: Any = "viridis"
        self._overlays: list[_Entry] = []
        self._extent: tuple[float, float, float, float] | None = None
        self._frame_callbacks: list[Callable] = []
        self._bar: _ColorBar | None = None
        self._ramp_width: int | None = None
        self._refresh_target: Callable[[], None] | None = None

    def control(self) -> EmtkCanvas:
        """The canvas that draws the picture: what a host shows."""
        return self._canvas

    def _rect_for(self, rows: int, columns: int) -> tuple[float, float, float, float]:
        """Where a ``rows x columns`` picture sits: the extent, or its pixels."""
        if self._extent is not None:
            x0, x1, y0, y1 = self._extent
            return (x0, y0, x1 - x0, y1 - y0)
        return (0.0, 0.0, float(columns), float(rows))

    def set_image(self, data, *, auto_levels: bool = True, axes=None) -> None:
        """Show an image, or a ``(t, y, x)`` stack whose first frame is shown.

        A stack is mapped over its **whole** range so stepping through it does
        not rescale every frame; ``axes`` is accepted for the old
        ``pg.ImageView`` spelling and ignored, the order is always ``(t, row, column)``.
        """
        values = np.asarray(data, dtype=float)
        if values.ndim == 3:
            self._stack = values
            frame = values[0]
        elif values.ndim == 2:
            self._stack = None
            frame = values
        else:
            raise ValueError(f"an image view takes 2-D or 3-D data; got {values.shape}")
        self._frame = 0
        rect = self._rect_for(*frame.shape)
        if self._image is None:
            self._image = self._canvas.add_image(frame, colormap=self._colormap, rect=rect)
            first = True
        else:
            first = (
                self._image.state.get("rect") != rect
                or self._image.get_image().shape != frame.shape
            )
            self._image.set_image(frame)
            self._image.set_rect(*rect)
        if auto_levels:
            if self._stack is not None:
                finite = values[np.isfinite(values)]
                low, high = (
                    (float(finite.min()), float(finite.max())) if finite.size else (0.0, 1.0)
                )
                self._image.set_levels(low, high)
            else:
                self._image.auto_levels()
        if first:
            self._canvas.auto_range()
        if self._bar is None:
            self._bar = _ColorBar(self._image)
            self._bar.set_refresh_target(self._refresh_target)
            self.set_histogram_width(self._ramp_width)
        self._bar.refresh()
        for callback in self._frame_callbacks:
            callback(0)

    def set_refresh_target(self, callback: Callable[[], None] | None) -> None:
        """Send the picture's and the ramp's repaint requests to *callback* (a surface drawing them)."""
        self._refresh_target = callback
        self._canvas.set_refresh_target(callback)
        if self._bar is not None:
            self._bar.set_refresh_target(callback)

    def colorbar(self) -> _ColorBar | None:
        """The colour ramp with draggable levels (a control), once an image is shown (else ``None``)."""
        return self._bar

    @property
    def frame_count(self) -> int:
        """Number of frames: the stack's length, ``1`` for a single image."""
        return 1 if self._stack is None else int(self._stack.shape[0])

    @property
    def frame(self) -> int:
        """The frame being shown."""
        return self._frame

    def set_frame(self, index: int) -> None:
        """Show frame *index* of a stack (a no-op for a single image)."""
        if self._stack is None:
            return
        self._frame = int(index) % self._stack.shape[0]
        if self._image is not None:
            self._image.set_image(self._stack[self._frame])
        for callback in self._frame_callbacks:
            callback(self._frame)

    def on_frame_changed(self, callback) -> None:
        """Call ``callback(index)`` whenever the shown frame changes."""
        self._frame_callbacks.append(callback)

    def set_extent(self, extent) -> None:
        """Place the picture on real axes ``(x0, x1, y0, y1)``; ``None`` = pixel indices."""
        changed = extent is not None and tuple(extent) != self._extent
        if extent is None:
            self._extent = None
        else:
            x0, x1, y0, y1 = (float(v) for v in extent)
            self._extent = (x0, x1, y0, y1)
        self._replace_rects()
        if changed or extent is None:
            self._canvas.auto_range()

    def _replace_rects(self) -> None:
        """Re-place the picture and every overlay on the current extent."""
        for entry in [self._image, *self._overlays]:
            if entry is None:
                continue
            rows, columns = np.asarray(entry.get_image()).shape[:2]
            entry.set_rect(*self._rect_for(rows, columns))

    def set_labels(self, *, bottom=None, left=None) -> None:
        """Title the axes; either one makes the axes visible."""
        self._canvas.set_labels(bottom=bottom, left=left)

    def set_axes_visible(self, visible: bool) -> None:
        """Draw tick numbers and titles on both axes (off: a bare picture)."""
        for side in ("left", "bottom"):
            self._canvas.set_axis_visible(side, visible)

    def invert_y(self, invert: bool = True) -> None:
        """Row 0 at the top (``True``, the picture convention) or at the bottom."""
        self._canvas.invert_y(invert)

    def set_aspect_locked(self, lock: bool = True) -> None:
        """Square pixels, or fill the panel."""
        self._canvas.set_aspect_locked(lock)

    def auto_range(self) -> None:
        """Fit the view to the picture."""
        self._canvas.auto_range()

    def view_range(self):
        """The visible ``((x0, x1), (y0, y1))`` in axis units."""
        return self._canvas.get_range()

    def set_colormap(self, name, source: str = "matplotlib") -> None:
        """Apply a named colormap."""
        self._colormap = name
        if self._image is not None:
            self._image.set_colormap(name)
        if self._bar is not None:
            self._bar.refresh()

    def clear(self) -> None:
        """Clear the image and its overlays."""
        self._canvas.clear()
        self._image = None
        if self._bar is not None:
            self._bar.remove()
            self._bar = None
        self._overlays.clear()
        self._stack = None
        self._frame = 0

    def set_histogram_width(self, width) -> None:
        """Fix the colour ramp's width in pixels, or free it with ``None``."""
        self._ramp_width = width
        if self._bar is not None:
            self._bar.set_width(width)

    def set_interactive(self, *, mouse=None, menu=None) -> None:
        """Toggle pan and zoom."""
        self._canvas.set_interactive(mouse=mouse, menu=menu)

    def set_auto_range_button(self, shown: bool) -> None:
        """Show (default) or never show the "A" auto-range button on the image."""
        self._canvas.set_auto_range_button(shown)

    def add_overlay(self, data, *, colormap=None) -> H.Image:
        """Overlay a second image on the view and return its handle."""
        rgb = np.ndim(data) == 3
        values = np.asarray(data) if rgb else np.asarray(data, dtype=float)
        overlay = self._canvas.add_image(
            values,
            colormap=self._colormap if colormap is None else colormap,
            rect=self._rect_for(*values.shape[:2]),
        )
        overlay.z = 1.0 + len(self._overlays)
        self._overlays.append(overlay)
        return overlay

    def add_marks(self, x, y, **style) -> H.Scatter:
        """Draw symbols (``symbol``, ``size``, ``pen``, ``brush``, ``width``) over the picture."""
        marks = self._canvas.add_marks(x, y, **style)
        marks.z = 10.0
        return marks

    def add_text(self, text, pos, **style) -> H.Text:
        """Write *text* at data position *pos* (``color``, ``anchor``)."""
        label = self._canvas.add_text(text, pos, **style)
        label.z = 11.0
        return label

    def add_roi(
        self,
        *,
        kind="rect",
        pos=None,
        size=None,
        pen=None,
        movable=True,
        rotatable=False,
        points=None,
        angle=0.0,
        resizable=False,
    ) -> H.Roi:
        """Add a region of interest to the view and return its handle."""
        return self._canvas.add_roi(
            kind=kind,
            pos=pos,
            size=size,
            pen=pen,
            movable=movable,
            rotatable=rotatable,
            points=points,
            angle=angle,
            resizable=resizable,
        )

    def on_click(self, callback) -> None:
        """Register ``callback(x, y)`` for clicks in axis coordinates."""
        self._canvas.on_click(lambda x, y, *_: callback(x, y))

    def on_hover(self, callback) -> None:
        """Register ``callback(x, y)`` for pointer motion in axis coordinates."""
        self._canvas.on_mouse_move(callback)

    def set_paint_handler(self, handler) -> None:
        """Hand the left drag to ``handler(phase, x, y)``; ``None`` restores panning."""
        self._canvas.set_paint_handler(handler)

    @property
    def native(self) -> Any:
        """The canvas the view draws through."""
        return self._canvas


class _ColorBar:
    """A colour ramp bound to an image, drawn by emtk; the ColorBar handle.

    The ramp spans the image's levels, labelled at both ends. Dragging in the
    upper half moves the high level and in the lower half the low one, as the
    handles of pyqtgraph's level editor do; there is no histogram beside it.
    """

    #: Pixels kept free above and below the ramp for its two labels.
    LABEL_H = 14.0

    #: The width a host gives the ramp, ``(least, most)`` pixels, unless fixed.
    WIDTH_RANGE = (56, 80)

    def __init__(self, image: _Entry, colormap=None) -> None:
        self._image = image
        self._callbacks: list[Callable] = []
        self._drag: tuple[str, float, tuple[float, float]] | None = None
        self._box = (0.0, 0.0, 1.0, 1.0)
        self._alive = True
        self._visible = True
        self._z = 0.0
        #: What shows the ramp (duck-typed, see :meth:`attach_host`), if anything.
        self._host: Any = None
        self._refresh_target: Callable[[], None] | None = None
        #: ``(least, most)`` width in pixels a host or a grid gives the ramp.
        self.width_range: tuple[int, int] = self.WIDTH_RANGE
        #: The background a host fills behind the ramp.
        self.background = (30, 32, 38)
        if colormap is not None:
            image.set_colormap(colormap)

    # -- the host ------------------------------------------------------
    def attach_host(self, host: Any) -> None:
        """Let *host* show the ramp; ``None`` detaches it.

        Duck-typed: ``update()`` repaints; the optional ``set_visible(bool)``,
        ``set_width_range(least, most)`` and ``detach()`` follow :meth:`hide`,
        :meth:`set_width` and :meth:`remove`.
        """
        self._host = host
        if host is not None:
            self._call_host("set_width_range", *self.width_range)
            self._call_host("set_visible", self._visible)

    @property
    def host(self) -> Any:
        """The attached host, or ``None``."""
        return self._host

    def _call_host(self, name: str, *args: Any) -> None:
        method = getattr(self._host, name, None)
        if callable(method):
            method(*args)

    def set_refresh_target(self, callback: Callable[[], None] | None) -> None:
        """Send repaint requests to *callback* (a surface drawing the ramp) instead of the host."""
        self._refresh_target = callback

    def refresh(self) -> None:
        """Ask whatever shows the ramp to repaint."""
        if self._refresh_target is not None:
            self._refresh_target()
        else:
            self._call_host("update")

    def set_width(self, width: int | None) -> None:
        """Fix the ramp's width in pixels, or give it back its default range with ``None``."""
        self.width_range = self.WIDTH_RANGE if width is None else (int(width), int(width))
        self._call_host("set_width_range", *self.width_range)

    # -- the control emtk draws ----------------------------------------
    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        """The ramp, high at the top, with the levels written at its ends."""
        self._box = (x, y, w, h)
        if not self._visible:
            return
        top, height = y + self.LABEL_H, max(h - 2.0 * self.LABEL_H, 1.0)
        table = _lut(self._image.state.get("colormap"), size=64)
        step = height / len(table)
        for index, colour in enumerate(table[::-1]):
            painter.fill_rect(
                x + 4.0,
                top + index * step,
                max(w - 8.0, 1.0),
                step + 0.5,
                tuple(int(c) for c in colour),
            )
        low, high = self.get_levels()
        painter.text(x, y, w, self.LABEL_H, 0, f"{high:.3g}", (220, 220, 220))
        painter.text(x, y + h - self.LABEL_H, w, self.LABEL_H, 0, f"{low:.3g}", (220, 220, 220))

    def press(self, px: float, py: float, *_args: Any) -> None:
        """Pick the level the press is nearer: high above the middle, low below."""
        x, y, w, h = self._box
        self._drag = ("high" if py < y + h / 2.0 else "low", py, self.get_levels())

    def drag(self, px: float, py: float, *_args: Any) -> None:
        """Move the picked level; the ramp's height spans the current range."""
        if self._drag is None:
            return
        which, start, (low, high) = self._drag
        span = (high - low) or 1.0
        height = max(self._box[3] - 2.0 * self.LABEL_H, 1.0)
        delta = (start - py) / height * span
        if which == "high":
            self.set_levels(low, max(high + delta, low + span * 1e-6), notify=True)
        else:
            self.set_levels(min(low + delta, high - span * 1e-6), high, notify=True)

    def release(self, *_args: Any) -> None:
        """End a drag."""
        self._drag = None

    def hover(self, *_args: Any) -> None:
        """Nothing changes under the pointer."""

    def scroll(self, *_args: Any) -> None:
        """The ramp does not zoom."""

    # -- ColorBar ------------------------------------------------------
    def set_colormap(self, colormap) -> None:
        """Map the image, and the ramp, through ``colormap``."""
        self._image.set_colormap(colormap)
        self.refresh()

    def set_levels(self, low: float, high: float, *, notify: bool = False) -> None:
        """Set the image's mapped range; a drag also tells the listeners."""
        self._image.set_levels(low, high)
        self.refresh()
        if notify:
            for callback in self._callbacks:
                callback(float(low), float(high))

    def get_levels(self) -> tuple[float, float]:
        """The image's mapped ``(low, high)``."""
        return self._image.get_levels()

    def set_histogram_visible(self, visible: bool) -> None:
        """No histogram is drawn, so there is nothing to show or hide."""

    def on_levels_changed(self, callback) -> None:
        """Call ``callback(low, high)`` when the user drags a level."""
        self._callbacks.append(callback)

    # -- Handle --------------------------------------------------------
    @property
    def visible(self) -> bool:
        """Whether the ramp is drawn."""
        return self._visible

    @visible.setter
    def visible(self, value: bool) -> None:
        self._visible = bool(value)
        self._call_host("set_visible", self._visible)
        self.refresh()

    @property
    def z(self) -> float:
        """Stacking order; a colour bar has its own cell, so it is only kept."""
        return self._z

    @z.setter
    def z(self, value: float) -> None:
        self._z = float(value)

    def hide(self) -> None:
        """Stop drawing the ramp."""
        self.visible = False

    def show(self) -> None:
        """Draw the ramp again."""
        self.visible = True

    def remove(self) -> None:
        """Take the ramp out of its grid (or view): its host lets go of it."""
        self._alive = False
        self._call_host("detach")
        self._host = None

    def is_alive(self) -> bool:
        """Whether the ramp still belongs to a grid."""
        return self._alive

    @property
    def native(self) -> Any:
        """The ramp itself: the control its host draws."""
        return self


class _Cell:
    """One item of a grid (a panel or a colour ramp) and the cells it spans."""

    __slots__ = ("item", "row", "col", "rowspan", "colspan", "rect")

    def __init__(self, item: Any, row: int, col: int, rowspan: int, colspan: int) -> None:
        self.item = item
        self.row, self.col = int(row), int(col)
        self.rowspan, self.colspan = max(int(rowspan), 1), max(int(colspan), 1)
        #: Where the last frame drew it, ``(x, y, w, h)``.
        self.rect: tuple[float, float, float, float] | None = None


def _tracks(
    count: int,
    total: float,
    spacing: float,
    stretch: dict[int, float],
    fixed: dict[int, tuple[float, float]],
) -> list[tuple[float, float]]:
    """``(offset, size)`` of *count* tracks sharing *total* pixels.

    A track in *fixed* (a colour ramp's column) gets the most of its
    ``(least, most)`` range that leaves the others room; the rest share what is
    left by their stretch factor (equal shares when none is set), as a grid
    layout does.
    """
    if count <= 0:
        return []
    room = max(total - spacing * (count - 1), 0.0)
    sizes = [0.0] * count
    free = [i for i in range(count) if i not in fixed]
    for i, (least, most) in fixed.items():
        if i < count:
            sizes[i] = float(most) if free else max(room / count, float(least))
    left = max(room - sum(sizes), 0.0)
    if free:
        weights = [float(stretch.get(i, 0.0)) for i in free]
        if not any(w > 0 for w in weights):
            weights = [1.0] * len(free)
        whole = sum(weights)
        for i, w in zip(free, weights):
            sizes[i] = left * w / whole
    out, at = [], 0.0
    for size in sizes:
        out.append((at, size))
        at += size + spacing
    return out


class EmtkGrid(base.GridCanvas):
    """Several panels in a grid, each an :class:`EmtkCanvas` of its own; itself a control.

    The grid lays its cells out by row and column (spans, stretch factors, a
    colour ramp's column kept narrow) and draws each item in its cell, so an
    emtk surface draws a whole grid as one control. Input goes to the item
    under the pointer, which keeps it from the press to the release. A host
    with a layout manager of its own can place the items itself from :meth:`cells`.
    """

    #: Pixels between two cells.
    SPACING = 2.0

    def __init__(self, **opts: Any) -> None:
        self._opts = opts
        self._panels: list[EmtkCanvas] = []
        self._cells: list[_Cell] = []
        self._row = 0
        self._column = 0
        self._column_stretch: dict[int, float] = {}
        self._row_stretch: dict[int, float] = {}
        self._captured: _Cell | None = None
        self._hovered: _Cell | None = None
        self._refresh_target: Callable[[], None] | None = None

    def _place(self, item: Any, row, col, rowspan, colspan) -> _Cell:
        if row is None:
            row = self._row
        if col is None:
            col = self._column
        cell = _Cell(item, row, col, rowspan, colspan)
        self._cells.append(cell)
        self._column = cell.col + cell.colspan
        if self._refresh_target is not None:
            item.set_refresh_target(self._refresh_target)
        return cell

    def add_panel(self, *, row=None, col=None, rowspan=1, colspan=1, title=None) -> base.Canvas:
        """Add and return a panel at the given cell, or at the cursor."""
        panel = EmtkCanvas(title=title, **self._opts)
        self._place(panel, row, col, rowspan, colspan)
        self._panels.append(panel)
        return panel

    def add_colorbar(
        self, image, *, colormap=None, row=None, col=None, rowspan=1, colspan=1
    ) -> H.ColorBar:
        """Add a colour ramp bound to ``image`` at the given cell, or at the cursor."""
        bar = _ColorBar(image, colormap)
        self._place(bar, row, col, rowspan, colspan)
        return bar

    def cells(self) -> list[tuple[Any, int, int, int, int]]:
        """``(item, row, col, rowspan, colspan)`` of every panel and ramp, in the order added."""
        return [(c.item, c.row, c.col, c.rowspan, c.colspan) for c in self._cells]

    def next_row(self) -> None:
        """Move the insertion cursor to the start of the next row."""
        self._row += 1
        self._column = 0

    def clear(self) -> None:
        """Remove every panel and ramp and start again at the first cell."""
        for cell in self._cells:
            if isinstance(cell.item, _ColorBar):
                cell.item.remove()
            else:
                cell.item.attach_host(None)
        self._cells.clear()
        self._panels.clear()
        self._captured = self._hovered = None
        self._row = self._column = 0
        self.refresh()

    def set_column_stretch(self, column: int, factor: float) -> None:
        """Set the relative width of a column."""
        self._column_stretch[int(column)] = float(factor)
        self.refresh()

    def set_row_stretch(self, row: int, factor: float) -> None:
        """Set the relative height of a row."""
        self._row_stretch[int(row)] = float(factor)
        self.refresh()

    def native(self) -> Any:
        """The panels themselves."""
        return self._panels

    # -- repainting ------------------------------------------------------
    def set_refresh_target(self, callback: Callable[[], None] | None) -> None:
        """Send every item's repaint requests to *callback* (the surface drawing the grid)."""
        self._refresh_target = callback
        for cell in self._cells:
            cell.item.set_refresh_target(callback)

    def refresh(self) -> None:
        """Ask the surface drawing the grid to repaint."""
        if self._refresh_target is not None:
            self._refresh_target()

    # -- the control -----------------------------------------------------
    def layout(self, x: float, y: float, w: float, h: float) -> None:
        """Give every cell its rectangle inside ``(x, y, w, h)``."""
        if not self._cells:
            return
        columns = max(c.col + c.colspan for c in self._cells)
        rows = max(c.row + c.rowspan for c in self._cells)
        fixed: dict[int, tuple[float, float]] = {}
        for column in range(columns):
            here = [c for c in self._cells if c.col <= column < c.col + c.colspan]
            if here and all(isinstance(c.item, _ColorBar) and c.colspan == 1 for c in here):
                fixed[column] = (
                    max(c.item.width_range[0] for c in here),
                    min(c.item.width_range[1] for c in here),
                )
        xs = _tracks(columns, w, self.SPACING, self._column_stretch, fixed)
        ys = _tracks(rows, h, self.SPACING, self._row_stretch, {})
        for c in self._cells:
            x0 = xs[c.col][0]
            last_x = xs[c.col + c.colspan - 1]
            y0 = ys[c.row][0]
            last_y = ys[c.row + c.rowspan - 1]
            c.rect = (x + x0, y + y0, last_x[0] + last_x[1] - x0, last_y[0] + last_y[1] - y0)

    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        """Draw every item in its cell, each on its own background."""
        self.layout(x, y, w, h)
        for c in self._cells:
            if c.rect is None:
                continue
            cx, cy, cw, ch = c.rect
            if cw < 1.0 or ch < 1.0:
                continue
            background = getattr(c.item, "_background", None) or getattr(c.item, "background", None)
            if background is not None:
                painter.fill_rect(cx, cy, cw, ch, tuple(background[:3]))
            painter.push_clip(cx, cy, cw, ch)
            try:
                c.item.draw(painter, cx, cy, cw, ch)
            finally:
                painter.pop_clip()

    def _cell_at(self, px: float, py: float) -> _Cell | None:
        for c in reversed(self._cells):
            if c.rect is not None:
                cx, cy, cw, ch = c.rect
                if cx <= px < cx + cw and cy <= py < cy + ch:
                    return c
        return None

    def press(self, px: float, py: float, *args: Any) -> None:
        """Hand the press to the item under it, which keeps the pointer until the release."""
        self._captured = self._cell_at(px, py)
        # A cell is only found where it was drawn, so it has a rect.
        if self._captured is not None and self._captured.rect is not None:
            self._captured.item.press(px, py, *self._captured.rect, *args[4:])

    def drag(self, px: float, py: float, *_args: Any) -> None:
        """Move what the press picked up."""
        if self._captured is not None and self._captured.rect is not None:
            self._captured.item.drag(px, py, *self._captured.rect)

    def release(self, *args: Any) -> None:
        """End the gesture on the item that took the press."""
        if self._captured is not None:
            self._captured.item.release(*args)
        self._captured = None

    def hover(self, px: float, py: float, *_args: Any) -> None:
        """Report the pointer to the item under it."""
        self._hovered = self._cell_at(px, py)
        if self._hovered is not None and self._hovered.rect is not None:
            self._hovered.item.hover(px, py, *self._hovered.rect)

    def scroll(self, rows: float, *args: Any) -> None:
        """Zoom the item the pointer is over."""
        if self._hovered is not None:
            self._hovered.item.scroll(rows, *args)


class EmtkBackend(base.Backend):
    """chiplot's backend over emtk."""

    name = "emtk"

    def create_canvas(self, **opts) -> base.Canvas:
        """Create a single-panel canvas."""
        return EmtkCanvas(**opts)

    def create_grid(self, **opts) -> base.GridCanvas:
        """Create a multi-panel grid."""
        return EmtkGrid(**opts)

    def create_image_view(self, **opts) -> base.ImageViewCanvas:
        """Create an image view."""
        return EmtkImageView(**opts)

    def configure(self, **global_opts: Any) -> None:
        """Nothing process-wide to set: emtk draws through its own painter."""
