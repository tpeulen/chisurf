"""Shared test helpers: a driver that operates the window with pointer and keys, and a layout checker."""

from __future__ import annotations

import time

from emtk.painter import ALIGN_HCENTER, ALIGN_RIGHT, ALIGN_VCENTER, colour_bytes

from chisurf.plugins.microscopy.imaging_emtk.testing import (  # noqa: F401
    Driver,
    MetricPainter,
    hermetic_env,
)

BIG = (1200, 800)
SMALL = (800, 600)


class BrowserDriver(Driver):
    """The imaging driver reading rectangles from the window's one registry (``item_rects``) and waiting for jobs."""

    def __init__(self, app, size=BIG):
        super().__init__(app, size)

    def rect(self, name):
        self.draw(1)
        found = self.app.item_rects.get(name)
        assert found, f"{name!r} was not drawn: {sorted(self.app.item_rects)}"
        return tuple(found)

    def settle(self, timeout=60.0, extra=2):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.jobs.future is not None:
            assert time.monotonic() < end, "the project job did not finish"
            time.sleep(0.02)
            self.draw(1)
        return self.draw(extra)


class ClipPainter(MetricPainter):
    """Records each text with the clip rectangle it was drawn under and the width it needs (to find a cut-off label)."""

    def __init__(self):
        super().__init__()
        self._stack = []
        self.shown = []
        self.ink_rects = []
        self._text_calls = []

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
        need = self.text_width(str(string))
        text_x = (
            x + w - need
            if align & ALIGN_RIGHT
            else (x + (w - need) / 2 if align & ALIGN_HCENTER else x)
        )
        self.shown.append(((x, y, w, h), str(string), clip, need))
        line_height = self.line_height()
        text_y = y + (h - line_height) / 2 if align & ALIGN_VCENTER else y
        self.ink_rects.append((text_x, text_y, need, line_height))
        self._text_calls.append(len(self.calls) - 1)

    @staticmethod
    def _intersection(a, b):
        """Return the positive rectangular intersection of two painter bounds."""
        x0, y0 = max(a[0], b[0]), max(a[1], b[1])
        x1, y1 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
        return (x0, y0, x1 - x0, y1 - y0) if x1 > x0 and y1 > y0 else None

    @classmethod
    def _subtract(cls, rect, cover):
        """Keep every part of a text rectangle not covered by an opaque fill."""
        common = cls._intersection(rect, cover)
        if common is None:
            return [rect]
        x, y, w, h = rect
        cx, cy, cw, ch = common
        pieces = [
            (x, y, w, cy - y),
            (x, cy + ch, w, y + h - cy - ch),
            (x, cy, cx - x, ch),
            (cx + cw, cy, x + w - cx - cw, ch),
        ]
        return [piece for piece in pieces if piece[2] > 0 and piece[3] > 0]

    def visible_text_fragments(self):
        """Yield measured text pieces that survive scissoring and later opaque paint."""
        covers, stack = [], []
        for index, call in enumerate(self.calls):
            kind, *args = call
            if kind == "push_clip":
                stack.append(tuple(args))
            elif kind == "pop_clip":
                if stack:
                    stack.pop()
            elif kind in ("fill_rect", "stroke_rect"):
                colour = args[4] if kind == "fill_rect" else args[5]
                if colour is None:
                    continue
                rgba = colour_bytes(colour)
                if len(rgba) > 3 and rgba[3] != 255:
                    continue
                rect = tuple(args[:4])
                for clip in stack:
                    rect = self._intersection(rect, clip)
                    if rect is None:
                        break
                if rect is not None:
                    covers.append((index, rect))
        for shown, ink, index in zip(self.shown, self.ink_rects, self._text_calls, strict=True):
            _allocated, caption, clip, _need = shown
            if not caption.strip():
                continue
            visible = ink
            if clip is not None:
                x0, y0, x1, y1 = clip
                visible = self._intersection(ink, (x0, y0, x1 - x0, y1 - y0))
            if visible is None:
                continue
            pieces = [visible]
            for painted_at, cover in covers:
                if painted_at > index:
                    pieces = [part for piece in pieces for part in self._subtract(piece, cover)]
                    if not pieces:
                        break
            if pieces:
                yield shown, ink, pieces


def clipped_texts(painter, ignore=()):
    """Texts that begin inside their clip rectangle but are cut by its right edge or sit half outside it vertically."""
    out = []
    for (_allocated, s, clip, need), (x, y, w, h), _pieces in painter.visible_text_fragments():
        if clip is None or not s.strip() or any(overlaps((x, y, w, h), g, 0) for g in ignore):
            continue
        x0, y0, x1, y1 = clip
        if x1 <= x0 or y1 <= y0:
            continue
        if y + h <= y0 or y >= y1 or x < x0 - 0.5:
            continue  # scrolled out of view vertically, not cut
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

    Horizontal bounds follow the painted text's metrics and alignment, not its
    allocation box. A text counts through the part its clip rectangle lets through:
    a scrolled-away row is not visible. The rectangles in *ignore* are skipped.
    """
    problems = []
    visible = []
    for (_, s, _clip, _need), (x, y, w, h), pieces in painter.visible_text_fragments():
        if not s.strip() or any(overlaps((x, y, w, h), g, 0) for g in ignore):
            continue
        for rect in pieces:
            rx, ry, rw, rh = rect
            if rx < -0.5 or ry < -0.5 or rx + rw > size[0] + 0.5 or ry + rh > size[1] + 0.5:
                problems.append(f"outside the window: {s!r} {tuple(round(v) for v in rect)}")
            visible.append((rect, s))
    for i, (a, sa) in enumerate(visible):
        for b, sb in visible[i + 1 :]:
            if overlaps(a, b, 2.0):
                problems.append(
                    f"overlap: {sa!r} {tuple(round(v) for v in a)} with {sb!r} {tuple(round(v) for v in b)}"
                )
    return problems
