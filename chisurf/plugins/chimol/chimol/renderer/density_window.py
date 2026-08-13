"""The density map's contour controls, drawn inside the viewport.

Why this is not the Qt panel with a new coat of paint
-----------------------------------------------------
The map panel is the first of chimol's docks to move into the 3-D view, and it
is the one that had to move for a second reason: it was reported **slow, and
prone to sticking while a threshold was dragged**. Both problems have the same
cause and the port is where it gets fixed.

A contour level is a *number*, and turning a number into a picture means
marching cubes over the whole grid. The dock ran that on every value change, so
dragging a marker asked for a full isosurface per mouse move — on a
180x180x180 map that is millions of cells per frame, and the drag falls behind
the cursor and stays behind it.

Here the drag does what the reference viewer does: the marker moves every
frame, and the *surface follows at a coarser step* — a throttled re-contour
under a reduced voxel budget, cheap enough to keep up with the mouse — with the
full-quality contour drawn once, on release. A model that does not understand
the ``preview`` keyword gets the old behaviour (marker only, contour on
release), so the window never demands more of its host than the host offers.

What it draws
-------------
The histogram of the map's values with the contour levels standing on it,
because choosing a contour is an act of *looking* at the distribution — a
number typed into a box says nothing about whether it sits on the noise floor
or in the shoulder.

The controls follow the reference viewer's volume panel, translated to the
gestures this chrome has (a press, a drag, a release — no buttons, no
modifier keys):

* one threshold is **selected**, and stays selected after the mouse is
  released — the colour well, the alpha slider and the level readout all act
  on it. The first version bound them to "the marker being dragged, else the
  first one", which made a second contour impossible to recolour at all;
* the colour well opens a **palette drawn in the panel** (hue columns, tint
  to shade rows, a grey row), because the reference viewer's colour well
  opens its system colour editor and this panel also runs in a browser where
  there is none. Picking a colour recolours the selected contour immediately
  — the contour itself is memoised, so only the colours change;
* a marker **dragged off the histogram** is deleted on release (the reference
  viewer's gesture for removing a threshold), except the last one — an empty
  level list would fall back to the opening contour and the map would
  reappear, which reads as a refusal that redraws;
* clicking empty histogram still adds a threshold there, and selects it.

Everything is drawn through :mod:`chimol.renderer.ui.painter`'s six operations,
so this panel runs wherever the chrome runs: the desktop viewport and the
browser, from one implementation.
"""
from __future__ import annotations

import colorsys
import logging
import time

import numpy as np

from .internal_gui import GuiWindow
from .ui.painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER
from .ui.widgets import ColorEdit4, SliderFloat

logger = logging.getLogger(__name__)

__all__ = ["DensityWindow", "MODES"]

#: How a map may be drawn. `surface` and `mesh` share an isosurface and differ
#: in whether it is filled; `solid` is the reference tool's volume rendering —
#: the markers become a colour/opacity transfer function and the map is
#: composited through it as translucent fog.
MODES: tuple[str, ...] = ("surface", "mesh", "solid")

#: Surface-quality presets, ordered cheap to fine. The names wrap the
#: reference tool's rendering options: `coarse` shrinks the voxel budget,
#: `smooth` is its surface_smoothing, `fine` its subdivide_surface on top.
QUALITIES: tuple[str, ...] = ("coarse", "normal", "smooth", "fine")

# Palette, in the same family as the rest of the chrome.
_TEXT = (230, 230, 230)
_DIM = (150, 150, 150)
_HIST = (110, 110, 118, 220)
_AXIS = (90, 90, 96, 200)
_MARKER = (255, 96, 176)
_MARKER_HELD = (255, 200, 90)
_MODE_ON = (66, 150, 250, 220)
_MODE_OFF = (60, 60, 66, 220)

#: Row height and margin. Tight on purpose: this panel sits *over* the map it
#: describes, and the space it takes is map. The header used to be two lines of
#: text and three 22-pixel button rows -- 108 fixed pixels of a 242-pixel body,
#: before the histogram, which is the only part anybody drags.
_ROW = 13.0
_PAD = 5.0
#: The gap between two control rows.
_GAP = 3.0
#: Room left at the bottom-right for the window's resize grip.
_GRIP_ROOM = 16.0
#: How near a marker a press has to land, in pixels.
_GRAB = 6.0

#: Seconds between preview contours while a marker is dragged. Mouse moves
#: arrive faster than a contour can be cut; anything between two previews only
#: moves the marker.
_PREVIEW_INTERVAL = 0.05
#: A preview slower than this (seconds) stops the live surface for the rest of
#: the drag — on such a map the marker-only drag is the responsive behaviour,
#: and the release still contours in full.
_PREVIEW_TOO_SLOW = 0.25

#: How far (pixels) a marker must be dragged past the histogram's edge before
#: releasing it deletes the level. Small enough to be discoverable, large
#: enough that overshooting a drag to the minimum does not eat the contour.
_DELETE_MARGIN = 18.0


def _build_palette() -> list[list[tuple[int, int, int]]]:
    """Build the colour well's palette: hue columns, tint-to-shade rows, greys.

    Computed rather than listed so the well offers the whole wheel evenly —
    the reference viewer's well opens a full colour editor, and a hand-picked
    handful of favourites is what made the old control a dead end: five
    presets indexed by marker number, so pressing the well repeatedly changed
    nothing.
    """
    columns = 12
    rows: list[list[tuple[int, int, int]]] = []
    for saturation, value in ((0.32, 0.98), (0.85, 0.95), (0.95, 0.68), (0.95, 0.42)):
        row = []
        for column in range(columns):
            r, g, b = colorsys.hsv_to_rgb(column / columns, saturation, value)
            row.append((int(round(r * 255)), int(round(g * 255)), int(round(b * 255))))
        rows.append(row)
    greys = [
        (v, v, v)
        for v in (int(round(255 * i / (columns - 1))) for i in range(columns))
    ]
    rows.append(greys)
    return rows


_PALETTE = _build_palette()


class DensityWindow:
    """Contour controls for the active map, as a viewport window.

    Parameters
    ----------
    model : VolumeViewModel
        The same view model the Qt dock used -- it already exposes the
        histogram, the value range and the levels, and nothing about it is
        Qt-specific.
    on_change : callable, optional
        Called when the levels have actually changed and the map needs
        re-contouring. Deliberately **not** called during a drag.
    """

    def __init__(self, model, on_change=None) -> None:
        self.model = model
        self.on_change = on_change
        self._held: int | None = None
        self._pending: float | None = None
        self._last_preview = 0.0
        self._preview_live = True
        self._plot = None          # the histogram's rectangle, set while drawing
        self._mode_rects: list[tuple[object, str]] = []
        self._quality_rects: list[tuple[object, str]] = []
        self._alpha_slider = SliderFloat("Alpha", 0.0, 1.0, value=1.0, fmt="%.2f")
        # No label. The painter does not clip text, and "Color" in a 48 px box
        # ran straight into the alpha slider beside it -- the header read
        # "ColorAlpha: 1.00". A swatch next to a slider called Alpha needs no
        # word, and the tooltip says what it does for anyone unsure.
        self._color_swatch = ColorEdit4("")
        self._alpha_box: _Box | None = None
        self._color_box: _Box | None = None
        #: The threshold the colour well, alpha slider and level readout act
        #: on. Persists across releases -- the reference viewer keeps a
        #: selected threshold, and without one a second contour can never be
        #: recoloured.
        self._selected = 0
        self._picker_open = False
        self._picker_box: _Box | None = None
        self._picker_cells: list[tuple[_Box, tuple[int, int, int]]] = []
        #: The per-map eye (show/hide) and close (unload) buttons, laid out
        #: on the header line while drawing.
        self._eye_box: _Box | None = None
        self._close_box: _Box | None = None
        #: Set while a held marker sits past the histogram's edge; releasing
        #: there deletes the level.
        self._delete_armed = False

    # ------------------------------------------------------------------ #
    # The window
    # ------------------------------------------------------------------ #
    def window(self, **kwargs) -> GuiWindow:
        """Return a :class:`GuiWindow` wired to this panel."""
        # Smaller by default: the panel floats over the map it describes, and
        # the histogram -- the only part anybody drags -- keeps the remainder,
        # about 70 px. The resize grip is there for whoever wants it larger.
        options = dict(
            key="density", title="Density", x=24.0, y=90.0, w=300.0, h=185.0,
        )
        options.update(kwargs)
        options.setdefault("on_tooltip", self.tooltip)
        return GuiWindow(
            body=self.draw,
            on_press=self.press,
            on_drag=self.drag,
            on_release=self.release,
            **options,
        )

    # ------------------------------------------------------------------ #
    # The hover tooltip: what each control does, in words
    # ------------------------------------------------------------------ #
    def tooltip(self, x: float, y: float, rect) -> str | None:
        """The tooltip for the control under the cursor, or ``None``."""
        if self._eye_box is not None and self._eye_box.contains(x, y):
            return "show or hide this map in the 3-D view"
        if self._close_box is not None and self._close_box.contains(x, y):
            return "unload this map (the window stays; the map goes)"
        for box, mode in self._mode_rects:
            if box.contains(x, y):
                return {
                    "surface": "a filled contour at each level",
                    "mesh": "the same contour as a wire net (grid-plane edges)",
                    "solid": "translucent fog: the levels become a colour and "
                             "opacity ramp through the data",
                }.get(mode)
        for box, quality in self._quality_rects:
            if box.contains(x, y):
                return {
                    "coarse": "quarter voxel budget: fastest, roughest",
                    "normal": "the raw contour",
                    "smooth": "relax the staircase and noise "
                              "(surface smoothing)",
                    "fine": "subdivide each triangle, then smooth: "
                            "finest, slowest",
                }.get(quality)
        if self._color_box is not None and self._color_box.contains(x, y):
            return "colour of the selected level; opens a palette"
        if self._alpha_box is not None and self._alpha_box.contains(x, y):
            return "opacity of the selected level"
        if self._plot is not None and self._plot.contains(x, y):
            return ("the map's value histogram: drag a marker to move its "
                    "level, click empty space to add one, drag a marker off "
                    "the plot to delete it")
        return None

    # ------------------------------------------------------------------ #
    # Drawing
    # ------------------------------------------------------------------ #
    def draw(self, p, rect) -> None:
        """Paint the summary, the mode buttons, histogram and color/alpha controls."""
        grid = self.model._grid()
        if grid is None:
            p.text(rect.x + _PAD, rect.y + _PAD, rect.w - 2 * _PAD, _ROW,
                   ALIGN_VCENTER | ALIGN_LEFT,
                   "No map loaded.  load_map file.mrc", _DIM)
            self._plot = None
            self._mode_rects = []
            self._quality_rects = []
            self._eye_box = None
            self._close_box = None
            return

        low, high = self.model.value_range()
        y = rect.y + _PAD
        shape = grid.shape
        # The map's own controls, right-aligned on the header line: the eye
        # shows or hides the map object, the x unloads it. Per map, not per
        # window -- closing the window leaves the map; this closes the map.
        button_w = _ROW + 4.0
        close_box = _Box(rect.x + rect.w - _PAD - button_w, y, button_w, _ROW)
        eye_box = _Box(close_box.x - 2.0 - button_w, y, button_w, _ROW)
        shown = True
        try:
            shown = bool(self.model.map_visible())
        except AttributeError:
            pass
        p.fill_rect(eye_box.x, eye_box.y, eye_box.w, eye_box.h,
                    _MODE_ON if shown else _MODE_OFF)
        p.text(eye_box.x, eye_box.y, eye_box.w, eye_box.h, ALIGN_CENTER,
               "o" if shown else "-", _TEXT)
        p.fill_rect(close_box.x, close_box.y, close_box.w, close_box.h,
                    _MODE_OFF)
        p.text(close_box.x, close_box.y, close_box.w, close_box.h,
               ALIGN_CENTER, "x", _TEXT)
        self._eye_box, self._close_box = eye_box, close_box

        # One line, not two: the name, the shape and the range are one fact
        # about the map. But the painter does **not** clip text to the width it
        # is given, so "fits" has to be arranged rather than assumed -- drawn
        # full-width the name ran under the range and the two read as one
        # string of nonsense ("EMD-3061.map 27 180x180x180o" in a screenshot).
        #
        # `x`, not `×`: the baked chrome atlas has no multiplication sign, and
        # a glyph it does not have draws as nothing -- the dimensions read as
        # "28 28 28".
        try:
            title = str(self.model.map_title() or grid.name)
        except AttributeError:
            title = str(grid.name)
        size = f"{shape[0]}x{shape[1]}x{shape[2]}"
        right = f"{low:.3g} … {high:.3g}"
        right_w = p.text_width(right) + _PAD
        left_w = max(rect.w - 3 * _PAD - 2 * button_w - right_w, 40.0)

        # Shed the least useful part first: the file name in brackets, which
        # `map_title` adds only when it differs from the object's name. Then
        # elide the name itself, and only then the size.
        candidates = [f"{title}  {size}"]
        if "  (" in title:
            candidates.append(f"{title.split('  (')[0]}  {size}")
        left = candidates[-1]
        for candidate in candidates:
            if p.text_width(candidate) <= left_w:
                left = candidate
                break
        else:
            stem = left[: -len(size) - 2] if left.endswith(size) else left
            while len(stem) > 4 and p.text_width(f"{stem[:-1]}…  {size}") > left_w:
                stem = stem[:-1]
            left = f"{stem[:-1]}…  {size}" if len(stem) > 4 else size

        p.text(rect.x + _PAD, y, left_w, _ROW,
               ALIGN_VCENTER | ALIGN_LEFT, left, _TEXT)
        p.text(rect.x + _PAD, y,
               rect.w - 3 * _PAD - 2 * button_w - 2.0, _ROW,
               ALIGN_VCENTER | ALIGN_RIGHT, right, _DIM)
        y += _ROW + _GAP

        # The levels can change under the panel (a command, a new map), so the
        # selection is clamped where everything that uses it starts.
        count = len(self.model.levels)
        if count and self._selected >= count:
            self._selected = count - 1

        y = self._draw_modes(p, rect, y)
        y = self._draw_quality(p, rect, y)
        y = self._draw_color_alpha_controls(p, rect, y)
        self._draw_histogram(p, rect, y, low, high)
        if self._picker_open:
            self._draw_picker(p, rect, y)
        else:
            self._picker_box = None
            self._picker_cells = []

    def _draw_modes(self, p, rect, y: float) -> float:
        """Draw the surface / mesh / voxel buttons; returns the next free y."""
        self._mode_rects = []
        current = self.model.display_mode()
        width = (rect.w - 2 * _PAD) / len(MODES)
        for index, mode in enumerate(MODES):
            x = rect.x + _PAD + index * width
            box = _Box(x, y, width - 2.0, _ROW)
            p.fill_rect(box.x, box.y, box.w, box.h,
                        _MODE_ON if mode == current else _MODE_OFF)
            p.text(box.x, box.y, box.w, box.h, ALIGN_CENTER, mode, _TEXT)
            self._mode_rects.append((box, mode))
        return y + _ROW + _GAP

    def _draw_quality(self, p, rect, y: float) -> float:
        """Draw the coarse / normal / smooth / fine buttons; returns the next free y.

        The reference tool buries these as rendering options; a row of named
        presets is what a panel this size can carry, and the option values
        behind the names are exactly its defaults.
        """
        self._quality_rects = []
        current = "normal"
        try:
            current = self.model.display_quality()
        except Exception:
            logger.debug("density window: no quality to read", exc_info=True)
        width = (rect.w - 2 * _PAD) / len(QUALITIES)
        for index, quality in enumerate(QUALITIES):
            x = rect.x + _PAD + index * width
            box = _Box(x, y, width - 2.0, _ROW)
            p.fill_rect(box.x, box.y, box.w, box.h,
                        _MODE_ON if quality == current else _MODE_OFF)
            p.text(box.x, box.y, box.w, box.h, ALIGN_CENTER, quality, _TEXT)
            self._quality_rects.append((box, quality))
        return y + _ROW + _GAP

    def _draw_color_alpha_controls(self, p, rect, y: float) -> float:
        """Color swatch and alpha slider, both acting on the selected level."""
        levels = self.model.levels
        if levels and 0 <= self._selected < len(levels):
            entry = levels[self._selected]
            c = entry.get("color", (0.5, 0.7, 1.0, 1.0))
            if isinstance(c, (list, tuple)) and len(c) >= 4:
                alpha_val = float(c[3])
                self._color_swatch.color = self._color_swatch._parse_color(c)
            else:
                alpha_val = 1.0
            self._alpha_slider.value = alpha_val

        # Swatch on left, slider on right. The swatch is square and needs no
        # more than its own height plus a little air; the rest is the slider's,
        # which is the control anyone actually drags.
        swatch_w = _ROW + 8.0
        slider_w = rect.w - 3 * _PAD - swatch_w
        swatch_x = rect.x + _PAD
        slider_x = swatch_x + swatch_w + _PAD

        self._color_box = _Box(swatch_x, y, swatch_w, _ROW)
        self._color_swatch.draw(p, swatch_x, y, swatch_w, _ROW)

        self._alpha_box = _Box(slider_x, y, slider_w, _ROW)
        self._alpha_slider.draw(p, slider_x, y, slider_w, _ROW)

        return y + _ROW + _GAP

    def _draw_picker(self, p, rect, top: float) -> None:
        """Draw the colour well's palette over the histogram while it is open.

        Cells are laid out here and remembered, so :meth:`press` hit-tests the
        rectangles that were actually painted rather than a second copy of the
        layout arithmetic.
        """
        columns = len(_PALETTE[0])
        cell_w = (rect.w - 2 * _PAD - 2.0) / columns
        # Clamped into the body: on the compact panel a fixed cell height ran
        # the palette past the histogram into the footer, where the click
        # meant to *dismiss* it landed on a grey cell and recoloured instead.
        room = max(rect.y + rect.h - _ROW - 2.0 - top - 2.0, 20.0)
        cell_h = min(15.0, room / len(_PALETTE))
        box = _Box(
            rect.x + _PAD, top,
            columns * cell_w + 2.0, len(_PALETTE) * cell_h + 2.0,
        )
        self._picker_box = box
        self._picker_cells = []
        p.fill_rect(box.x - 1.0, box.y - 1.0, box.w + 2.0, box.h + 2.0,
                    (30, 30, 34, 250))
        for row_index, row in enumerate(_PALETTE):
            for column, rgb in enumerate(row):
                cell = _Box(
                    box.x + 1.0 + column * cell_w,
                    box.y + 1.0 + row_index * cell_h,
                    cell_w - 1.0, cell_h - 1.0,
                )
                p.fill_rect(cell.x, cell.y, cell.w, cell.h, rgb + (255,))
                self._picker_cells.append((cell, rgb))

    def _draw_histogram(self, p, rect, top: float, low: float, high: float) -> None:
        """Draw the value distribution (log scale like Chimera) with a marker per level."""
        plot = _Box(
            rect.x + _PAD, top,
            max(rect.w - 2 * _PAD, 1.0),
            max(rect.y + rect.h - top - _PAD - _ROW, 1.0),
        )
        self._plot = plot
        p.fill_rect(plot.x, plot.y + plot.h, plot.w, 1.0, _AXIS)

        data = self.model.level_histogram_data()
        if data is not None:
            counts, _edges = data
            counts = np.asarray(counts, dtype=float)
            if counts.size and counts.max() > 0:
                # Log-scale heights (Chimera style) so background counts don't squash signal bins
                log_counts = np.log10(counts + 1.0)
                max_log = log_counts.max()
                if max_log > 0:
                    columns = int(max(plot.w, 1))
                    idx = np.linspace(0, counts.size - 1, columns).astype(int)
                    tall = log_counts[idx] / max_log
                    for column in range(columns):
                        height = float(tall[column]) * plot.h
                        if height <= 0.0:
                            continue
                        p.fill_rect(plot.x + column, plot.y + plot.h - height,
                                    1.0, height, _HIST)

        span = float(high - low) or 1.0
        for index, entry in enumerate(self.model.levels):
            try:
                level = float(entry.get("level"))
            except (TypeError, ValueError):
                continue
            if index == self._held and self._pending is not None:
                level = self._pending
            x = plot.x + (level - low) / span * plot.w
            raw_c = entry.get("color", (0.26, 0.59, 0.98, 1.0))
            if isinstance(raw_c, (list, tuple)) and len(raw_c) >= 3:
                marker_c = tuple(int(round(float(v) * (255 if float(v) <= 1.0 else 1))) for v in raw_c[:3]) + (240,)
            else:
                marker_c = _MARKER
            if index == self._held:
                marker_c = _MARKER_HELD

            # Marker line + top handle box (Chimera style). The selected one
            # gets the gold handle so what the colour well and alpha slider
            # will act on is visible at a glance.
            handle = _MARKER_HELD if index == self._selected else (255, 255, 255, 255)
            p.fill_rect(x - 1.0, plot.y, 2.0, plot.h, marker_c)
            p.stroke_rect(x - 4.0, plot.y, 8.0, 6.0, handle, marker_c)

        if self._delete_armed:
            text = "release to delete this level"
        elif self._held is not None:
            text = f"level {self._level_of(self._held):.4g}"
        else:
            selected = self._level_of(self._selected) if self.model.levels else float("nan")
            # ASCII separators: the middot is not in the chrome atlas and a
            # glyph the atlas lacks draws as nothing. Short enough to fit the
            # default width -- "click adds" was clipped by the frame edge.
            text = (
                f"level {selected:.4g}   drag off deletes, click adds"
                if selected == selected  # not NaN
                else f"min {low:.3g}   click adds a level   max {high:.3g}"
            )
        # The last line stops short of the corner: the window's resize grip
        # sits there and text run under it reads as clipped.
        p.text(rect.x + _PAD, rect.y + rect.h - _ROW - 2.0,
               rect.w - 2 * _PAD - _GRIP_ROOM, _ROW,
               ALIGN_VCENTER | ALIGN_LEFT, text, _DIM)

    # ------------------------------------------------------------------ #
    # Input
    # ------------------------------------------------------------------ #
    def press(self, x: float, y: float, rect) -> bool:
        """Take a marker, switch mode, pick a colour, or add a level.

        Returns True to start a body drag. While the palette is open it takes
        the press first: a cell recolours the selected level, anywhere else
        closes it — either way the click is spent, so a stray dismiss cannot
        also move a marker.
        """
        if self._picker_open:
            self._picker_open = False
            for cell, rgb in self._picker_cells:
                if cell.contains(x, y):
                    self._apply_color(rgb)
                    break
            return False

        if self._eye_box is not None and self._eye_box.contains(x, y):
            try:
                self.model.set_map_visible(not self.model.map_visible())
            except AttributeError:
                logger.debug("density window: model has no visibility toggle")
            self._changed()
            return False

        if self._close_box is not None and self._close_box.contains(x, y):
            try:
                self.model.close_map()
            except AttributeError:
                logger.debug("density window: model cannot close the map")
            self._changed()
            return False

        for box, mode in self._mode_rects:
            if box.contains(x, y):
                self.model.set_display_mode(mode)
                self._changed()
                return False

        for box, quality in self._quality_rects:
            if box.contains(x, y):
                try:
                    self.model.set_display_quality(quality)
                except AttributeError:
                    logger.debug("density window: model has no quality setter")
                self._changed()
                return False

        if self._alpha_box and self._alpha_box.contains(x, y):
            if self._alpha_slider.press(x, y, self._alpha_box.x, self._alpha_box.y, self._alpha_box.w, self._alpha_box.h):
                self._apply_alpha(self._alpha_slider.value, rebuild=False)
                return True

        if self._color_box and self._color_box.contains(x, y):
            if self._color_swatch.press(x, y, self._color_box.x, self._color_box.y, self._color_box.w, self._color_box.h):
                self._picker_open = True
                return False

        plot = self._plot
        if plot is None or not plot.contains(x, y):
            return False

        found = self._marker_at(x)
        if found is not None:
            self._selected = found
            self._held = found
            self._pending = None
            self._delete_armed = False
            # A new drag gets a fresh chance at a live surface; a map that
            # proved too slow last time will disable it again after one try.
            self._preview_live = True
            return True
        else:
            # Click on histogram plot to add a new level (Chimera style)
            low, high = self.model.value_range()
            span = float(high - low) or 1.0
            fraction = (x - plot.x) / max(plot.w, 1.0)
            new_level = float(low + min(max(fraction, 0.0), 1.0) * span)
            levels = [dict(e) for e in self.model.levels]
            levels.append({"level": new_level, "color": [0.26, 0.59, 0.98, 1.0], "style": "surface"})
            self.model.set_levels(levels, rebuild=True)
            self._selected = len(levels) - 1
            self._held = self._selected
            self._delete_armed = False
            self._changed()
            return True

    def drag(self, x: float, y: float, rect) -> bool:
        """Move the held marker or alpha slider; the surface follows at preview quality."""
        if self._alpha_slider._held and self._alpha_box:
            if self._alpha_slider.drag(x, y, self._alpha_box.x, self._alpha_box.y, self._alpha_box.w, self._alpha_box.h):
                self._apply_alpha(self._alpha_slider.value, rebuild=False)
                return True
            return True

        if self._held is None or self._plot is None:
            return False
        plot = self._plot
        # Past the histogram's edge the drag stops meaning "move" and starts
        # meaning "remove" -- the reference viewer's delete gesture. The level
        # itself stops updating so an aborted delete leaves it where it was.
        outside = (
            x < plot.x - _DELETE_MARGIN or x > plot.x + plot.w + _DELETE_MARGIN
            or y < plot.y - _DELETE_MARGIN or y > plot.y + plot.h + _DELETE_MARGIN
        )
        if outside and len(self.model.levels) > 1:
            self._delete_armed = True
            return True
        self._delete_armed = False
        low, high = self.model.value_range()
        span = float(high - low) or 1.0
        fraction = (x - plot.x) / max(plot.w, 1.0)
        self._pending = float(low + min(max(fraction, 0.0), 1.0) * span)
        self._apply_pending(rebuild=False)
        self._preview_contour()
        return True

    def _preview_contour(self) -> None:
        """Let the surface follow the drag, at preview quality, when it can.

        Throttled, timed, and self-disabling: a map whose preview contour
        cannot keep up stops being asked for one, and the drag falls back to
        marker-only with the full contour on release. A model without the
        ``preview`` keyword (an older host, a test double) takes the fallback
        immediately.
        """
        if not self._preview_live or self._held is None or self._pending is None:
            return
        now = time.monotonic()
        if now - self._last_preview < _PREVIEW_INTERVAL:
            return
        self._last_preview = now
        levels = [dict(entry) for entry in self.model.levels]
        if not (0 <= self._held < len(levels)):
            return
        levels[self._held]["level"] = self._pending
        started = time.perf_counter()
        try:
            self.model.set_levels(levels, rebuild=True, preview=True)
        except TypeError:
            self._preview_live = False
            return
        if time.perf_counter() - started > _PREVIEW_TOO_SLOW:
            self._preview_live = False

    def release(self) -> None:
        """Re-contour once, delete an armed marker, or just settle the alpha."""
        if self._alpha_slider._held:
            self._alpha_slider.release()
            self._apply_alpha(self._alpha_slider.value, rebuild=True)
        if self._held is not None and self._delete_armed:
            self._delete_held()
        elif self._held is not None and self._pending is not None:
            self._apply_pending(rebuild=True)
        self._held = None
        self._pending = None
        self._delete_armed = False

    def _delete_held(self) -> None:
        """Remove the level whose marker was dragged off the histogram."""
        levels = [dict(entry) for entry in self.model.levels]
        if not (0 <= self._held < len(levels)) or len(levels) <= 1:
            return
        del levels[self._held]
        self.model.set_levels(levels, rebuild=True)
        self._selected = min(self._selected, len(levels) - 1)
        self._changed()

    def _apply_color(self, rgb: tuple[int, int, int]) -> None:
        """Recolour the selected level from the palette, keeping its alpha."""
        levels = [dict(entry) for entry in self.model.levels]
        if not (0 <= self._selected < len(levels)):
            return
        current = list(levels[self._selected].get("color", [0.5, 0.7, 1.0, 1.0]))
        alpha = float(current[3]) if len(current) >= 4 else 1.0
        levels[self._selected]["color"] = [
            rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, alpha,
        ]
        # The contour for this level is memoised, so the rebuild only recolours.
        self.model.set_levels(levels, rebuild=True)
        self._changed()

    def _apply_alpha(self, alpha_val: float, *, rebuild: bool = False) -> None:
        """Update the alpha component of the selected level."""
        levels = [dict(e) for e in self.model.levels]
        if not (0 <= self._selected < len(levels)):
            return
        color = list(levels[self._selected].get("color", [0.5, 0.7, 1.0, 1.0]))
        if len(color) < 4:
            color = (color + [1.0] * 4)[:4]
        color[3] = float(min(max(alpha_val, 0.0), 1.0))
        levels[self._selected]["color"] = color
        self.model.set_levels(levels, rebuild=rebuild)
        if rebuild:
            self._changed()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _marker_at(self, x: float) -> int | None:
        """Index of the marker within :data:`_GRAB` pixels of ``x``."""
        plot = self._plot
        low, high = self.model.value_range()
        span = float(high - low) or 1.0
        best, best_gap = None, _GRAB
        for index, entry in enumerate(self.model.levels):
            try:
                level = float(entry.get("level"))
            except (TypeError, ValueError):
                continue
            gap = abs(plot.x + (level - low) / span * plot.w - x)
            if gap <= best_gap:
                best, best_gap = index, gap
        return best

    def _level_of(self, index: int | None) -> float:
        if index is None:
            return float("nan")
        if self._pending is not None:
            return self._pending
        try:
            return float(self.model.levels[index].get("level"))
        except Exception:
            return float("nan")

    def _apply_pending(self, *, rebuild: bool) -> None:
        """Write the dragged level back, optionally asking for a redraw."""
        if self._held is None or self._pending is None:
            return
        levels = [dict(entry) for entry in self.model.levels]
        if not (0 <= self._held < len(levels)):
            return
        levels[self._held]["level"] = self._pending
        self.model.set_levels(levels, rebuild=rebuild)
        if rebuild:
            self._changed()

    def _changed(self) -> None:
        if self.on_change is not None:
            try:
                self.on_change()
            except Exception:
                logger.debug("density window: change callback failed", exc_info=True)


class _Box:
    """A rectangle with a ``contains``; the chrome's `Rect` without the import."""

    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.x, self.y, self.w, self.h = float(x), float(y), float(w), float(h)

    def contains(self, x: float, y: float) -> bool:
        return self.x <= x <= self.x + self.w and self.y <= y <= self.y + self.h
