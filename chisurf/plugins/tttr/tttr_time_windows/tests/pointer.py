"""Simulated pointer and keyboard input for a drawn emtk app.

The app is an :class:`emtk.app.ImApp`: its ``pointer_move`` / ``pointer_press`` /
``pointer_release`` / ``wheel`` / ``key`` hooks are what every host (Qt, native window, page)
calls, and the next ``draw`` acts on them. This driver draws a frame after each event, finds a
control by the text it drew (centre of its box) and reports what the next frame shows.
"""

from __future__ import annotations

from emtk.app import LEFT_BUTTON, RIGHT_BUTTON
from emtk.keys import KEY_BACKSPACE, KEY_ENTER, KEY_ESCAPE, KEY_RETURN, KEY_TAB
from emtk.testing import RecordingPainter

__all__ = ["Pointer", "KEY_BACKSPACE", "KEY_ENTER", "KEY_ESCAPE", "KEY_RETURN", "KEY_TAB"]


class Pointer:
    """Click, drag, type and scroll on a drawn app, one frame per event."""

    def __init__(self, app, size=(1200.0, 800.0)) -> None:
        self.app = app
        self.size = size
        self.painter = RecordingPainter()
        self.frame(3)

    # -- frames ---------------------------------------------------------------
    def frame(self, n: int = 1) -> RecordingPainter:
        for _ in range(n):
            self.painter = RecordingPainter()
            self.app.draw(self.painter, 0.0, 0.0, *self.size)
        return self.painter

    @property
    def strings(self) -> list[str]:
        return self.painter.strings

    def drawn(self, text: str) -> bool:
        return text in self.painter.strings

    # -- finding controls --------------------------------------------------------
    def boxes(self, text: str) -> list[tuple[float, float, float, float]]:
        return [(t[0], t[1], t[2], t[3]) for t in self.painter.texts if t[5] == text]

    def where(self, text: str, nth: int = 0) -> tuple[float, float]:
        """The centre of the *nth* box in which *text* was drawn (last frame)."""
        found = self.boxes(text)
        if len(found) <= nth:
            raise AssertionError(f"{text!r} was not drawn (n={nth}): {self.painter.strings}")
        x, y, w, h = found[nth]
        return (x + w / 2.0, y + h / 2.0)

    def _point(self, target, nth: int = 0):
        if isinstance(target, str):
            return self.where(target, nth)
        return (float(target[0]), float(target[1]))

    # -- pointer ------------------------------------------------------------------
    def move(self, target, nth: int = 0, buttons: int = 0):
        p = self._point(target, nth)
        self.app.pointer_move(*p, buttons)
        self.frame()
        return p

    def press(self, target, nth: int = 0, button=LEFT_BUTTON, clicks: int = 1, modifiers: int = 0):
        p = self.move(target, nth)
        self.app.pointer_press(*p, button, modifiers, clicks)
        self.frame()
        return p

    def release(self, p, button=LEFT_BUTTON, modifiers: int = 0) -> None:
        self.app.pointer_release(*p, button, modifiers)
        self.frame(2)

    def click(self, target, nth: int = 0, button=LEFT_BUTTON, modifiers: int = 0):
        """Hover, press and release at the control; returns the point."""
        p = self.press(target, nth, button, 1, modifiers)
        self.release(p, button, modifiers)
        return p

    def right_click(self, target, nth: int = 0):
        return self.click(target, nth, RIGHT_BUTTON)

    def double_click(self, target, nth: int = 0):
        p = self.click(target, nth)
        self.app.pointer_press(*p, LEFT_BUTTON, 0, 2)
        self.frame()
        self.release(p)
        return p

    def drag(self, start, end, steps: int = 6, nth: int = 0):
        """Press at *start*, move to *end* in *steps*, release there."""
        a = self._point(start, nth)
        b = self._point(end)
        self.press(a)
        for i in range(1, steps + 1):
            q = (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)
            self.app.pointer_move(*q, LEFT_BUTTON)
            self.frame()
        self.release(b)
        return b

    def wheel(self, target, steps: float, nth: int = 0):
        p = self.move(target, nth)
        self.app.wheel(*p, steps)
        self.frame(2)

    # -- keyboard --------------------------------------------------------------------
    def key(self, key: int, text: str = "", modifiers: int = 0) -> None:
        self.app.key(key, text, modifiers)
        self.frame()
        self.frame()

    def type(self, text: str) -> None:
        for ch in text:
            self.key(ord(ch.upper()) if ch.isalpha() else ord(ch), ch)

    def enter(self) -> None:
        self.key(KEY_RETURN)
