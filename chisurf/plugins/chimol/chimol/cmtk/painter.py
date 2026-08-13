"""The drawing surface the in-viewport chrome is written against.

Why the chrome needs one
------------------------
:class:`~chimol.renderer.internal_gui.InternalGui` -- the object panel, the
sequence strip, the wizard, the movie transport and the menus -- is a layout and
hit-test engine with a painter bolted to the end of it. The layout half is
arithmetic and has never needed a GUI toolkit; the painting half called
``QPainter`` directly, and that one dependency decided where the whole app could
run.

It is also the app's largest per-frame cost. The chrome is rasterised into a
full-viewport premultiplied RGBA image and uploaded as a texture, which
``wgpu_view`` measured at **9.6 ms of a 21 ms frame** with a quarter of a
million beads on screen. The mitigation is a timer that lets the panel go
*stale* rather than repaint it when it changes -- and it is bypassed entirely
for any scene carrying labels, because labels move with the camera.

So the painting half is expressed here instead, as operations that a triangle
rasteriser can serve directly -- six of them axis-aligned rectangles, plus one
arbitrary filled triangle for the callers a rectangle cannot serve: a diagonal
line, a scatter marker, a projected 3-D face. See
``okf/plugins/chimol-cmtk.md`` for what added the seventh operation and why it
is additive rather than a reversal of the floor described below.

What the interface is, and what it deliberately is not
------------------------------------------------------
Not a ``QPainter`` with the names changed. ``QPainter`` is a *state machine* --
set a pen, set a brush, draw, and hope nothing in between changed either -- and
the chrome used it that way: thirty-one ``setPen`` and twenty ``setBrush`` calls
feeding eighteen ``drawRect``\\ s and fourteen ``drawText``\\ s. Ported literally,
that state would have to be tracked while emitting vertices, and a stale brush
becomes a mis-coloured quad rather than an error.

Every call here carries its own colour, so there is no state to get wrong and
each call maps to a fixed number of quads:

* :meth:`Painter.fill_rect` -- one quad;
* :meth:`Painter.stroke_rect` -- an optional fill plus four edge quads;
* :meth:`Painter.gradient_rect` -- one quad with per-vertex colour;
* :meth:`Painter.text` -- one quad per glyph, from an atlas;
* :meth:`Painter.push_clip` / :meth:`Painter.pop_clip` -- a scissor rectangle;
* :meth:`Painter.fill_triangle` -- three independent corners, flat-shaded.

Colours are plain ``(r, g, b)`` or ``(r, g, b, a)`` tuples of 0-255 ints,
because that is what the chrome's palette constants already are.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, Union

__all__ = [
    "ALIGN_LEFT",
    "ALIGN_RIGHT",
    "ALIGN_HCENTER",
    "ALIGN_VCENTER",
    "ALIGN_CENTER",
    "Colour",
    "Painter",
    "line",
]

#: A colour: ``(r, g, b)`` or ``(r, g, b, a)``, 0-255.
Colour = Union[tuple[int, int, int], tuple[int, int, int, int]]

#: Horizontal alignment within the box passed to :meth:`Painter.text`.
ALIGN_LEFT = 0x01
ALIGN_RIGHT = 0x02
ALIGN_HCENTER = 0x04

#: Vertical alignment. There is no top or bottom: the chrome centres every
#: string in its row, and offering alignments nobody uses would mean a glyph
#: rasteriser that has to implement them.
ALIGN_VCENTER = 0x80

#: The two combined, as the menus and buttons want.
ALIGN_CENTER = ALIGN_HCENTER | ALIGN_VCENTER


class Painter(Protocol):
    """What the chrome needs in order to draw itself.

    Two implementations exist and must agree: the Qt one, which is the
    before-half and the reference, and the GPU one, which emits quads.
    """

    def fill_rect(self, x: float, y: float, w: float, h: float, colour: Colour) -> None:
        """Fill a rectangle. No outline."""
        ...

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
        ...

    def gradient_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        stops: Sequence[Colour],
        edge: Colour | None = None,
    ) -> None:
        """Fill a rectangle with a left-to-right gradient through *stops*.

        One caller: the panel's ``C`` button, whose rainbow is what says the
        button colours things. Evenly spaced -- the palette carries no offsets.
        """
        ...

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
        """Draw *string* aligned inside the box.

        ``bold`` has exactly one caller -- a menu's title row, which is how a
        menu says what it is a menu *of*. It is a parameter rather than painter
        state because state is what made the ``QPainter`` version awkward to
        emit vertices from, and because a glyph atlas has to bake a second face
        for it: a flag that is invisible at the call site is a flag that gets
        baked wrong.
        """
        ...

    def push_clip(self, x: float, y: float, w: float, h: float) -> None:
        """Restrict drawing to a rectangle until :meth:`pop_clip`.

        Menus are the only caller, and they are the reason clipping exists at
        all: a menu taller than its allotted height scrolls inside a fixed box.
        """
        ...

    def pop_clip(self) -> None:
        """Undo the most recent :meth:`push_clip`."""
        ...

    def fill_triangle(
        self,
        p0: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
        colour: Colour,
    ) -> None:
        """Fill a triangle with three independent corners. No outline.

        The one primitive a rectangle cannot serve: a diagonal edge. Every
        other shape a plot needs -- a line segment, a marker -- is one or two
        calls to this, done by :func:`line` and by the callers in ``cmtk``.
        """
        ...

    def text_width(self, string: str) -> float:
        """Advance width of *string*, in pixels."""
        ...

    def line_height(self) -> float:
        """Height of one line of text, in pixels."""
        ...


def line(
    p: "Painter",
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    width: float,
    colour: Colour,
) -> None:
    """Draw a segment of *width* pixels through :meth:`Painter.fill_triangle`.

    Not a :class:`Painter` method. A segment is a thin quad -- two triangles
    -- built once here from the perpendicular offset, rather than asked of
    every implementation separately; that is what keeps a new :class:`Painter`
    backend at seven methods instead of eight, and what keeps this arithmetic
    in one place instead of two copies quietly disagreeing at a shared
    endpoint's width.

    A degenerate segment (``x0 == x1 and y0 == y1``) draws nothing -- there is
    no direction to offset a zero-length line perpendicular to.
    """
    dx = x1 - x0
    dy = y1 - y0
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0.0:
        return
    hw = width * 0.5
    ox = -dy / length * hw
    oy = dx / length * hw
    a = (x0 + ox, y0 + oy)
    b = (x1 + ox, y1 + oy)
    c = (x1 - ox, y1 - oy)
    d = (x0 - ox, y0 - oy)
    p.fill_triangle(a, b, c, colour)
    p.fill_triangle(a, c, d, colour)
