"""Real-input driver for the click tests of the emtk tool apps.

Only what a host delivers reaches the app: pointer press / release / move at screen positions, the wheel, typed
characters and keys, and file drops. Nothing here calls a model method, so a test built on it proves a control
works the way a user operates it. Rectangles come from what the app drew (``item_rects``, ``FormState.rects``,
or the text of a button found in the recording painter).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from emtk import keys
from emtk.testing import RecordingPainter

#: Modifier bit the emtk hosts send for Ctrl/Cmd (select all in a text field).
CTRL = 0x04000000
SIZE = (1200, 800)
SMALL = (800, 600)


class Driver:
    """Draw an app at a size and operate it with simulated pointer and keyboard events."""

    def __init__(
        self, app: Any, size: tuple[int, int] = SIZE, idle: Callable[[], bool] | None = None
    ) -> None:
        self.app = app
        self.size = size
        self.idle = idle

    # -- frames --------------------------------------------------------------------------------- #
    def draw(self, frames: int = 2) -> RecordingPainter:
        painter = RecordingPainter()
        for _ in range(frames):
            painter = RecordingPainter()
            self.app.draw(painter, 0, 0, *self.size)
        return painter

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        self.draw()

    # -- lookup --------------------------------------------------------------------------------- #
    def rect(self, name: str) -> tuple[float, float, float, float]:
        """The rectangle the control *name* was drawn in (the app's item rectangles, then its forms')."""
        self.draw()
        rects = dict(getattr(self.app, "item_rects", {}) or {})
        for form in (
            (getattr(self.app, "forms", None) or {}).values()
            if isinstance(getattr(self.app, "forms", None), dict)
            else [getattr(self.app, "form", None)]
        ):
            rects.update(getattr(form, "rects", {}) or {})
        rect = rects.get(name)
        assert rect, f"{name!r} was not drawn: {sorted(rects)[:40]}"
        return tuple(rect)

    @staticmethod
    def text_rect(
        painter: RecordingPainter, label: str, last: bool = True
    ) -> tuple[float, float, float, float]:
        """The rectangle of the drawn text *label* (a button caption, a list entry, a table cell)."""
        hits = [t[:4] for t in painter.texts if t[5] == label]
        assert hits, f"{label!r} is not drawn: {[t[5] for t in painter.texts][:60]}"
        return hits[-1] if last else hits[0]

    def drawn(self, label: str) -> bool:
        return any(t[5] == label for t in self.draw(1).texts)

    # -- pointer -------------------------------------------------------------------------------- #
    def click(
        self, rect, fx: float = 0.5, fy: float = 0.5, clicks: int = 1, hold_frames: int = 1
    ) -> None:
        x, y, w, h = rect
        self.app.pointer_move(x + w * fx, y + h * fy)
        self.draw(1)
        self.app.press(x + w * fx, y + h * fy, clicks=clicks)
        self.draw(hold_frames)
        self.app.release()
        self.draw(1)

    def click_name(self, name: str, **kw) -> None:
        self.click(self.rect(name), **kw)

    def click_text(self, label: str, last: bool = True, **kw) -> None:
        self.click(self.text_rect(self.draw(2), label, last), **kw)

    def drag(self, start, end, steps: int = 8) -> None:
        (x0, y0), (x1, y1) = start, end
        self.app.pointer_move(x0, y0)
        self.draw(1)
        self.app.press(x0, y0)
        self.draw(1)
        for i in range(1, steps + 1):
            t = i / steps
            self.app.drag(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            self.draw(1)
        self.app.release()
        self.draw(2)

    def wheel(self, x: float, y: float, steps: float = 1.0, modifiers: int = 0) -> None:
        self.app.pointer_move(x, y)
        self.draw(1)
        self.app.wheel(x, y, steps, modifiers)
        self.draw(2)

    # -- keyboard ------------------------------------------------------------------------------- #
    def type(self, text: str) -> None:
        for ch in text:
            self.app.key(ord(ch.upper()) if ch.isalpha() else ord(ch), ch)
            self.draw(1)

    def enter(self) -> None:
        self.app.key(keys.KEY_RETURN, "\r")
        self.draw(2)

    def escape(self) -> None:
        self.app.key(keys.KEY_ESCAPE, "")
        self.draw(2)

    def delete(self) -> None:
        self.app.key(keys.KEY_DELETE, "")
        self.draw(2)

    def type_into(self, rect, text: str, fx: float = 0.3, commit: bool = True) -> None:
        """Click a text or number field, replace its content with *text*, press Enter."""
        self.click(rect, fx=fx)
        assert self.app.io.want_capture_keyboard, "the field did not take the keyboard"
        self.app.key(0x41, "a", CTRL)
        self.draw(1)
        self.type(text)
        if commit:
            self.enter()

    def type_into_name(self, name: str, text: str, **kw) -> None:
        self.type_into(self.rect(name), text, **kw)

    # -- host ----------------------------------------------------------------------------------- #
    def drop(self, *paths: str | Path) -> bool:
        handler = getattr(self.app, "files_dropped", None) or self.app.on_files_dropped
        took = handler([str(p) for p in paths])
        self.draw(2)
        return took

    def screenshot(self, path: str | Path) -> Path:
        from test.gui.emtk_port_parity import emtk_screenshot

        self.draw(2)
        return emtk_screenshot(self.app, Path(path), self.size)


def tour_card_box(
    tour: Any, size: tuple[int, int] = SIZE
) -> tuple[float, float, float, float] | None:
    """Where the guided-tour card of the current step is drawn: ``(x, y, w, h)``, mirroring ``EmTkGuidedTour.draw``.

    The card's size follows its text and the placement comes from the tour module's own ``place_tour_card``; the
    user's drag (``card_offset``) is added the way the tour adds it. ``None`` when no tour step is shown.
    """
    import sys

    if not getattr(tour, "active", False):
        return None
    step = tour.steps[tour.step_idx]
    width, height = float(size[0]), float(size[1])
    place = sys.modules[type(tour).__module__].place_tour_card
    target = step.get("target")
    rect = (
        tour.get_target_rect(tour._target_key(target))
        if target and callable(tour.get_target_rect)
        else None
    )
    card_w = min(480.0, width - 40.0)
    per_line = max(20.0, (card_w - 28.0) / 7.4)
    body = str(step.get("text", "")).replace("<br/>", "\n")
    import re

    body = re.sub(r"<[^>]+>", "", body)
    lines = sum(max(1, int(len(part) / per_line) + 1) for part in body.split("\n"))
    hint = step.get("hint") or (
        step.get("await", {}).get("hint") if isinstance(step.get("await"), dict) else None
    )
    lines += (int(len(str(hint)) / per_line) + 2) if hint else 0
    card_h = max(120.0, min(260.0, 78.0 + 16.0 * lines))
    x, y = place(rect, width, height, card_w, card_h)
    return (x + tour.card_offset[0], y + tour.card_offset[1], card_w, card_h)


def assert_tour_card_clear(tour: Any, size: tuple[int, int] = SIZE) -> None:
    """The current step's target was drawn, lies inside the window, and the card does not cover it."""
    if not getattr(tour, "active", False):
        return
    step = tour.steps[tour.step_idx]
    target = step.get("target")
    if not target:
        return
    key = tour._target_key(target)
    if not key:
        return
    rect = tour.get_target_rect(key)
    if rect is None:
        # A tab-only target (``{"tab": ...}``) is allowed to resolve to nothing; a named control is not.
        assert "tab" in target and not any(
            target.get(k) for k in ("name", "action", "key", "attr")
        ), f"step {step.get('title')!r}: target {target} was not drawn"
        return
    tx, ty, tw, th = rect
    assert (
        tw > 0
        and th > 0
        and tx >= 0
        and ty >= 0
        and tx + tw <= size[0] + 1
        and ty + th <= size[1] + 1
    ), f"step {step.get('title')!r}: target {key!r} {rect} is not inside the {size} window"
    cx, cy, cw, ch = tour_card_box(tour, size)
    covered = not (cx + cw <= tx or cx >= tx + tw or cy + ch <= ty or cy >= ty + th)
    assert not covered, (
        f"step {step.get('title')!r}: the card {(cx, cy, cw, ch)} covers its target {key!r} {rect}"
    )


__all__ = ["CTRL", "Driver", "SIZE", "SMALL", "assert_tour_card_clear", "tour_card_box"]
