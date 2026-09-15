"""What is drawn later is drawn on top -- whatever it is drawn with.

The chrome's painter keeps two streams while a frame is built: a rectangle is
one compact record that is expanded to six vertices at the end, and a triangle
is three independent vertices with nowhere to sit in that record. They were
concatenated -- every rectangle, then every triangle -- which is *batching by
primitive kind*, and batching by kind throws paint order away between kinds.

It showed the moment a panel drew something that is not a rectangle. The
labelling network's chords and the nerd overlay's graphs are triangles, so they
floated above the menu opened over them, above the window frame they were
inside, above everything: "the plot is somehow on top, but should be below".
No amount of reordering the paint pass could fix it, because the paint pass was
already in the right order.

So the painter records the order the two streams were written in and puts them
back together that way. What is pinned here is the property -- submission order
survives to the buffer, for every primitive the painter offers, including the
one that writes glyph quads straight into the array and has to say so.
"""
from __future__ import annotations

import numpy as np
import pytest

from cmtk.quad_painter import QuadPainter

RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)


def _colours(painter) -> list:
    """The colour of every vertex in the buffer, in order."""
    return [tuple(np.round(row[4:8], 3)) for row in painter.vertices()]


def _first_at(colours, wanted) -> int:
    for index, colour in enumerate(colours):
        if colour[:3] == pytest.approx(wanted, abs=0.01):
            return index
    raise AssertionError(f"{wanted} was not drawn at all")


def test_a_triangle_drawn_before_a_rectangle_is_behind_it():
    p = QuadPainter()
    p.fill_triangle((0, 0), (5, 0), (0, 5), GREEN)
    p.fill_rect(0, 0, 10, 10, RED)
    colours = _colours(p)
    assert _first_at(colours, (0, 1, 0)) < _first_at(colours, (1, 0, 0))


def test_a_triangle_drawn_after_a_rectangle_is_in_front_of_it():
    """The reported bug is this one's mirror: it used to hold either way."""
    p = QuadPainter()
    p.fill_rect(0, 0, 10, 10, RED)
    p.fill_triangle((0, 0), (5, 0), (0, 5), GREEN)
    colours = _colours(p)
    assert _first_at(colours, (1, 0, 0)) < _first_at(colours, (0, 1, 0))


def test_the_streams_interleave_as_often_as_they_are_swapped():
    p = QuadPainter()
    p.fill_rect(0, 0, 10, 10, RED)
    p.fill_triangle((0, 0), (5, 0), (0, 5), GREEN)
    p.fill_rect(0, 0, 10, 10, BLUE)
    colours = _colours(p)
    assert (_first_at(colours, (1, 0, 0))
            < _first_at(colours, (0, 1, 0))
            < _first_at(colours, (0, 0, 1)))


@pytest.mark.parametrize("draw", [
    lambda p: p.polyline([(0, 0), (10, 10), (20, 0)], 2.0, GREEN),
    lambda p: p.fill_convex([(0, 0), (10, 0), (10, 10), (0, 10)], GREEN),
    lambda p: p.fill_triangle((0, 0), (5, 0), (0, 5), GREEN),
])
def test_every_triangle_primitive_keeps_its_place(draw):
    """A plot trace, a filled polygon and a bare triangle are the same case."""
    p = QuadPainter()
    draw(p)
    p.fill_rect(0, 0, 40, 40, RED)
    colours = _colours(p)
    assert _first_at(colours, (0, 1, 0)) < _first_at(colours, (1, 0, 0))


def test_text_takes_its_place_too():
    """Glyph quads are written straight into the array; they must still be told.

    Missing them shifted every run after the first label, which drew the panel's
    contents somewhere else entirely -- a worse bug than the one being fixed,
    and the reason this test asks about the accounting rather than the picture.
    """
    from cmtk.painter import ALIGN_LEFT, ALIGN_VCENTER

    p = QuadPainter()
    p.fill_rect(0, 0, 10, 10, RED)
    p.text(0, 0, 80, 12, ALIGN_LEFT | ALIGN_VCENTER, "hello", BLUE)
    p.fill_triangle((0, 0), (5, 0), (0, 5), GREEN)
    accounted = sum(count * (6 if kind == 0 else 3) for kind, count in p._runs)
    assert accounted == len(p.vertices()), "a primitive reached the buffer unrecorded"


def test_the_buffer_is_still_one_upload():
    """Order is restored by slicing runs, not by drawing in several passes."""
    p = QuadPainter()
    for _ in range(20):
        p.fill_rect(0, 0, 10, 10, RED)
        p.fill_triangle((0, 0), (5, 0), (0, 5), GREEN)
    vertices = p.vertices()
    assert vertices.dtype == np.float32
    assert vertices.flags["C_CONTIGUOUS"]
    assert len(vertices) == 20 * 6 + 20 * 3
    assert len(p._runs) == 40, "runs should merge only when the kind repeats"


def test_clearing_forgets_the_order_as_well():
    p = QuadPainter()
    p.fill_rect(0, 0, 10, 10, RED)
    p.fill_triangle((0, 0), (5, 0), (0, 5), GREEN)
    p.clear()
    assert p._runs == []
    assert len(p.vertices()) == 0
