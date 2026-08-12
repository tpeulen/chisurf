"""Draw the chrome as quads instead of rasterising it on the CPU.

This is the other implementation of :class:`~.painter.Painter`. It draws
nothing: it *appends*, building one interleaved vertex array that
``renderer/wgsl/ui.wgsl`` turns into the panel, the strip, the menus and the
transport in a single draw call.

Why that is worth doing is measured, not assumed. ``wgpu_view`` records the
``QPainter`` path at **9.6 ms of a 21 ms frame** with a quarter-million beads on
screen -- so the chrome was mitigated by a *timer* that lets the panel go stale
rather than repaint when it changes, and that mitigation is bypassed entirely
for any scene carrying labels, because labels move with the camera. A frame of
chrome is a few hundred rectangles and a few thousand glyphs; as vertices that
is kilobytes and no rasterisation.

Vertex format
-------------
Six vertices per quad -- two triangles, no index buffer, because the chrome is
rebuilt every frame and an index buffer would be another allocation to keep in
step for no reuse. Each vertex is 12 floats::

    position  x, y            pixels, y-down from the top left
    uv        u, v            atlas texels
    colour    r, g, b, a      0-1, straight alpha; the shader premultiplies
    box       x0, y0, x1, y1  the clip rectangle in pixels

The clip rectangle rides on the vertex rather than being a scissor, so the
whole chrome stays one draw call.

A rectangle points at the atlas's opaque block, so there is no second pipeline
and no "is this text" branch: the difference between a panel background and a
letter is which texels the quad samples.
"""
from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .font import Atlas, load_atlas
from .painter import (
    ALIGN_HCENTER,
    ALIGN_RIGHT,
    ALIGN_VCENTER,
    Colour,
)

__all__ = ["QuadPainter", "FLOATS_PER_VERTEX", "VERTICES_PER_QUAD"]

#: Floats per vertex; see the module docstring.
FLOATS_PER_VERTEX = 12

#: Two triangles.
VERTICES_PER_QUAD = 6

#: The clip rectangle used when nothing is clipping. Large enough to pass any
#: on-screen fragment, and finite so the comparison in the shader stays a
#: comparison rather than a NaN.
_NO_CLIP = (-1.0e6, -1.0e6, 1.0e6, 1.0e6)


def _rgba(colour: Colour) -> tuple[float, float, float, float]:
    """Return *colour* as floats in ``[0, 1]``, with alpha.

    Parameters
    ----------
    colour : tuple
        ``(r, g, b)`` or ``(r, g, b, a)``, 0-255.

    Returns
    -------
    tuple of float
    """
    if len(colour) == 3:
        r, g, b = colour
        a = 255
    else:
        r, g, b, a = colour
    return r / 255.0, g / 255.0, b / 255.0, a / 255.0


class QuadPainter:
    """Accumulate the chrome as an interleaved vertex array.

    Parameters
    ----------
    atlas : Atlas, optional
        The baked font. Loaded from the package by default.
    scale : float, optional
        Device pixels per logical pixel.
    font_scale : float, optional
        Text size, as a multiple of the baked one. The atlas is a bitmap face,
        so this scales the glyph quads and their advance together -- there is
        no second size to bake. It is the *drawing* half of the chrome scale;
        the layout half is ``InternalGui.FONT_PT``, and the two must be given
        the same number or the boxes and the text they hold disagree.
    """

    def __init__(self, atlas: Atlas | None = None, scale: float = 1.0,
                 font_scale: float = 1.0) -> None:
        self._atlas = atlas if atlas is not None else load_atlas()
        self._font_scale = float(font_scale)
        self._data: list[float] = []
        self._clips: list[tuple[float, float, float, float]] = []
        #: Device pixels per logical pixel.
        #:
        #: The panel lays itself out in **logical** pixels -- that is what a
        #: window's coordinates are, and what a mouse event carries -- while the
        #: surface it lands on is in **device** pixels. Applied here, at the one
        #: point where layout becomes geometry, so hit-testing keeps working in
        #: the coordinates the events arrive in.
        #:
        #: Getting this wrong does not look like a scaling bug. On a 2x display
        #: the panel draws at half size in the corner of the window while
        #: ``hit_test`` still answers for where it *should* be, so every click
        #: misses by the ratio and the panel looks inert rather than misplaced.
        self._scale = float(scale)

    # -- output ------------------------------------------------------------

    @property
    def vertex_count(self) -> int:
        """Number of vertices accumulated so far."""
        return len(self._data) // FLOATS_PER_VERTEX

    def vertices(self) -> np.ndarray:
        """Return the interleaved array, ready for upload.

        Returns
        -------
        numpy.ndarray
            ``(n, 12)`` float32, C-contiguous -- the same guarantees
            :mod:`chimol.renderer.pack` makes of geometry, for the same reason:
            a view onto the interpreter's heap can only be handed to a GPU if
            it is already in the layout the GPU expects.
        """
        if not self._data:
            return np.zeros((0, FLOATS_PER_VERTEX), dtype=np.float32)
        return np.ascontiguousarray(
            np.asarray(self._data, dtype=np.float32).reshape(-1, FLOATS_PER_VERTEX)
        )

    def clear(self) -> None:
        """Drop everything accumulated, keeping the loaded atlas."""
        self._data.clear()
        self._clips.clear()

    # -- internals ---------------------------------------------------------

    @property
    def _clip(self) -> tuple[float, float, float, float]:
        """The clip rectangle currently in force."""
        return self._clips[-1] if self._clips else _NO_CLIP

    def _quad(
        self,
        x: float, y: float, w: float, h: float,
        u: float, v: float, uw: float, vh: float,
        corners,
    ) -> None:
        """Append one quad.

        Parameters
        ----------
        x, y, w, h : float
            Destination rectangle, in pixels.
        u, v, uw, vh : float
            Source rectangle, in atlas texels.
        corners : sequence
            Per-corner RGBA, in the order top-left, top-right, bottom-right,
            bottom-left. A single tuple is accepted and used for all four,
            which is every case except the gradient.
        """
        if w <= 0.0 or h <= 0.0:
            return
        scale = self._scale
        cx0, cy0, cx1, cy1 = (value * scale for value in self._clip)
        if isinstance(corners, tuple) and corners and isinstance(corners[0], float):
            corners = (corners,) * 4

        x, y, w, h = x * scale, y * scale, w * scale, h * scale
        tl = (x, y, u, v, *corners[0])
        tr = (x + w, y, u + uw, v, *corners[1])
        br = (x + w, y + h, u + uw, v + vh, *corners[2])
        bl = (x, y + h, u, v + vh, *corners[3])
        for vertex in (tl, tr, br, tl, br, bl):
            self._data.extend(vertex)
            self._data.extend((cx0, cy0, cx1, cy1))

    def _solid(self, x: float, y: float, w: float, h: float, corners) -> None:
        """Append a quad that samples the atlas's opaque block."""
        sx, sy, sw, sh = self._atlas.solid
        # A texel well inside the block, so filtering cannot reach its edge.
        self._quad(x, y, w, h, sx + sw * 0.5, sy + sh * 0.5, 0.0, 0.0, corners)

    # -- the interface -----------------------------------------------------

    def fill_rect(self, x: float, y: float, w: float, h: float, colour: Colour) -> None:
        """Fill a rectangle. No outline."""
        self._solid(x, y, w, h, _rgba(colour))

    def stroke_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        edge: Colour,
        fill: Colour | None = None,
    ) -> None:
        """Draw a one-pixel outline, optionally over a fill."""
        if fill is not None:
            self._solid(x, y, w, h, _rgba(fill))
        line = _rgba(edge)
        self._solid(x, y, w, 1.0, line)
        self._solid(x, y + h - 1.0, w, 1.0, line)
        self._solid(x, y, 1.0, h, line)
        self._solid(x + w - 1.0, y, 1.0, h, line)

    def gradient_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        stops: Sequence[Colour],
        edge: Colour | None = None,
    ) -> None:
        """Fill a rectangle with a left-to-right gradient through *stops*."""
        colours = [_rgba(stop) for stop in stops]
        if len(colours) == 1:
            self._solid(x, y, w, h, colours[0])
        else:
            span = w / (len(colours) - 1)
            for index in range(len(colours) - 1):
                left, right = colours[index], colours[index + 1]
                self._solid(
                    x + index * span, y, span, h,
                    (left, right, right, left),
                )
        if edge is not None:
            line = _rgba(edge)
            self._solid(x, y, w, 1.0, line)
            self._solid(x, y + h - 1.0, w, 1.0, line)
            self._solid(x, y, 1.0, h, line)
            self._solid(x + w - 1.0, y, 1.0, h, line)

    def text(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        align: int,
        string: str,
        colour: Colour,
        bold: bool = False,
    ) -> None:
        """Draw *string* aligned inside the box, one quad per glyph."""
        if not string:
            return
        atlas = self._atlas
        advance = atlas.advance() * self._font_scale
        width = advance * len(string)

        if align & ALIGN_RIGHT:
            pen_x = x + w - width
        elif align & ALIGN_HCENTER:
            pen_x = x + (w - width) * 0.5
        else:
            pen_x = x

        scale = atlas.scale
        shrink = atlas.render_scale * self._font_scale
        cell_w, cell_h = atlas.cell
        # The pen sits a fixed (pad, pad + ascent) inside every cell, so a
        # glyph's quad is the cell placed relative to the baseline. No
        # per-glyph bearing is needed; see the baker.
        baseline = (
            y + h * 0.5 + (atlas.ascent - atlas.cell[1] * 0.5) * shrink
            if align & ALIGN_VCENTER
            else y + atlas.ascent * shrink
        )
        top = baseline - (atlas.ascent + atlas.pad) * shrink
        quad_w, quad_h = cell_w * shrink, cell_h * shrink

        rgba = _rgba(colour)
        for index, char in enumerate(string):
            cell = atlas.cell_of(char, bold=bold)
            if cell is None:
                continue
            cx, cy, cw, ch = cell
            self._quad(
                pen_x + index * advance - atlas.pad * shrink, top,
                quad_w, quad_h,
                cx, cy, cw, ch,
                rgba,
            )

    def push_clip(self, x: float, y: float, w: float, h: float) -> None:
        """Restrict drawing to a rectangle until :meth:`pop_clip`."""
        box = (x, y, x + w, y + h)
        if self._clips:
            px0, py0, px1, py1 = self._clips[-1]
            box = (
                max(box[0], px0), max(box[1], py0),
                min(box[2], px1), min(box[3], py1),
            )
        self._clips.append(box)

    def pop_clip(self) -> None:
        """Undo the most recent :meth:`push_clip`."""
        if self._clips:
            self._clips.pop()

    def text_width(self, string: str) -> float:
        """Advance width of *string*, in pixels."""
        return self._atlas.advance(string) * self._font_scale

    def line_height(self) -> float:
        """Height of one line of text, in pixels."""
        return self._atlas.line_height * self._font_scale
