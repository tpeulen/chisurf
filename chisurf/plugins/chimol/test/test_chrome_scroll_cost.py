"""Scrolling costs one panel, not the whole chrome.

"Still scrolling very slow ... architecture issue." It was. The chrome was
cached as *one* buffer behind *one* fingerprint, so the fingerprint could not
tell "the object list scrolled" from "the menu bar changed": every notch rebuilt
every window, the sequence strip, the menu bar and the status line. Measured on
a labelling network: 11 ms of an otherwise 3 ms frame, of which ten were the
windows that had not moved.

Two changes, and this file states them as properties rather than as timings --
a stopwatch on a loaded machine measures the machine:

* the chrome is painted in **blocks** with their own keys (the furniture under
  the windows, each window, the furniture over them), so a scroll invalidates
  one block;
* the object list draws the rows it can *see*, rather than drawing all of them
  and clipping;
* and a run of triangles is filled in one painter call, because a band or a
  ribbon emitted a triangle at a time is two Python calls per step -- which is
  what made a circle of a hundred chords expensive, quads being the thing it
  was not short of.
"""
from __future__ import annotations

import numpy as np
import pytest

from emtk.quad_painter import QuadPainter
from chimol.ui.gui import GuiRow, GuiWindow, InternalGui


def _gui(rows: int = 120) -> InternalGui:
    gui = InternalGui()
    gui.set_rows([GuiRow(name="all", is_header=True)]
                 + [GuiRow(name=f"object_{index}") for index in range(rows)])
    gui.add_window(GuiWindow(key="panel", title="Panel", x=40.0, y=90.0,
                             w=240.0, h=200.0,
                             body=lambda p, rect: p.text(
                                 rect.x, rect.y, rect.w, 14.0, 0x81, "body", (200,) * 3)))
    gui.layout(1000, 700)
    return gui


def _keys(gui) -> list:
    return [key for key, _paint in gui.paint_blocks(lambda: None)]


# --------------------------------------------------------------------------- #
# Blocks
# --------------------------------------------------------------------------- #
def test_the_chrome_is_painted_in_blocks():
    gui = _gui()
    kinds = [key[0] for key in _keys(gui)]
    assert kinds[0] == "under" and kinds[-1] == "over"
    assert "window" in kinds


def test_scrolling_one_panel_invalidates_only_that_panel():
    """The property the whole-chrome fingerprint could not express."""
    gui = _gui()
    before = _keys(gui)
    gui.scroll_objects(-60.0)
    gui.layout(1000, 700)
    after = _keys(gui)
    changed = [key for key in after if key not in before]
    assert len(changed) == 1, changed
    assert changed[0][0] == "window" and changed[0][1] == "objects"


def test_a_windows_own_repaint_does_not_touch_the_furniture():
    gui = _gui()
    before = dict.fromkeys(_keys(gui))
    window = gui.window("panel")
    window.body_revision += 1
    after = _keys(gui)
    assert [key for key in after if key not in before] == [
        key for key in after if key[0] == "window" and key[1] == "panel"
    ]


def test_the_furniture_key_ignores_the_windows():
    """Or a scroll invalidates the menu bar with it, which is the old cost.

    Asserted against the furniture key *and* the block keys, because those are
    the two halves of the claim: the windows are absent from the first and
    present in the second. `chrome_fingerprint` used to take a `with_windows`
    flag for the comparison, which no caller in the product ever passed -- so
    the assertion was made against a shape only the tests could produce.
    """
    gui = _gui()
    before = gui.chrome_fingerprint()
    keys_before = _keys(gui)
    gui.window("panel").body_revision += 1
    gui.scroll_objects(-30.0)
    assert gui.chrome_fingerprint() == before, "a window moved the furniture"
    assert _keys(gui) != keys_before, "a window moved nothing at all"


def test_the_blocks_still_draw_the_whole_chrome():
    """Split for caching, identical on screen: same vertices, same order."""
    gui = _gui()
    whole = QuadPainter(scale=1.0)
    gui.paint(whole)          # `paint` draws the over-window half itself

    pieces = []
    for _key, paint in gui.paint_blocks(lambda: None):
        painter = QuadPainter(scale=1.0)
        paint(painter)
        vertices = painter.vertices()
        if len(vertices):
            pieces.append(vertices)
    assembled = np.concatenate(pieces, axis=0)
    expected = whole.vertices()
    assert assembled.shape == expected.shape
    assert np.allclose(assembled, expected)


# --------------------------------------------------------------------------- #
# What each block costs to build
# --------------------------------------------------------------------------- #
def test_the_object_list_draws_only_the_rows_it_can_see():
    """Clipping hides an off-screen row; it does not stop it being emitted."""
    short = _gui(rows=8)
    long = _gui(rows=400)
    short_painter, long_painter = QuadPainter(scale=1.0), QuadPainter(scale=1.0)
    short._paint_panel(short_painter)
    long._paint_panel(long_painter)
    assert long_painter.vertex_count < short_painter.vertex_count * 8, (
        "a four-hundred-row list emits quads for rows nobody can see"
    )


def test_a_band_of_triangles_is_one_painter_call():
    """A circle's rings and ribbons: emitted per triangle, they are the frame."""
    from emtk.widgets.circle import CirclePlot

    calls = {"n": 0}

    class Counting(QuadPainter):
        def fill_triangle(self, *args, **kwargs):
            calls["n"] += 1
            return super().fill_triangle(*args, **kwargs)

    painter = Counting(scale=1.0)
    circle = CirclePlot(0, 0, 400, 400)
    circle.sector("E", (1, 164))
    circle.sector("S", (1, 40))
    circle.link(("E", 10, 30), ("S", 5, 20))          # a ribbon
    circle.link(("E", 20, 20), ("S", 8, 8))           # a line
    circle.draw(painter)
    assert calls["n"] == 0, f"{calls['n']} triangles emitted one at a time"
    assert len(painter.vertices()) > 100, "and it still drew something"


def test_every_painter_gets_the_triangles_even_without_a_fast_path():
    """The recording painter has six operations and must still see them all."""
    from emtk.painter import fill_triangles
    from emtk.testing import RecordingPainter

    painter = RecordingPainter()
    block = np.array([[[0, 0], [1, 0], [0, 1]], [[1, 0], [1, 1], [0, 1]]], dtype=float)
    fill_triangles(painter, block, (255, 0, 0, 255))
    assert len(painter.triangles) == 2
