"""While a tool works, the user waits behind a blur with a progress bar -- for every tool in the shell.

The shell draws each hosted tool, then :class:`BusyOverlay` over it. When the tool has been busy
for :data:`DELAY_S` (a short job never flickers a card) its area is washed and blurred
(:func:`emtk.backdrop.draw_modal_backdrop`, the look of every modal surface) and a card says what
it is doing, with a bar: filled to the fraction when the tool reports one, sliding otherwise, and
a *Stop* button when the tool can be stopped. Clicks into the tool wait until it is done.

No tool has to do anything for this: :func:`busy_state` reads the conventions the tools already
follow -- ``running`` / ``busy`` (on the app, its controller, its job, a hub's current step),
``progress_fraction`` or ``progress = (done, total)``, the job's ``progress`` text, ``stop()`` /
``cancel()`` or a model's ``cancel_event``. A tool whose ``running`` is a live view the user
watches (Record's acquisition) sets ``busy_overlay = False``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

#: Seconds a tool must be busy before the overlay shows.
DELAY_S = 0.5

CARD_W, CARD_H = 380.0, 124.0
_CARD_BG = (36, 38, 46, 245)
_CARD_BORDER = (90, 96, 110, 255)
_BAR_BG = (58, 62, 74, 255)
_BAR_FG = (96, 150, 230, 255)
_TEXT = (230, 232, 238, 255)
_MUTED = (170, 175, 186, 255)
_BUTTON = (70, 76, 92, 255)


@dataclass
class BusyState:
    """What the overlay shows: the line, the fraction (``None``: unknown) and how to stop."""

    message: str
    fraction: float | None = None
    stop: Callable[[], Any] | None = None


def _flag(obj: Any, name: str) -> bool:
    value = getattr(obj, name, None)
    return value is True  # a property evaluated to True; methods and other values do not count


def _fraction(obj: Any) -> float | None:
    value = getattr(obj, "progress_fraction", None)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, min(1.0, float(value)))
    value = getattr(obj, "progress", None)
    if isinstance(value, tuple) and len(value) == 2:
        done, total = value
        if isinstance(total, (int, float)) and total > 0:
            return max(0.0, min(1.0, float(done) / float(total)))
    return None


def _message(obj: Any) -> str:
    job = getattr(obj, "job", None)
    text = getattr(job, "progress", "") if job is not None else ""
    if isinstance(text, str) and text.strip():
        return text.strip()
    for owner in (obj, getattr(obj, "model", None), getattr(obj, "controller", None)):
        text = getattr(owner, "status_text", "") if owner is not None else ""
        if isinstance(text, str) and text.strip():
            return text.strip()
    return ""


def _stopper(obj: Any) -> Callable[[], Any] | None:
    for owner in (obj, getattr(obj, "controller", None)):
        if owner is None:
            continue
        for name in ("stop", "cancel"):
            method = getattr(owner, name, None)
            if callable(method):
                return method
    for owner in (getattr(obj, "model", None), getattr(obj, "controller", None)):
        event = getattr(owner, "cancel_event", None) if owner is not None else None
        if event is not None and callable(getattr(event, "set", None)):
            return event.set
    return None


def busy_state(app: Any, _depth: int = 0) -> BusyState | None:
    """The tool's busy state, or ``None`` when it is idle (or opted out with ``busy_overlay = False``)."""
    if app is None or getattr(app, "busy_overlay", True) is False or _depth > 3:
        return None
    owners = [app, getattr(app, "controller", None), getattr(app, "job", None)]
    busy = any(o is not None and (_flag(o, "running") or _flag(o, "busy")) for o in owners)
    if not busy:
        # a hub (tool rail, wizard): the step on screen is what works
        for name in ("child", "current_app"):
            child = getattr(app, name, None)
            if child is not None and child is not app and not callable(child):
                state = busy_state(child, _depth + 1)
                if state is not None:
                    return state
        return None
    fraction = next(
        (f for f in (_fraction(o) for o in [*owners, getattr(app, "model", None)] if o is not None)
         if f is not None),
        None,
    )
    return BusyState(_message(app), fraction, _stopper(app))


class BusyOverlay:
    """The overlay of one hosted tool: when it started being busy, and where its Stop button is."""

    def __init__(self, delay_s: float = DELAY_S) -> None:
        self.delay_s = float(delay_s)
        self.since: float | None = None
        self.state: BusyState | None = None
        self.visible = False
        self.stop_rect: tuple[float, float, float, float] | None = None
        self.stopping = False

    def update(self, app: Any, now: float | None = None) -> bool:
        """Read the tool; returns whether the overlay shows this frame."""
        now = time.monotonic() if now is None else now
        self.state = busy_state(app)
        if self.state is None:
            self.since, self.visible, self.stopping = None, False, False
            return False
        if self.since is None:
            self.since = now
        self.visible = now - self.since >= self.delay_s
        return self.visible

    def draw(self, painter: Any, box: tuple[float, float, float, float], now: float | None = None) -> None:
        """Blur *box* (canvas coordinates) and draw the card over it."""
        if not self.visible or self.state is None:
            self.stop_rect = None
            return
        from emtk.backdrop import draw_modal_backdrop

        now = time.monotonic() if now is None else now
        x, y, w, h = box
        draw_modal_backdrop(painter, x, y, w, h)
        can_stop = self.state.stop is not None and not self.stopping
        cw, ch = min(CARD_W, max(160.0, w - 24.0)), CARD_H if can_stop else CARD_H - 30.0
        cx, cy = x + (w - cw) / 2.0, y + max(8.0, (h - ch) / 2.0)
        painter.fill_rect(cx - 1, cy - 1, cw + 2, ch + 2, _CARD_BORDER)
        painter.fill_rect(cx, cy, cw, ch, _CARD_BG)
        elapsed = max(0.0, now - (self.since or now))
        title = "Stopping…" if self.stopping else "Working…"
        painter.text(cx + 14, cy + 10, cw - 28, 20, 0, f"{title}  {elapsed:.0f} s", _TEXT, True)
        line = (self.state.message or "Please wait until this step has finished.").splitlines()[0]
        if len(line) > 60:
            line = line[:59] + "…"
        painter.text(cx + 14, cy + 34, cw - 28, 18, 0, line, _MUTED)
        bx, by, bw, bh = cx + 14, cy + 60, cw - 28, 12
        painter.fill_rect(bx, by, bw, bh, _BAR_BG)
        if self.state.fraction is not None:
            painter.fill_rect(bx, by, bw * self.state.fraction, bh, _BAR_FG)
            painter.text(bx, by + bh + 2, bw, 16, 2, f"{100 * self.state.fraction:.0f} %", _MUTED)
        else:  # unknown size: a segment sliding across
            seg = 0.25
            t = (elapsed * 0.6) % (1.0 + seg) - seg
            start, end = max(0.0, t), min(1.0, t + seg)
            if end > start:
                painter.fill_rect(bx + bw * start, by, bw * (end - start), bh, _BAR_FG)
        self.stop_rect = None
        if can_stop:
            sw, sh = 72.0, 22.0
            sx, sy = cx + cw - 14 - sw, cy + ch - 10 - sh
            painter.fill_rect(sx, sy, sw, sh, _BUTTON)
            painter.text(sx, sy + 2, sw, sh - 4, 1, "Stop", _TEXT)
            self.stop_rect = (sx, sy, sw, sh)

    def press(self, x: float, y: float) -> bool:
        """A press while the overlay shows: Stop stops the tool; any other press is swallowed.

        Returns ``True`` when the press was the overlay's (the tool must not see it).
        """
        if not self.visible:
            return False
        r = self.stop_rect
        if r is not None and r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]:
            stop = self.state.stop if self.state is not None else None
            if callable(stop):
                try:
                    stop()
                finally:
                    self.stopping = True
        return True
