"""Result views of the imaging tools: series plots, an image or movie panel, a vector field.

Each view is drawn from what the model computed -- an empty model draws a message naming the action that
produces the data, never a placeholder curve.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np
from emtk import im, implot
from emtk.view_form import FormState, draw_sections

from chisurf.emtk.image_canvas import ImageCanvas

#: The playback speed field: a spin box as the Qt movie bar had (1 to 120 fps).
FPS_SECTION = {"type": "value", "attr": "fps", "label": "Playback speed", "kind": "int", "style": "spin",
               "minimum": 1, "maximum": 120, "suffix": " fps",
               "description": "Playback speed in frames per second (1 to 120)."}

#: Colormaps the image canvas offers.
COLORMAPS = ("magma", "inferno", "viridis", "gray")


def rgba(colour: Any, default: tuple = (200, 200, 200, 255)) -> tuple:
    """Parse ``"#rrggbb"`` (or a tuple) into an RGBA tuple of 0-255 integers."""
    if isinstance(colour, (tuple, list)) and len(colour) >= 3:
        return (int(colour[0]), int(colour[1]), int(colour[2]), int(colour[3]) if len(colour) > 3 else 255)
    text = str(colour or "").lstrip("#")
    if len(text) == 6:
        try:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16), 255)
        except ValueError:
            pass
    return default


def muted(text: str) -> None:
    """A dimmed message that wraps at the window's right edge instead of running past it."""
    im.push_text_wrap_pos(0.0)
    im.text_disabled(text)
    im.pop_text_wrap_pos()


def _arrays(series: dict) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(series.get("x", ()), dtype=float)
    y = np.asarray(series.get("y", ()), dtype=float)
    n = min(len(x), len(y))
    return x[:n], y[:n]


_MARKERS = {"o": "MARKER_CIRCLE", "d": "MARKER_DIAMOND", "s": "MARKER_SQUARE", "t": "MARKER_UP"}


def draw_series_plot(section: dict, model: Any, owner: Any) -> None:
    """A plot of the model's series (``options.source`` names a method returning a list of dicts).

    A series is ``{"x", "y", "name", "color", "width", "symbol", "symbol_size", "no_line", "style"}``.
    ``options``: ``source``, ``x_label``, ``y_label``, ``log_x``, ``log_y``, ``invert_y``, ``equal``,
    ``legend``, ``empty`` (the message shown while there is nothing to draw).
    """
    options = section.get("options") or {}
    source = str(options.get("source", ""))
    fn = getattr(model, source, None)
    series = list(fn() or []) if callable(fn) else []
    title = str(section.get("title", source))
    rect_name = str(options.get("name", title))
    if not series:
        muted(str(options.get("empty", "Nothing to show yet.")))
        im.set_item_tooltip(str(section.get("description", "")))
        owner.item_rects[rect_name] = im.get_item_rect()
        return
    height = max(120.0, im.get_content_region_avail()[1] - 6.0)
    # A new result brings its own range: refit the axes once when what is drawn changed (a pan or zoom of the old view must not hide it).
    state = owner.__dict__.setdefault("plot_state", {})
    fingerprint = (len(series), tuple((len(e.get("x", ())), float(np.nanmin(e["x"])), float(np.nanmax(e["x"]))) if len(e.get("x", ())) else 0
                                      for e in series[:3]))
    changed = state.get(source) != fingerprint
    state[source] = fingerprint
    if changed:
        implot.set_next_axes_to_fit()
    flags = 0 if options.get("legend") else implot.FLAGS_NO_LEGEND
    if options.get("equal"):
        flags |= implot.FLAGS_EQUAL
    y_flags = implot.AXIS_FLAGS_INVERT if options.get("invert_y") else 0
    if implot.begin_plot(f"##{source}", (-1.0, height), flags):
        implot.setup_axes(str(options.get("x_label", "")), str(options.get("y_label", "")), 0, y_flags)
        if options.get("legend"):
            implot.setup_legend(implot.LOCATION_NORTH_EAST)
        if options.get("y_range"):
            lo, hi = options["y_range"]
            implot.setup_axis_limits(implot.AXIS_Y1, float(lo), float(hi), implot.COND_ALWAYS if changed else implot.COND_ONCE)
        if options.get("log_x"):
            implot.setup_axis_scale(implot.AXIS_X1, implot.SCALE_LOG10)
        if options.get("log_y"):
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
        for entry in series:
            x, y = _arrays(entry)
            if not len(x):
                continue
            colour = rgba(entry.get("color"))
            name = str(entry.get("name", ""))
            if entry.get("no_line") or entry.get("symbol") and not entry.get("width"):
                marker = getattr(implot, _MARKERS.get(str(entry.get("symbol", "o")), "MARKER_CIRCLE"))
                implot.set_next_marker_style(marker, float(entry.get("symbol_size", 6.0)), colour)
                implot.plot_scatter(name, x, y)
                continue
            dash = {"dash": (6.0, 4.0), "dot": (2.0, 3.0)}.get(str(entry.get("style", "")))
            implot.set_next_line_style(colour, float(entry.get("width", 1.5)) + 0.5, dash)
            implot.plot_line(name, x, y)
            if entry.get("symbol"):
                marker = getattr(implot, _MARKERS.get(str(entry["symbol"]), "MARKER_CIRCLE"))
                implot.set_next_marker_style(marker, float(entry.get("symbol_size", 6.0)), colour)
                implot.plot_scatter(f"##{name}_points", x, y)  # no second legend entry
        plot_rect = (*implot.get_plot_pos(), *implot.get_plot_size())
        implot.end_plot()
        owner.item_rects[rect_name] = plot_rect
    im.set_item_tooltip(str(section.get("description", "")))


class ImagePanel:
    """An image (or a frame stack with play controls) with colormap, levels and point markers.

    Parameters
    ----------
    key : str
        Unique widget id.
    movie : bool
        Draw Play / Loop / Stop / fps controls for a ``(frame, y, x)`` stack, as the Qt image dock does.
    fps : int
        Initial playback speed.
    clock : callable
        Seconds; replaceable by a test.
    """

    def __init__(self, key: str, *, movie: bool = False, fps: int = 10,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.key = key
        self.movie = bool(movie)
        self.fps = int(fps)
        self.loop = True
        self.playing = False
        self.clock = clock
        self._last = 0.0
        self.canvas = ImageCanvas(key)
        self.rects: dict[str, tuple] = {}
        self.form = FormState()

    @property
    def frame(self) -> int:
        return int(self.canvas.z)

    def reset(self) -> None:
        """Forget the view (a new image replaces the old one)."""
        self.playing = False
        self.canvas.reset()

    def stop(self) -> None:
        self.playing = False
        self.canvas.z = 0

    def toggle_play(self) -> None:
        self.playing = not self.playing
        self._last = self.clock()

    def _advance(self, n_frames: int) -> None:
        if not self.playing or n_frames < 2:
            self.playing = self.playing and n_frames >= 2
            return
        now = self.clock()
        step = int((now - self._last) * self.fps)
        if step < 1:
            return
        self._last += step / max(self.fps, 1)
        z = int(self.canvas.z) + step
        if z >= n_frames:
            if self.loop:
                z %= n_frames
            else:
                z, self.playing = n_frames - 1, False
        self.canvas.z = z

    def draw(self, array: Any, model: Any, owner: Any, *, markers: Any = (), empty: str = "",
             description: str = "", colormap_attr: str = "") -> None:
        """Draw *array* (``None`` draws *empty*), keeping ``model.<colormap_attr>`` in step with the combo."""
        if array is None:
            muted(empty or "No image yet.")
            im.set_item_tooltip(description)
            return
        source = np.asarray(array)
        stack = source.ndim == 3
        if colormap_attr:
            wanted = str(getattr(model, colormap_attr, self.canvas.colormap))
            if wanted in COLORMAPS:
                self.canvas.colormap = wanted
        if self.movie:
            n = int(source.shape[0]) if stack else 1
            self._advance(n)
            im.begin_disabled(not stack)
            if im.button(f"{'Pause' if self.playing else 'Play'}##{self.key}_play"):
                self.toggle_play()
            im.set_item_tooltip("Play the frame stack; it stops at the last frame unless Loop is on.")
            self.rects["play"] = im.get_item_rect()
            im.same_line()
            _, self.loop = im.checkbox(f"Loop##{self.key}_loop", self.loop)
            im.set_item_tooltip("Wrap around to the first frame at the end of the stack.")
            self.rects["loop"] = im.get_item_rect()
            im.same_line()
            if im.button(f"Stop##{self.key}_stop"):
                self.stop()
            im.set_item_tooltip("Stop playback and return to the first frame.")
            self.rects["stop"] = im.get_item_rect()
            im.end_disabled()
            im.begin_disabled(not stack)
            draw_sections([FPS_SECTION], self, self.form)
            self.rects["fps"] = self.form.rects.get("fps", (0, 0, 0, 0))
            im.end_disabled()
        self.canvas.draw(source, markers=markers, pick_enabled=False, analysis_editable=False)
        if colormap_attr and self.canvas.colormap != getattr(model, colormap_attr, self.canvas.colormap):
            setattr(model, colormap_attr, self.canvas.colormap)
        self.rects["image"] = tuple(self.canvas.rect or (0, 0, 0, 0))
        owner.item_rects[f"{self.key}.image"] = self.rects["image"]


def arrow_colour(magnitude: float, largest: float) -> tuple:
    """Cool for the slowest arrow, warm for the fastest (the Qt quiver's ramp)."""
    fraction = 0.0 if largest <= 0 else min(1.0, magnitude / largest)
    return (int(255 * min(1.0, 0.35 + 0.65 * fraction)), int(200 * (1.0 - 0.75 * fraction)), 64, 255)


def quiver_segments(vectors: list, scale: float) -> list[tuple]:
    """``(x0, y0, x1, y1, magnitude)`` per drawable arrow (zero-length and non-finite ones are skipped)."""
    out = []
    for v in vectors:
        magnitude = float(np.hypot(v.get("dx", 0.0), v.get("dy", 0.0)))
        if not np.isfinite(magnitude) or magnitude <= 0.0:
            continue
        x, y = float(v["x"]), float(v["y"])
        out.append((x, y, x + float(v["dx"]) * scale, y + float(v["dy"]) * scale, magnitude))
    return out


class QuiverPanel:
    """A vector field over an image: one arrow per vector, coloured by length, in the image's units."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.canvas = ImageCanvas(key)
        self.canvas.colormap = "gray"
        self.caption = ""
        self.n_drawn = 0

    def draw(self, section: dict, model: Any, owner: Any) -> None:
        options = section.get("options") or {}

        def call(name: str) -> Any:
            fn = getattr(model, str(options.get(name, "")), None)
            return fn() if callable(fn) else None

        image, vectors, extent = call("image_source"), call("vectors_source") or [], call("extent_source")
        if image is None:
            muted(str(options.get("empty", "No field yet.")))
            im.set_item_tooltip(str(section.get("description", "")))
            self.caption, self.n_drawn = "", 0
            return
        scale = float(getattr(model, str(options.get("scale_attr", "")), 1.0) or 1.0)
        segments = quiver_segments(list(vectors), scale)
        speeds = [s[4] for s in segments]
        largest = max(speeds) if speeds else 0.0
        data = np.asarray(image, dtype=float)
        ny, nx = data.shape[-2:]
        x0, x1, y0, y1 = (float(v) for v in extent) if extent and len(extent) == 4 else (0.0, nx, 0.0, ny)
        height = max(140.0, im.get_content_region_avail()[1] - 28.0)
        flags = implot.FLAGS_EQUAL | implot.FLAGS_NO_LEGEND
        if implot.begin_plot(f"##{self.key}", (-1.0, height), flags):
            implot.setup_axes(str(options.get("x_label", "x")), str(options.get("y_label", "y")), 0,
                              implot.AXIS_FLAGS_INVERT)
            implot.setup_axes_limits(x0, x1, y0, y1, implot.COND_ONCE)
            implot.plot_image("##image", self.canvas.texture(data), (x0, y0), (x1, y1),
                              uv0=(0, 1), uv1=(1, 0))
            head = 0.25
            for xa, ya, xb, yb, magnitude in segments:
                colour = arrow_colour(magnitude, largest)
                dx, dy = xb - xa, yb - ya
                length = float(np.hypot(dx, dy))
                ux, uy = dx / length, dy / length
                hl = head * length
                px, py = -uy, ux
                xs = [xa, xb, xb - hl * ux + 0.5 * hl * px, xb, xb - hl * ux - 0.5 * hl * px]
                ys = [ya, yb, yb - hl * uy + 0.5 * hl * py, yb, yb - hl * uy - 0.5 * hl * py]
                implot.set_next_line_style(colour, 2.0)
                implot.plot_line(f"##arrow{xa:.3g}_{ya:.3g}", np.asarray(xs), np.asarray(ys))
            plot_rect = (*implot.get_plot_pos(), *implot.get_plot_size())
            implot.end_plot()
            owner.item_rects[str(section.get("title", self.key))] = plot_rect
        im.set_item_tooltip(str(section.get("description", "")))
        self.n_drawn = len(segments)
        self.caption = self._caption(len(segments), len(vectors), speeds, scale, str(options.get("units", "")))
        muted(self.caption)

    @staticmethod
    def _caption(drawn: int, total: int, speeds: list, scale: float, units: str) -> str:
        """What the Qt section said under the field: how many arrows, how fast, at what display scale."""
        if not drawn:
            return "No arrows \u2014 nothing passed the quality threshold, or the field is empty."
        unit = f" {units}" if units else ""
        parts = [f"{drawn} of {total} arrows", f"fastest {max(speeds):.3g}{unit}"]
        if abs(scale - 1.0) > 1e-9:
            parts.append(f"drawn at {scale:g}x (display only)")
        return " \u00b7 ".join(parts)
