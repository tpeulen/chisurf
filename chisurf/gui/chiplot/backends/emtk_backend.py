"""chiplot over emtk, the toolkit chimol draws its own interface with.

emtk is an immediate-mode toolkit: a control is handed a painter and draws
itself, frame by frame, and nothing persists between frames. chiplot is the
opposite -- ``plot.line(...)`` hands back a handle the caller keeps and mutates
later. This module is the bridge: the canvas owns a **display list** of series,
the handles edit entries in that list, and the control redraws the whole list
whenever Qt asks for a repaint.

That shape is also why this backend cannot crash the way the pyqtgraph one
does. There are no per-item QGraphicsItems to outlive their scene and no
Python slots connected to C++ destructors: a discarded plot is a Python list
that the garbage collector frees like any other.

What is drawn here today: curves (with symbols), scatter clouds, images and
heatmaps, draggable regions (the fit range is one), markers in both
orientations, the legend, axis labels and title, ranges (explicit, queried and
auto), log scaling, grid and background, bar graphs, filled bands, error bars
and text labels, rectangle/ellipse/polygon ROIs, an inverted y-axis, the colour
bar, arrows, the multi-panel grid and the image view. What is left -- filled
curves, horizontal regions -- raises :class:`NotImplementedError` naming what is
missing, because a plot that silently omits half of what it was asked to draw
is worse than one that says so. Those are the open front recorded in okf/subsystems/chiplot.md.

It is the default backend; ``CHISURF_PLOT_BACKEND=pyqtgraph`` or
``gui.plot.backend: pyqtgraph`` selects the other one.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np

from chisurf.gui import QtWidgets
from chisurf.gui.chiplot import handles as H
from chisurf.gui.chiplot import style as S
from chisurf.gui.chiplot.backends import base


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
        return tuple(int(component) for component in color[:3])
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
        return (*(int(component) for component in color[:3]), alpha)
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


def _lut(colormap, size: int = 256) -> np.ndarray:
    """Return ``colormap`` as an ``(size, 4)`` uint8 RGBA lookup table.

    matplotlib when it is installed, a grey ramp when it is not: a heatmap in
    the wrong colours still shows the data, and refusing to draw one because a
    plotting nicety is missing would not.
    """
    name = getattr(colormap, "name", colormap)
    table = np.linspace(0.0, 1.0, size)
    try:
        import matplotlib

        colours = matplotlib.colormaps[str(name)](table)
        return (np.asarray(colours) * 255.0).astype(np.uint8)
    except Exception:
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

    values = np.asarray(data, dtype=float)
    if values.ndim != 2:
        raise ValueError(f"an image is 2-D; got shape {values.shape}")
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
    def set_data(self, x, y=None, **_: Any) -> None:
        """Replace the series' samples."""
        if y is None and x is not None and len(np.shape(x)) == 2:
            data = np.asarray(x, dtype=float)
            x, y = data[:, 0], data[:, 1]
        self.state["x"], self.state["y"] = _finite_pairs(x, y, gaps=self.state.get("gaps", False))
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
        self.state["data"] = np.asarray(data, dtype=float)
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


class EmtkCanvas(base.Canvas):
    """A chiplot panel drawn by emtk from a display list."""

    def __init__(self, *, title: str | None = None, background=None, **_: Any) -> None:
        self._entries: list[_Entry] = []
        self._title = title or ""
        self._labels: dict[str, str] = {}
        self._log = {"x": False, "y": False}
        self._range: dict[str, tuple[float, float] | None] = {"x": None, "y": None}
        self._grid = True
        self._legend = False
        self._background = _rgb(background, (30, 32, 38))
        self._interactive = True
        self._y_inverted = False
        self._axis_visible = {"left": True, "bottom": True}
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
        self._widget = self._build_widget()

    # -- the Qt side ---------------------------------------------------
    def _build_widget(self) -> QtWidgets.QWidget:
        """Host this canvas in a widget that repaints it on demand."""
        from emtk.qt_host import ControlHost

        return ControlHost(self, background=self._background)

    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable Qt widget for this panel."""
        return self._widget

    def refresh(self) -> None:
        """Ask the host widget to repaint."""
        update = getattr(self._widget, "update", None)
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
        from emtk.widgets.plot import Plot as EmtkPlot

        row = float(painter.line_height())
        left_axis, bottom_axis = self._axis_visible["left"], self._axis_visible["bottom"]
        gutter_left = (row + 2.0 + _Y_TICK_WIDTH + 6.0) if left_axis else 4.0
        gutter_bottom = 4.0
        if bottom_axis:
            gutter_bottom += row + 2.0
            if self._labels.get("bottom"):
                gutter_bottom += row
        gutter_top = row + 2.0 if self._title else 6.0
        gutter_right = 10.0
        bx, by = x + gutter_left, y + gutter_top
        bw = max(w - gutter_left - gutter_right, 8.0)
        bh = max(h - gutter_top - gutter_bottom, 8.0)

        x_range = self._to_axis("x", self._range["x"]) or self._group_x_extent()
        y_range = self._to_axis("y", self._range["y"]) or self._fitted(1, 0.04)
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
        plot.show_y_tick_labels = False
        plot.x_tick_target = max(2, int(bw // 90))
        plot.y_tick_target = max(3, int(bh // 36))
        plot._x_axis.log_decades = self._log["x"]
        plot._y_axis.log_decades = self._log["y"]
        plot.underlays.append(self._draw_regions)
        for entry in sorted(self._entries, key=lambda e: e.z):
            if not entry.visible:
                continue
            self._draw_entry(plot, entry)
        plot.draw(painter)
        self._drawn = {"x": plot._x_axis.range, "y": plot._y_axis.range}
        # After the axes exist: the plot places its own box and axis ranges in
        # draw(), and an image is positioned in data coordinates, so it cannot
        # be blitted before that mapping is known.
        self._draw_bands(painter, plot)
        for texture, x0, y0, width, height in getattr(plot, "_images", []):
            left = plot._x_axis.to_pixels(x0)
            right = plot._x_axis.to_pixels(x0 + width)
            top = plot._y_axis.to_pixels(y0 + height)
            bottom = plot._y_axis.to_pixels(y0)
            painter.image(
                min(left, right), min(top, bottom), abs(right - left), abs(bottom - top), texture
            )
        self._draw_axes(painter, plot, x, y, w, h, row)
        self._draw_texts(painter, plot)

    def _draw_axes(self, painter, plot, x, y, w, h, row) -> None:
        """Tick numbers, axis titles and the panel title, around the plot area."""
        from emtk.painter import ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER

        bx, by, bw, bh = plot.x, plot.y, plot.w, plot.h
        if self._axis_visible["left"]:
            ticks = plot._y_axis.ticks(plot.y_tick_target)
            for value, text in zip(ticks, _tick_labels(ticks, self._log["y"])):
                py = plot._y_axis.to_pixels(value)
                if by - 1.0 <= py <= by + bh + 1.0:
                    painter.text(
                        bx - _Y_TICK_WIDTH - 6.0,
                        py - row * 0.5,
                        _Y_TICK_WIDTH,
                        row,
                        ALIGN_RIGHT | ALIGN_VCENTER,
                        text,
                        _TICK_TEXT,
                    )
            label = self._labels.get("left")
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
                        _LABEL_TEXT,
                        -90.0,
                    )
                else:
                    painter.text(x + 2.0, by, bx - x - 4.0, row, ALIGN_VCENTER, label, _LABEL_TEXT)
        if self._axis_visible["bottom"]:
            ticks = plot._x_axis.ticks(plot.x_tick_target)
            for value, text in zip(ticks, _tick_labels(ticks, self._log["x"])):
                px = plot._x_axis.to_pixels(value)
                if bx - 1.0 <= px <= bx + bw + 1.0:
                    painter.text(
                        px - 40.0,
                        by + bh + 2.0,
                        80.0,
                        row,
                        ALIGN_HCENTER | ALIGN_VCENTER,
                        text,
                        _TICK_TEXT,
                    )
            label = self._labels.get("bottom")
            if label:
                painter.text(
                    bx,
                    by + bh + 2.0 + row,
                    bw,
                    row,
                    ALIGN_HCENTER | ALIGN_VCENTER,
                    label,
                    _LABEL_TEXT,
                )
        if self._title:
            painter.text(
                bx, y + 1.0, bw, row, ALIGN_HCENTER | ALIGN_VCENTER, self._title, _LABEL_TEXT
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
            elif entry.kind == "image":
                x0, y0, width, height = state["rect"]
                start, extent = (x0, width) if axis == 0 else (y0, height)
                exact_low = min(exact_low, float(start))
                exact_high = max(exact_high, float(start + extent))
            elif entry.kind == "region" and axis == 0:
                a, b = entry.bounds
                exact_low, exact_high = min(exact_low, a), max(exact_high, b)
        return (
            (low, high) if high >= low else None,
            (exact_low, exact_high) if exact_high >= exact_low else None,
        )

    def _fitted(self, axis: int, fraction: float, members=None) -> tuple[float, float] | None:
        """The auto-fitted range of *axis* over *members* (default: this panel)."""
        series, exact = [], []
        for member in members or (self,):
            data, placed = member._extent(axis)
            if data is not None:
                series.append(data)
            if placed is not None:
                exact.append(placed)
        spans = []
        if series:
            spans.append(
                self._padded((min(a for a, _ in series), max(b for _, b in series)), fraction)
            )
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
            if xs.size:
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
            left, right = sorted((plot._x_axis.to_pixels(low), plot._x_axis.to_pixels(high)))
            fill = entry.state.get("brush", (70, 110, 160, 50))
            painter.fill_rect(left, top, right - left, height, fill)
            edge = (*fill[:3], 220)
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
                painter.fill_triangle((cx, cy), previous, point, (*colour, 60))
                previous = point
        else:
            painter.stroke_rect(*box, colour, (*colour, 40))
        entry.state["_box"] = (box[0], box[1], box[0] + box[2], box[1] + box[3])

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
        alpha = 60 if kind == "ellipse" else 40
        for index, point in enumerate(outline):
            painter.fill_triangle(
                centre, point, outline[(index + 1) % len(outline)], (*colour, alpha)
            )
        xs, ys = [p[0] for p in outline], [p[1] for p in outline]
        entry.state["_box"] = (min(xs), min(ys), max(xs), max(ys))

    def _draw_bars(self, painter, plot, entry: _Entry) -> None:
        """A bar per sample, from the axis floor up to its height."""
        xs, heights = entry.state["x"], entry.state["height"]
        if not len(xs):
            return
        width = entry.state.get("width")
        if width is None:
            width = float(np.min(np.diff(xs))) * 0.8 if len(xs) > 1 else 1.0
        floor = plot._y_axis.to_pixels(0.0)
        for centre, height in zip(xs, heights):
            left = plot._x_axis.to_pixels(centre - width / 2.0)
            right = plot._x_axis.to_pixels(centre + width / 2.0)
            top = plot._y_axis.to_pixels(height)
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
        for index in range(len(xs)):
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
        for entry in reversed(self._entries):
            if not entry.visible or not entry.state.get("movable", True):
                continue
            if entry.kind == "text":
                box = entry.state.get("_box")
                if box and box[0] <= px <= box[2] and box[1] <= py <= box[3]:
                    self._dragging = (entry, (px, py))
                    break
                continue
            if entry.kind == "roi":
                box = entry.state.get("_box")
                if box and box[0] <= px <= box[2] and box[1] <= py <= box[3]:
                    self._dragging = (entry, (self._from_pixels(px), self._from_pixels_y(py)))
                    break
                continue
            span = entry.state.get("_pixels")
            if span is None or entry.kind not in ("region", "marker"):
                continue
            if entry.kind == "region":
                # An edge moves on its own, as pyqtgraph's region does; the
                # inside moves the whole range.
                for edge, at in (("low", span[0]), ("high", span[1])):
                    if abs(px - at) <= 5.0:
                        self._dragging = (entry, (edge, self._from_pixels(px)))
                        break
                if self._dragging is not None:
                    break
            if span[0] - 3.0 <= px <= span[1] + 3.0:
                self._dragging = (entry, self._from_pixels(px))
                break
        if self._dragging is None and self._interactive:
            # Nothing under the pointer: the gesture pans the view, which is
            # what dragging a plot does everywhere else.
            self._panning = (self._from_pixels(px), self._from_pixels_y(py))
            for callback in self._click_callbacks:
                callback(self._from_pixels(px), self._from_pixels_y(py), 1)

    def drag(self, px: float, py: float, *_args: Any) -> None:
        """Move whatever the press picked up, or pan the view."""
        if getattr(self, "_panning", None):
            grabbed_x, grabbed_y = self._panning
            (x0, x1), (y0, y1) = self._view()
            dx = grabbed_x - self._from_pixels(px)
            dy = grabbed_y - self._from_pixels_y(py)
            self._set_view(x=(x0 + dx, x1 + dx), y=(y0 + dy, y1 + dy))
            return
        if not getattr(self, "_dragging", None):
            return
        entry, grabbed_at = self._dragging
        if entry.kind == "text":
            grabbed_x, grabbed_y = grabbed_at
            if entry.state.get("anchored"):
                x, y = entry.state["pos"]
                entry.set_position(x + px - grabbed_x, y + py - grabbed_y)
            else:
                x, y = entry.state["pos"]
                entry.set_position(
                    x + self._from_pixels(px) - self._from_pixels(grabbed_x),
                    y + self._from_pixels_y(py) - self._from_pixels_y(grabbed_y),
                )
            self._dragging = (entry, (px, py))
            return
        if entry.kind == "region" and isinstance(grabbed_at, tuple):
            edge, _ = grabbed_at
            low, high = entry.bounds
            at = self._from_pixels(px)
            if edge == "low":
                entry.set_bounds(min(at, high), high)
            else:
                entry.set_bounds(low, max(at, low))
            self._dragging = (entry, (edge, at))
            entry._notify(final=False)
            return
        if entry.kind == "roi":
            grabbed_x, grabbed_y = grabbed_at
            now_x, now_y = self._from_pixels(px), self._from_pixels_y(py)
            x, y = entry.pos
            entry.set_pos((x + now_x - grabbed_x, y + now_y - grabbed_y))
            self._dragging = (entry, (now_x, now_y))
            entry._notify(final=False)
            return
        moved = self._from_pixels(px) - grabbed_at
        if entry.kind == "region":
            low, high = entry.bounds
            entry.set_bounds(low + moved, high + moved)
        else:
            entry.set_value(entry.value + moved)
        self._dragging = (entry, self._from_pixels(px))
        entry._notify(final=False)

    def release(self, *_args: Any) -> None:
        """Finish the drag and tell the listeners where it ended."""
        if getattr(self, "_dragging", None):
            entry, _ = self._dragging
            if entry.kind != "text":
                entry._notify(final=True)
        self._dragging = None
        self._panning = None

    def hover(self, px: float, py: float, *_args: Any) -> None:
        """Report the pointer in data coordinates."""
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
                data = data.T
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
    def set_labels(self, *, left=None, bottom=None, right=None, top=None) -> None:
        """Set axis labels; axes not named are left alone."""
        for side, text in (("left", left), ("bottom", bottom), ("right", right), ("top", top)):
            if text is not None:
                self._labels[side] = str(text)
        self.refresh()

    def set_title(self, title: str) -> None:
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

    def _data_range(self, axis: int) -> tuple[float, float]:
        """The extent of the drawn data along *axis*, or ``(0, 1)`` when empty.

        An image counts as data: its rect is where it sits, so a panel holding
        only a heatmap fits the heatmap rather than the unit square.
        """
        spans: list[tuple[float, float]] = []
        for entry in self._entries:
            if not entry.visible:
                continue
            if entry.kind in ("curve", "scatter"):
                samples = entry.state["x" if axis == 0 else "y"]
                if samples is not None and len(samples):
                    spans.append((float(np.min(samples)), float(np.max(samples))))
            elif entry.kind == "image":
                x0, y0, width, height = entry.state["rect"]
                start, extent = (x0, width) if axis == 0 else (y0, height)
                spans.append((float(start), float(start + extent)))
        if not spans:
            return (0.0, 1.0)
        low = min(start for start, _ in spans)
        high = max(end for _, end in spans)
        return (low, high) if high > low else (low, low + 1.0)

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
        """Toggle the axis grid."""
        if x is not None or y is not None:
            self._grid = bool(x or y)
        self.refresh()

    def set_background(self, color) -> None:
        """Set the panel background colour."""
        self._background = _rgb(color, self._background)
        if hasattr(self._widget, "background"):
            self._widget.background = self._background
        self.refresh()

    def set_tick_spacing(self, side, *, major=None, minor=None) -> None:
        """Not offered: emtk chooses its own tick interval."""

    def set_aspect_locked(self, lock: bool, ratio: float = 1.0) -> None:
        """Not offered yet; the panel always fills its widget."""

    def set_si_prefix(self, *, x=None, y=None) -> None:
        """Not offered: emtk never prefixes tick values, which is the default
        chiplot asks both backends for.
        """

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

    def set_interactive(self, *, mouse=None, menu=None) -> None:
        """Enable or disable mouse pan and zoom."""
        if mouse is not None:
            self._interactive = bool(mouse)

    def export_image(self, path, *, width=None) -> bool:
        """Render the panel to an image file; ``True`` when it was written."""
        from qtpy import QtGui

        widget = self._widget
        size = widget.size()
        if width:
            scale = float(width) / max(size.width(), 1)
            size.setWidth(int(width))
            size.setHeight(int(size.height() * scale))
        pixmap = QtGui.QPixmap(size)
        pixmap.fill()
        widget.render(pixmap)
        return bool(pixmap.save(str(path)))

    def native(self) -> Any:
        """The display list; emtk keeps no plot object between frames."""
        return self._entries

    # -- the families this backend does not draw yet -------------------
    def _unsupported(self, what: str):
        raise NotImplementedError(
            f"emtk: {what} is not drawn yet; use CHISURF_PLOT_BACKEND="
            f"pyqtgraph for a plot that needs it"
        )

    def add_bars(self, x, height, *, width=None, pen=None, brush=None) -> H.Bars:
        """Draw a bar graph and return its handle."""
        xs, heights = _finite_pairs(x, height)
        return self._add(
            "bars",
            x=xs,
            height=heights,
            width=None if width is None else float(width),
            brush=_rgb(brush, (120, 150, 200)),
        )

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
        if height is not None and top is None and bottom is None:
            half = np.asarray(height, dtype=float).ravel() / 2.0
            tops = bottoms = half
        else:
            tops = np.asarray(top if top is not None else 0.0, dtype=float).ravel()
            bottoms = np.asarray(bottom if bottom is not None else 0.0, dtype=float).ravel()
        tops = np.resize(tops, xs.shape) if tops.size else np.zeros_like(xs)
        bottoms = np.resize(bottoms, xs.shape) if bottoms.size else np.zeros_like(xs)
        return self._add(
            "errorbars",
            x=xs,
            y=ys,
            top=tops,
            bottom=bottoms,
            color=_rgb(pen),
            beam=float(beam or 3.0),
        )

    def add_image(self, data, *, colormap=None, levels=None, rect=None, axis_order=None) -> H.Image:
        """Draw an image or heatmap and return its handle."""
        values = np.asarray(data, dtype=float)
        if values.ndim != 2:
            raise ValueError(f"an image is 2-D; got shape {values.shape}")
        if str(axis_order or "row-major") not in ("row-major", "col-major"):
            raise ValueError(f"unknown axis order {axis_order!r}")
        col_major = str(axis_order) == "col-major"
        rows, columns = values.shape[::-1] if col_major else values.shape
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
        if _orientation(orientation) != "vertical":
            raise NotImplementedError(
                "emtk: a horizontal region is not drawn yet; use "
                "CHISURF_PLOT_BACKEND=pyqtgraph for one"
            )
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
    ) -> H.Roi:
        """Draw a region of interest and return its handle.

        Rectangles, ellipses, polygons and polylines are drawn and can be
        dragged; a rectangle or ellipse is turned ``angle`` degrees about its
        centre. Resize and rotation grips are not drawn: a shape is moved whole,
        and its size and angle are set programmatically.
        """
        shape = str(getattr(kind, "value", kind)).lower()
        if shape not in ("rect", "rectangle", "ellipse", "circle", "polygon", "polyline"):
            raise NotImplementedError(
                f"emtk: a {shape!r} region of interest is not drawn yet; "
                f"use CHISURF_PLOT_BACKEND=pyqtgraph for one"
            )
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
    """An image view: one canvas showing a picture, with a frame slider.

    pyqtgraph's ImageView is a widget of its own with a LUT panel and a
    timeline. Here it is the panel that already draws images, plus the two
    things the view adds -- a stack it can step through, and clicks reported
    in image coordinates.
    """

    def __init__(self, **opts: Any) -> None:
        self._canvas = EmtkCanvas(**opts)
        self._stack: np.ndarray | None = None
        self._frame = 0
        self._image: _Entry | None = None
        self._colormap: Any = "viridis"
        self._overlays: list[_Entry] = []

    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable Qt widget."""
        return self._canvas.widget()

    def set_image(self, data, *, auto_levels: bool = True, axes=None) -> None:
        """Show an image, or a ``(t, y, x)`` stack whose first frame is shown."""
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
        if self._image is None:
            self._image = self._canvas.add_image(frame, colormap=self._colormap)
        else:
            self._image.set_image(frame)
            if auto_levels:
                self._image.auto_levels()

    def set_frame(self, index: int) -> None:
        """Show frame *index* of a stack (a no-op for a single image)."""
        if self._stack is None:
            return
        self._frame = int(index) % self._stack.shape[0]
        if self._image is not None:
            self._image.set_image(self._stack[self._frame])

    def set_colormap(self, name, source: str = "matplotlib") -> None:
        """Apply a named colormap."""
        self._colormap = name
        if self._image is not None:
            self._image.set_colormap(name)

    def clear(self) -> None:
        """Clear the image and its overlays."""
        self._canvas.clear()
        self._image = None
        self._overlays.clear()
        self._stack = None

    def set_histogram_width(self, width) -> None:
        """No histogram panel to size: levels are set through the handle."""

    def set_interactive(self, *, mouse=None, menu=None) -> None:
        """No pan/zoom yet; the view always shows the whole image."""

    def add_overlay(self, data, *, colormap=None) -> H.Image:
        """Overlay a second image on the view and return its handle."""
        overlay = self._canvas.add_image(
            np.asarray(data, dtype=float), colormap=colormap or self._colormap
        )
        overlay.z = 1.0 + len(self._overlays)
        self._overlays.append(overlay)
        return overlay

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
        )

    def on_click(self, callback) -> None:
        """Register ``callback(x, y)`` for clicks in image coordinates."""
        self._canvas.on_click(lambda x, y, *_: callback(x, y))

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

    def __init__(self, image: _Entry, colormap=None) -> None:
        from emtk.qt_host import ControlHost

        self._image = image
        self._callbacks: list[Callable] = []
        self._drag: tuple[str, float, tuple[float, float]] | None = None
        self._box = (0.0, 0.0, 1.0, 1.0)
        self._alive = True
        self._visible = True
        self._z = 0.0
        if colormap is not None:
            image.set_colormap(colormap)
        self._widget = ControlHost(self, background=(30, 32, 38))
        self._widget.setMinimumWidth(56)
        self._widget.setMaximumWidth(80)

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
    def widget(self) -> QtWidgets.QWidget:
        """The Qt widget the grid places."""
        return self._widget

    def set_colormap(self, colormap) -> None:
        """Map the image, and the ramp, through ``colormap``."""
        self._image.set_colormap(colormap)
        self._widget.update()

    def set_levels(self, low: float, high: float, *, notify: bool = False) -> None:
        """Set the image's mapped range; a drag also tells the listeners."""
        self._image.set_levels(low, high)
        self._widget.update()
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
        self._widget.setVisible(self._visible)

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
        """Take the ramp out of its grid."""
        self._alive = False
        self._widget.setParent(None)

    def is_alive(self) -> bool:
        """Whether the ramp still belongs to a grid."""
        return self._alive

    @property
    def native(self) -> Any:
        """The Qt widget hosting the ramp."""
        return self._widget


class EmtkGrid(base.GridCanvas):
    """Several panels in a grid, each an :class:`EmtkCanvas` of its own."""

    def __init__(self, **opts: Any) -> None:
        self._opts = opts
        self._panels: list[EmtkCanvas] = []
        self._row = 0
        self._column = 0
        self._widget = QtWidgets.QWidget()
        self._layout = QtWidgets.QGridLayout(self._widget)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

    def widget(self) -> QtWidgets.QWidget:
        """Return the embeddable Qt widget for the whole grid."""
        return self._widget

    def add_panel(self, *, row=None, col=None, rowspan=1, colspan=1, title=None) -> base.Canvas:
        """Add and return a panel at the given cell, or at the cursor."""
        if row is None:
            row = self._row
        if col is None:
            col = self._column
        panel = EmtkCanvas(title=title, **self._opts)
        self._layout.addWidget(panel.widget(), int(row), int(col), int(rowspan), int(colspan))
        self._panels.append(panel)
        self._column = int(col) + int(colspan)
        return panel

    def add_colorbar(
        self, image, *, colormap=None, row=None, col=None, rowspan=1, colspan=1
    ) -> H.ColorBar:
        """Add a colour ramp bound to ``image`` at the given cell, or at the cursor."""
        if row is None:
            row = self._row
        if col is None:
            col = self._column
        bar = _ColorBar(image, colormap)
        self._layout.addWidget(bar.widget(), int(row), int(col), int(rowspan), int(colspan))
        self._column = int(col) + int(colspan)
        return bar

    def next_row(self) -> None:
        """Move the insertion cursor to the start of the next row."""
        self._row += 1
        self._column = 0

    def clear(self) -> None:
        """Remove every panel and start again at the first cell."""
        for panel in self._panels:
            widget = panel.widget()
            self._layout.removeWidget(widget)
            widget.setParent(None)
        self._panels.clear()
        self._row = self._column = 0

    def set_column_stretch(self, column: int, factor: int) -> None:
        """Set the relative width of a column."""
        self._layout.setColumnStretch(int(column), int(factor))

    def set_row_stretch(self, row: int, factor: int) -> None:
        """Set the relative height of a row."""
        self._layout.setRowStretch(int(row), int(factor))

    def native(self) -> Any:
        """The panels themselves."""
        return self._panels


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

    def raw_module(self):
        """Return emtk itself."""
        import emtk

        return emtk
