"""A tool app hosted in the shell, spoken to through one contract whichever one the app speaks.

The shell forwards input to the tool under the pointer with the *rich* hooks an
:class:`emtk.app.ImApp` has -- ``pointer_press(x, y, button, modifiers, clicks)``,
``pointer_move``, ``pointer_release``, ``wheel``, ``animating``, ``next_frame_in``. A tool written
to emtk's *classic* control contract (``press(x, y, bx, by, bw, bh, modifiers, clicks)``,
``drag`` / ``hover``, ``release``, ``scroll``) -- what :class:`emtk.app.ControlSurface` hosts in
its own window -- has none of them, and the shell raised on every frame and pointer move while
one was open. :func:`as_child` puts such a tool behind :class:`ClassicChild`, which maps the rich
hooks onto the classic ones the way ``ControlSurface`` does.
"""

from __future__ import annotations

from typing import Any

#: The left mouse button, the only one the classic contract hears.
LEFT_BUTTON = 1


class ClassicChild:
    """A classic-contract control with the rich hooks the shell calls; everything else passes through."""

    def __init__(self, control: Any) -> None:
        self._control = control
        self._box = (0.0, 0.0, 1.0, 1.0)
        self._pressed = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._control, name)

    def _hook(self, name: str):
        hook = getattr(self._control, name, None)
        return hook if callable(hook) else None

    def draw(self, painter, x: float, y: float, w: float, h: float) -> None:
        self._box = (float(x), float(y), float(w), float(h))
        self._control.draw(painter, x, y, w, h)

    def pointer_press(self, x, y, button, modifiers=0, clicks=1) -> None:
        if button != LEFT_BUTTON:
            return
        self._pressed = True
        press = self._hook("press")
        if press is not None:
            press(float(x), float(y), *self._box, int(modifiers), int(clicks))

    def pointer_move(self, x, y, buttons=0, modifiers=0) -> None:
        handler = self._hook("drag" if self._pressed and int(buttons) & LEFT_BUTTON else "hover")
        if handler is not None:
            handler(float(x), float(y), *self._box)

    def pointer_release(self, x, y, button, modifiers=0) -> None:
        if button != LEFT_BUTTON:
            return
        self._pressed = False
        release = self._hook("release")
        if release is not None:
            release()

    def wheel(self, x, y, steps, modifiers=0) -> None:
        scroll = self._hook("scroll")
        if scroll is not None:
            scroll(int(steps))

    def scroll(self, rows) -> Any:
        scroll = self._hook("scroll")
        return scroll(rows) if scroll is not None else None

    def key(self, key, text="", modifiers=0) -> Any:
        hook = self._hook("key")
        return hook(key, text, modifiers) if hook is not None else False

    def animating(self) -> bool:
        hook = self._hook("animating")
        return bool(hook()) if hook is not None else False

    def next_frame_in(self) -> float | None:
        hook = self._hook("next_frame_in")
        return hook() if hook is not None else None


def as_child(app: Any) -> Any:
    """*app* itself when it has the rich hooks, else behind :class:`ClassicChild`."""
    if app is None or callable(getattr(app, "pointer_press", None)):
        return app
    return ClassicChild(app)


__all__ = ["ClassicChild", "as_child"]
