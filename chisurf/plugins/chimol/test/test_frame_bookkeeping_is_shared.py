"""Every host that draws a frame does the frame's bookkeeping the same way.

Four things happen around a frame that are not the rasterising: the movie is
advanced, the counters roll over, the frame is timed, and the readout's idle
timer is re-armed. Two of the three hosts got them from
``CanvasRenderer._draw``. The page rasterises into its own canvas and so has
its own ``draw`` -- and quietly had none of the four. The visible half was the
report "stats for nerds not displayed", then "not accurate ... seems broken":
in the browser the overlay reported a frame of 0.0 ms that drew 0 of
everything, on a page that was plainly drawing, and the movie had to be pumped
by hand from JavaScript to advance at all.

The fix is that the four are one thing with one owner --
``CanvasRenderer.frame()``, a context manager -- and a host wraps its draw in
it. What is pinned here is that property rather than the symptom: the page uses
it, the windowed path uses it, and neither carries its own copy of the clock.
"""

from __future__ import annotations

import inspect

import pytest
from chimol.viewport.canvas import CanvasRenderer


def test_the_renderer_offers_the_bookkeeping_as_one_call():
    assert hasattr(CanvasRenderer, "frame")
    assert hasattr(CanvasRenderer.frame, "__wrapped__"), (
        "`frame` should be a context manager -- a host wraps its draw in it"
    )


def test_the_windowed_draw_goes_through_it():
    source = inspect.getsource(CanvasRenderer._draw)
    assert "self.frame()" in source, source
    assert "stats.begin" not in source, "the windowed path grew its own copy again"


def test_the_page_goes_through_it_too():
    """The host that had none of it."""
    from chimol.hosts.web.page import Page

    source = inspect.getsource(Page.draw)
    assert "self.sink.frame()" in source, source


def test_the_page_has_no_second_clock():
    """`Page.pump` was the JavaScript-driven half; the frame is the clock now."""
    from chimol.hosts.web import page as page_module

    assert not hasattr(page_module.Page, "pump"), (
        "the page pumps the movie itself again -- two clocks, one movie"
    )
    boot = (page_module.__file__.rsplit("/", 1)[0]) + "/boot.js"
    with open(boot, encoding="utf-8") as handle:
        text = handle.read()
    assert "viewer.pump()" not in text, "boot.js still advances the movie by hand"
    assert "viewer.animating()" in text, "the rAF loop lost its continuation check"


def test_a_frame_fills_the_counters(monkeypatch):
    """What the readout reads: after one drawn frame, the counters are not zero.

    Driven through the mock host rather than a real GPU, so this runs
    everywhere; what it checks is the bookkeeping, which is host-independent.
    """
    stats = pytest.importorskip("chimol.render.frame_stats").FrameStats()
    stats.enabled = True
    stats.draw("mesh", instances=3, vertices=12)
    stats.count("chrome_quads", 40)
    stats.begin()  # rolls the frame over
    assert stats.last_draws == 1
    assert stats.last_instances == 3
    assert stats.last_chrome_quads == 40
    assert stats.draws == 0, "the live counters were not reset for the next frame"


def test_counting_costs_nothing_when_nobody_reads_it():
    from chimol.render.frame_stats import FrameStats

    stats = FrameStats()
    stats.draw("mesh", instances=3, vertices=12)
    stats.count("chrome_quads", 40)
    stats.begin()
    assert stats.last_draws == 0 and stats.last_chrome_quads == 0
