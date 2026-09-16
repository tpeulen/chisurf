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
and text labels. What is left -- ROIs and arrows, the multi-panel grid and the
image view -- raises :class:`NotImplementedError` naming what is missing, because a
plot that silently omits half of what it was asked to draw is worse than one
that says so. Those families are the rest of PRD-104.

Select it with ``CHISURF_PLOT_BACKEND=emtk`` or ``gui.plot.backend: emtk``.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Sequence

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
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return tuple(int(component) for component in color[:3])
    text = str(color).strip()
    if text.startswith("#") and len(text) >= 7:
        return (int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16))
    return default


def _orientation(value) -> str:
    """Return ``"vertical"`` or ``"horizontal"`` from a string or the enum.

    The facade hands down ``handles.Orientation``; ``str()`` on an enum is
    ``"Orientation.VERTICAL"``, which matches neither.
    """
    return str(getattr(value, "value", value)).lower()


def _finite_pairs(x, y) -> tuple[np.ndarray, np.ndarray]:
    """Return ``(x, y)`` as float arrays with the non-finite samples dropped."""
    xs = np.asarray(x, dtype=float).ravel()
    ys = np.asarray(y, dtype=float).ravel()
    if xs.size and ys.size and xs.size != ys.size:
        size = min(xs.size, ys.size)
        xs, ys = xs[:size], ys[:size]
    if xs.size == 0:
        return xs, ys
    keep = np.isfinite(xs) & np.isfinite(ys)
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
    rgba = table[indices]                      # (rows, columns, 4)
    rows, columns = rgba.shape[0], rgba.shape[1]
    return Texture(columns, rows, rgba.tobytes()), rows, columns


class _Entry:
    """One item in a canvas's display list, and the handle the caller holds."""

    def __init__(self, canvas: "EmtkCanvas", kind: str, **state: Any) -> None:
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

    def native(self) -> Any:
        """The display-list entry itself; emtk has no per-series object."""
        return self.state

    # -- Curve / Scatter ----------------------------------------------
    def set_data(self, x, y=None, **_: Any) -> None:
        """Replace the series' samples."""
        if y is None and x is not None and len(np.shape(x)) == 2:
            data = np.asarray(x, dtype=float)
            x, y = data[:, 0], data[:, 1]
        self.state["x"], self.state["y"] = _finite_pairs(x, y)
        self._canvas.refresh()

    def get_data(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the samples as ``(x, y)``."""
        return self.state["x"], self.state["y"]

    def set_pen(self, pen: S.Pen) -> None:
        """Set the line colour and width."""
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

    def set_levels(self, levels) -> None:
        """Set the ``(low, high)`` the colours span."""
        self.state["levels"] = None if levels is None else (float(levels[0]), float(levels[1]))
        self.state["texture"] = None
        self._canvas.refresh()

    def set_colormap(self, colormap) -> None:
        """Set the colormap the samples are mapped through."""
        self.state["colormap"] = colormap
        self.state["texture"] = None
        self._canvas.refresh()

    def set_rect(self, rect) -> None:
        """Place the image in data coordinates: ``(x, y, width, height)``."""
        self.state["rect"] = tuple(float(v) for v in rect)
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

    def set_position(self, pos) -> None:
        """Move the label to a data coordinate."""
        self.state["pos"] = (float(pos[0]), float(pos[1]))
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
        """Draw the whole display list into the box emtk gives us."""
        from emtk.widgets.plot import Plot as EmtkPlot

        plot = EmtkPlot(
            x, y, w, h,
            x_range=self._range["x"],
            y_range=self._range["y"],
            show_ticks=True,
            show_legend=self._legend,
        )
        for entry in sorted(self._entries, key=lambda e: e.z):
            if not entry.visible:
                continue
            self._draw_entry(plot, entry)
        plot.draw(painter)
        # After the axes exist: the plot places its own box and axis ranges in
        # draw(), and an image is positioned in data coordinates, so it cannot
        # be blitted before that mapping is known.
        self._draw_bands(painter, plot)
        for texture, x0, y0, width, height in getattr(plot, "_images", []):
            left = plot._x_axis.to_pixels(x0)
            right = plot._x_axis.to_pixels(x0 + width)
            top = plot._y_axis.to_pixels(y0 + height)
            bottom = plot._y_axis.to_pixels(y0)
            painter.image(min(left, right), min(top, bottom),
                          abs(right - left), abs(bottom - top), texture)

    def _draw_entry(self, plot, entry: _Entry) -> None:
        """Add one display-list entry to *plot*."""
        state = entry.state
        label = state.get("name") or ""
        if entry.kind == "curve":
            xs, ys = self._scaled(state["x"], state["y"])
            if xs.size:
                plot.line(label, xs, ys, colour=state.get("color"),
                          width=state.get("width", 1.5))
            if state.get("symbol") is not None and xs.size:
                plot.scatter(label, xs, ys,
                             colour=state.get("symbol_color", state.get("color")),
                             radius=max(1.0, float(state.get("symbol_size", 7.0)) / 2.0))
        elif entry.kind == "scatter":
            xs, ys = self._scaled(state["x"], state["y"])
            if xs.size:
                plot.scatter(label, xs, ys, colour=state.get("color"),
                             radius=max(1.0, float(state.get("symbol_size", 7.0)) / 2.0))
        elif entry.kind == "image":
            self._draw_image(plot, entry)
        elif entry.kind == "marker":
            if state.get("orientation") == "horizontal":
                plot.hline(float(state.get("value", 0.0)),
                           state.get("color", (200, 200, 200)), label or None)
            else:
                # A vertical guide: emtk's Plot draws horizontal ones, so this
                # is a one-pixel band drawn with the regions below.
                plot._x_axis.fit((entry.value, entry.value))
        elif entry.kind == "region":
            low, high = entry.bounds
            plot._x_axis.fit((low, high))

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
            if entry.kind == "region":
                low, high = entry.bounds
                left = plot._x_axis.to_pixels(low)
                right = plot._x_axis.to_pixels(high)
                painter.fill_rect(min(left, right), top, abs(right - left), height,
                                  entry.state.get("brush", (70, 110, 160, 60)))
                entry.state["_pixels"] = (min(left, right), max(left, right))
            elif entry.kind == "marker" and entry.state.get("orientation") != "horizontal":
                at = plot._x_axis.to_pixels(entry.value)
                painter.fill_rect(at, top, 1.0, height,
                                  entry.state.get("color", (200, 200, 200)))
                entry.state["_pixels"] = (at - 4.0, at + 4.0)
            elif entry.kind == "bars":
                self._draw_bars(painter, plot, entry)
            elif entry.kind == "band":
                self._draw_band(painter, plot, entry)
            elif entry.kind == "errorbars":
                self._draw_errorbars(painter, plot, entry)
            elif entry.kind == "text":
                x, y = entry.state["pos"]
                painter.text(plot._x_axis.to_pixels(x), plot._y_axis.to_pixels(y),
                             120.0, plot.p_line_height if hasattr(plot, "p_line_height") else 14.0,
                             0, entry.text, entry.state.get("color", (220, 220, 220)))
        self._axis = plot._x_axis

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
            painter.fill_rect(min(left, right), min(top, floor), abs(right - left),
                              abs(floor - top), entry.state.get("brush", (120, 150, 200)))

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
            painter.fill_rect(min(left, right), min(top, bottom),
                              max(abs(right - left), 1.0), abs(bottom - top), colour)

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

    def press(self, px: float, py: float, *_args: Any) -> None:
        """Start a drag when the press lands on a draggable band."""
        self._dragging = None
        for entry in reversed(self._entries):
            if not entry.visible or not entry.state.get("movable", True):
                continue
            span = entry.state.get("_pixels")
            if span is None or entry.kind not in ("region", "marker"):
                continue
            if span[0] - 3.0 <= px <= span[1] + 3.0:
                self._dragging = (entry, self._from_pixels(px))
                break

    def drag(self, px: float, py: float, *_args: Any) -> None:
        """Move whatever the press picked up."""
        if not getattr(self, "_dragging", None):
            return
        entry, grabbed_at = self._dragging
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
            entry._notify(final=True)
        self._dragging = None

    def _draw_image(self, plot, entry: _Entry) -> None:
        """Place an image in the plot's data space.

        The texture is built once and kept until the data, levels or colormap
        change: a frame is drawn on every repaint, and re-mapping a megapixel
        array through a colormap each time would make panning the plot a
        slideshow.
        """
        state = entry.state
        if state.get("texture") is None:
            state["texture"], rows, columns = _texture(
                state["data"], state.get("colormap"), state.get("levels"))
            state.setdefault("rect", (0.0, 0.0, float(columns), float(rows)))
        # The axes have to know the image is there, or a panel holding nothing
        # else auto-fits to an empty range and the image lands outside it.
        x0, y0, width, height = state["rect"]
        plot._x_axis.fit((x0, x0 + width))
        plot._y_axis.fit((y0, y0 + height))
        entry.state["_placed"] = (x0, y0, width, height)
        plot._images = getattr(plot, "_images", [])
        plot._images.append((state["texture"], x0, y0, width, height))

    def _scaled(self, xs, ys) -> tuple[np.ndarray, np.ndarray]:
        """Apply the log scaling the panel is set to, dropping what it kills."""
        if not (self._log["x"] or self._log["y"]):
            return xs, ys
        xs = np.asarray(xs, dtype=float)
        ys = np.asarray(ys, dtype=float)
        keep = np.ones(xs.shape, dtype=bool)
        if self._log["x"]:
            keep &= xs > 0
        if self._log["y"]:
            keep &= ys > 0
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

    def add_curve(self, x, y, *, pen, name=None, fill=None, step=False, symbol=None,
                  symbol_size=7.0, symbol_brush=None, symbol_pen=None,
                  skip_missing=True) -> H.Curve:
        """Draw a line curve (optionally with markers) and return its handle."""
        if fill is not None:
            raise NotImplementedError(
                "emtk: a filled curve is not drawn yet (PRD-104); use the "
                "pyqtgraph backend for filled series"
            )
        xs, ys = _finite_pairs(x, y)
        return self._add(
            "curve", x=xs, y=ys, name=name, color=_rgb(pen),
            width=float(getattr(pen, "width", 1.0) or 1.0), symbol=symbol,
            symbol_size=symbol_size,
            symbol_color=_rgb(symbol_brush, _rgb(pen)) if symbol is not None else None,
            step=step,
        )

    def add_scatter(self, x, y, *, size=7.0, pen=None, brush=None, symbol=None,
                    name=None) -> H.Scatter:
        """Draw a scatter cloud and return its handle."""
        xs, ys = _finite_pairs(x, y)
        return self._add("scatter", x=xs, y=ys, name=name,
                         color=_rgb(brush, _rgb(pen)), symbol_size=size, symbol=symbol)

    def add_marker(self, pos, *, orientation="vertical", movable=False, pen=None,
                   label=None) -> H.Marker:
        """Draw a cursor line and return its handle."""
        return self._add("marker", value=float(pos), orientation=_orientation(orientation),
                         color=_rgb(pen), name=label, movable=bool(movable))

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
        for side, text in (("left", left), ("bottom", bottom),
                           ("right", right), ("top", top)):
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
        """Set the visible range in data units."""
        if x is not None:
            self._range["x"] = (float(x[0]), float(x[1]))
        if y is not None:
            self._range["y"] = (float(y[0]), float(y[1]))
        self.refresh()
        self._announce_range()

    def get_range(self) -> tuple[tuple[float, float], tuple[float, float]]:
        """Return the visible ``((x0, x1), (y0, y1))`` range."""
        return (self._range["x"] or self._data_range(0),
                self._range["y"] or self._data_range(1))

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
        self._range["x"] = None
        self._range["y"] = None
        self.refresh()
        self._announce_range()

    def enable_auto_range(self, *, x=None, y=None) -> None:
        """Keep the view fitted to contents as data changes."""
        if x:
            self._range["x"] = None
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
        chiplot asks both backends for."""

    def invert_y(self, invert: bool = True) -> None:
        """Not offered yet (PRD-104): the y-axis always runs upwards."""
        if invert:
            raise NotImplementedError("emtk: an inverted y-axis is not drawn yet (PRD-104)")

    # -- input ---------------------------------------------------------
    def on_click(self, callback) -> None:
        """Register ``callback(x, y, button)`` for clicks in data coordinates."""
        self._click_callbacks.append(callback)

    def on_mouse_move(self, callback) -> None:
        """Register ``callback(x, y)`` for pointer motion in data coordinates."""
        self._move_callbacks.append(callback)

    def native(self) -> Any:
        """The display list; emtk keeps no plot object between frames."""
        return self._entries

    # -- the families this backend does not draw yet -------------------
    def _unsupported(self, what: str):
        raise NotImplementedError(
            f"emtk: {what} is not drawn yet (PRD-104); use CHISURF_PLOT_BACKEND="
            f"pyqtgraph for a plot that needs it"
        )

    def add_bars(self, x, height, *, width=None, pen=None, brush=None) -> H.Bars:
        """Draw a bar graph and return its handle."""
        xs, heights = _finite_pairs(x, height)
        return self._add("bars", x=xs, height=heights,
                         width=None if width is None else float(width),
                         brush=_rgb(brush, (120, 150, 200)))

    def add_fill_between(self, lower, upper, *, brush=None) -> H.Handle:
        """Fill the area between two curve handles and return its handle."""
        low_x, low_y = lower.get_data()
        _, high_y = upper.get_data()
        size = min(len(low_x), len(low_y), len(high_y))
        fill = _rgb(brush, (120, 150, 200))
        return self._add("band", x=low_x[:size], lower=low_y[:size],
                         upper=high_y[:size], brush=(*fill, 70))

    def add_errorbars(self, x, y, *, height=None, top=None, bottom=None, pen=None,
                      beam=None) -> H.ErrorBars:
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
        return self._add("errorbars", x=xs, y=ys, top=tops, bottom=bottoms,
                         color=_rgb(pen), beam=float(beam or 3.0))

    def add_image(self, data, *, colormap=None, levels=None, rect=None,
                  axis_order=None) -> H.Image:
        """Draw an image or heatmap and return its handle."""
        values = np.asarray(data, dtype=float)
        if values.ndim != 2:
            raise ValueError(f"an image is 2-D; got shape {values.shape}")
        if str(axis_order or "row-major") not in ("row-major", "col-major"):
            raise ValueError(f"unknown axis order {axis_order!r}")
        if str(axis_order) == "col-major":
            values = values.T
        return self._add(
            "image", data=values, colormap=colormap,
            levels=None if levels is None else (float(levels[0]), float(levels[1])),
            rect=tuple(float(v) for v in rect) if rect is not None
            else (0.0, 0.0, float(values.shape[1]), float(values.shape[0])),
            texture=None,
        )

    def add_region(self, bounds, *, orientation="vertical", movable=True, brush=None,
                   pen=None) -> H.Region:
        """Draw a draggable interval selector and return its handle."""
        if _orientation(orientation) != "vertical":
            raise NotImplementedError(
                "emtk: a horizontal region is not drawn yet (PRD-104); use "
                "CHISURF_PLOT_BACKEND=pyqtgraph for one"
            )
        low, high = (float(bounds[0]), float(bounds[1]))
        fill = _rgb(brush, (70, 110, 160))
        return self._add("region", bounds=(min(low, high), max(low, high)),
                         movable=bool(movable), brush=(*fill, 60),
                         orientation=_orientation(orientation))

    def add_roi(self, *, kind="rect", pos=None, size=None, pen=None, movable=True,
                rotatable=False, points=None) -> H.Roi:
        """Not drawn yet."""
        self._unsupported("a region of interest")

    def add_arrow(self, pos, *, angle=0.0, size=None, tip_angle=None, head_width=None,
                  tail_length=None, tail_width=None, pen=None, brush=None) -> H.Arrow:
        """Not drawn yet."""
        self._unsupported("an arrow")

    def add_text(self, text, pos, *, color=None, anchor=None, draggable=False,
                 fill=None, border=None, anchored=False) -> H.Text:
        """Draw a text label at a data coordinate and return its handle."""
        return self._add("text", text=str(text),
                         pos=(float(pos[0]), float(pos[1])),
                         color=_rgb(color, (220, 220, 220)))


class EmtkBackend(base.Backend):
    """chiplot's backend over emtk."""

    name = "emtk"

    def create_canvas(self, **opts) -> base.Canvas:
        """Create a single-panel canvas."""
        return EmtkCanvas(**opts)

    def create_grid(self, **opts):
        """Not offered yet (PRD-104): one panel at a time."""
        raise NotImplementedError(
            "emtk: a multi-panel grid is not drawn yet (PRD-104); use "
            "CHISURF_PLOT_BACKEND=pyqtgraph"
        )

    def create_image_view(self, **opts):
        """Not offered yet (PRD-104)."""
        raise NotImplementedError(
            "emtk: the image view is not drawn yet (PRD-104); use "
            "CHISURF_PLOT_BACKEND=pyqtgraph"
        )

    def configure(self, **_: Any) -> None:
        """Nothing process-wide to set: emtk draws through its own painter."""

    def raw_module(self):
        """Return emtk itself."""
        import emtk

        return emtk
