"""Shared test helpers: a driver that operates the window with pointer and keys, and a layout checker."""

from __future__ import annotations

import time

from chisurf.plugins.core.project_browser.test.driving import (
    ClipPainter as ClipPainter,
)
from chisurf.plugins.core.project_browser.test.driving import (
    clipped_texts as clipped_texts,
)
from chisurf.plugins.core.project_browser.test.driving import (
    layout_problems as layout_problems,
)
from chisurf.plugins.microscopy.imaging_emtk.testing import (  # noqa: F401
    Driver,
    MetricPainter,
    hermetic_env,
)

BIG = (1200, 800)
SMALL = (800, 600)


class PSFDriver(Driver):
    """The imaging driver reading rectangles from the window's one registry (``item_rects``) and waiting for the volume."""

    def __init__(self, app, size=BIG):
        super().__init__(app, size)

    def rect(self, name):
        self.draw(1)
        found = self.app.item_rects.get(name)
        assert found, f"{name!r} was not drawn: {sorted(self.app.item_rects)}"
        return tuple(found)

    def settle(self, timeout=120.0, extra=2):
        """Draw until the debounce has run and the volume for the current parameters is in."""
        end = time.monotonic() + timeout
        self.draw(1)
        while (self.app.busy or self.app.model.is_stale) and not self.app.error and time.monotonic() < end:
            time.sleep(0.02)
            self.draw(1)
        assert not self.app.busy, "the computation did not finish"
        return self.draw(extra)


def draw_clip(app, size, frames=3):
    painter = None
    for _ in range(frames):
        painter = ClipPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def overlaps(a, b, tol=1.0):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw - tol and bx < ax + aw - tol and ay < by + bh - tol and by < ay + ah - tol
