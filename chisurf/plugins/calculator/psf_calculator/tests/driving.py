"""Shared test helpers: a driver that operates the window with pointer and keys, and a layout checker."""

from __future__ import annotations

import time

from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, MetricPainter, hermetic_env  # noqa: F401

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


class ClipPainter(MetricPainter):
    """Records each text with the clip rectangle it was drawn under and the width it needs (to find a cut-off label)."""

    def __init__(self):
        super().__init__()
        self._stack = []
        self.shown = []

    def push_clip(self, x, y, w, h):
        super().push_clip(x, y, w, h)
        self._stack.append((x, y, w, h))

    def pop_clip(self):
        super().pop_clip()
        if self._stack:
            self._stack.pop()

    def text(self, x, y, w, h, align, string, colour, bold=False):
        super().text(x, y, w, h, align, string, colour, bold)
        clip = None
        if self._stack:
            cx, cy, cw, ch = self._stack[0]
            x0, y0, x1, y1 = cx, cy, cx + cw, cy + ch
            for kx, ky, kw, kh in self._stack[1:]:
                x0, y0, x1, y1 = max(x0, kx), max(y0, ky), min(x1, kx + kw), min(y1, ky + kh)
            clip = (x0, y0, x1, y1)
        self.shown.append(((x, y, w, h), str(string), clip, self.text_width(str(string))))


def clipped_texts(painter, ignore=()):
    """Texts that begin inside their clip rectangle but are cut by its right edge or sit half outside it vertically."""
    out = []
    for (x, y, w, h), s, clip, need in painter.shown:
        if clip is None or not s.strip() or any(overlaps((x, y, w, h), g, 0) for g in ignore):
            continue
        x0, y0, x1, y1 = clip
        if x1 <= x0 or y1 <= y0:
            continue
        if y + h <= y0 or y >= y1 or x < x0 - 0.5:
            continue  # scrolled out of view vertically, not cut
        if x >= x1:
            out.append(f"starts beyond the right edge: {s!r} at x={x:.0f}, clip ends at {x1:.0f}")
            continue
        if x + need > x1 + 0.5 and w > need - 0.5:
            out.append(f"cut at the right edge: {s!r} needs {need:.0f}px, {x1 - x:.0f}px visible")
    return out


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


def layout_problems(painter, size, ignore=()):
    """Visible texts that run outside the window or overlap another visible text.

    A text counts through the part of it that its clip rectangle lets through: a row scrolled out of a window is not on
    screen. The rectangles in *ignore* (a plot, a graph canvas) are skipped.
    """
    problems = []
    visible = []
    for (x, y, w, h), s, clip, _need in painter.shown:
        if not s.strip() or any(overlaps((x, y, w, h), g, 0) for g in ignore):
            continue
        if clip is not None:
            x0, y0, x1, y1 = clip
            nx0, ny0, nx1, ny1 = max(x, x0), max(y, y0), min(x + w, x1), min(y + h, y1)
            if nx1 <= nx0 or ny1 <= ny0:
                continue  # clipped away entirely
            rect = (nx0, ny0, nx1 - nx0, ny1 - ny0)
        else:
            rect = (x, y, w, h)
        rx, ry, rw, rh = rect
        if rx < -0.5 or ry < -0.5 or rx + rw > size[0] + 0.5 or ry + rh > size[1] + 0.5:
            problems.append(f"outside the window: {s!r} {tuple(round(v) for v in rect)}")
        visible.append((rect, s))
    for i, (a, sa) in enumerate(visible):
        for b, sb in visible[i + 1:]:
            if overlaps(a, b, 2.0):
                problems.append(f"overlap: {sa!r} {tuple(round(v) for v in a)} with {sb!r} {tuple(round(v) for v in b)}")
    return problems
