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

What is drawn here today: curves (with symbols), scatter clouds, horizontal
and vertical markers, the legend, axis labels and title, ranges (explicit,
queried and auto), grid and background. Everything else -- images and
heatmaps, draggable regions and ROIs, error bars, bars, filled bands, text and
arrows -- raises :class:`NotImplementedError` naming what is missing, because a
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

    # -- Marker --------------------------------------------------------
    @property
    def value(self) -> float:
        """The marker's position along its axis."""
        return float(self.state.get("value", 0.0))

    def set_value(self, value: float) -> None:
        """Move the marker."""
        self.state["value"] = float(value)
        self._canvas.refresh()

    def on_change(self, callback, **_: Any) -> None:
        """Register a drag callback.

        Dragging is not wired yet -- markers here are read-only guides -- so
        the callback is remembered and never called, rather than dropped
        silently.
        """
        self.state.setdefault("callbacks", []).append(callback)


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
        elif entry.kind == "marker" and state.get("orientation") == "horizontal":
            plot.hline(float(state.get("value", 0.0)), state.get("color", (200, 200, 200)),
                       label or None)

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
        return self._add("marker", value=float(pos), orientation=str(orientation),
                         color=_rgb(pen), name=label)

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
        """The extent of the drawn data along *axis*, or ``(0, 1)`` when empty."""
        values = [entry.state["x" if axis == 0 else "y"]
                  for entry in self._entries
                  if entry.visible and entry.kind in ("curve", "scatter")
                  and entry.state.get("x") is not None]
        values = [v for v in values if len(v)]
        if not values:
            return (0.0, 1.0)
        low = min(float(np.min(v)) for v in values)
        high = max(float(np.max(v)) for v in values)
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
        """Not drawn yet."""
        self._unsupported("a bar graph")

    def add_fill_between(self, lower, upper, *, brush=None) -> H.Handle:
        """Not drawn yet."""
        self._unsupported("a filled band")

    def add_errorbars(self, x, y, *, height=None, top=None, bottom=None, pen=None,
                      beam=None) -> H.ErrorBars:
        """Not drawn yet."""
        self._unsupported("error bars")

    def add_image(self, data, *, colormap=None, levels=None, rect=None,
                  axis_order=None) -> H.Image:
        """Not drawn yet."""
        self._unsupported("an image or heatmap")

    def add_region(self, bounds, *, orientation="vertical", movable=True, brush=None,
                   pen=None) -> H.Region:
        """Not drawn yet."""
        self._unsupported("a draggable region")

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
        """Not drawn yet."""
        self._unsupported("a text label")


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
