"""The abstract controller every chigame game is written against.

Games bind to *actions*, never to keys or buttons. That is a design constraint
rather than a convenience: everything built on chigame must be playable on a
gamepad, so there are exactly nine inputs and no text entry. A game that cannot
be expressed in them is a game that would have needed a keyboard.

It also makes input scriptable. A headless test drives a game by pushing
actions, with no synthetic key events and no window.
"""

from __future__ import annotations

import enum
from collections.abc import Callable


class Action(enum.Enum):
    """The nine inputs a chigame game may respond to."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    MENU = "menu"
    SHOULDER_L = "shoulder_l"
    SHOULDER_R = "shoulder_r"


#: Default keyboard bindings. One action may have several keys; arrows and WASD
#: both drive movement so a second player can share a keyboard.
DEFAULT_BINDINGS: dict[str, Action] = {
    "ArrowUp": Action.UP,
    "ArrowDown": Action.DOWN,
    "ArrowLeft": Action.LEFT,
    "ArrowRight": Action.RIGHT,
    "w": Action.UP,
    "s": Action.DOWN,
    "a": Action.LEFT,
    "d": Action.RIGHT,
    "Enter": Action.CONFIRM,
    "\r": Action.CONFIRM,
    "\n": Action.CONFIRM,
    " ": Action.CONFIRM,
    "Escape": Action.CANCEL,
    "Backspace": Action.CANCEL,
    "Tab": Action.MENU,
    "q": Action.SHOULDER_L,
    "e": Action.SHOULDER_R,
}


class InputMap:
    """Tracks which actions are held, pressed and released this frame.

    Parameters
    ----------
    bindings : dict, optional
        Key name to :class:`Action`. Defaults to :data:`DEFAULT_BINDINGS`.
    """

    def __init__(self, bindings: dict[str, Action] | None = None) -> None:
        self.bindings = dict(DEFAULT_BINDINGS if bindings is None else bindings)
        self._held: set[Action] = set()
        self._pressed: set[Action] = set()
        self._released: set[Action] = set()
        self._wheel_dy = 0.0
        self._click: tuple[float, float] | None = None

    def attach(self, canvas) -> None:
        """Route a canvas' key, wheel and left-click events into this map.

        Parameters
        ----------
        canvas : object
            A ``rendercanvas`` canvas. The offscreen canvas emits no key
            events, which is why :meth:`press` exists.
        """
        canvas.add_event_handler(self._on_key_down, "key_down")
        canvas.add_event_handler(self._on_key_up, "key_up")
        canvas.add_event_handler(self._on_wheel, "wheel")
        canvas.add_event_handler(self._on_pointer_down, "pointer_down")

    def _on_key_down(self, event: dict) -> None:
        """Handle a canvas key-press event.

        Parameters
        ----------
        event : dict
            Event payload; ``event['key']`` names the key.
        """
        action = self.bindings.get(event.get("key", ""))
        if action is not None:
            self.press(action)

    def _on_key_up(self, event: dict) -> None:
        """Handle a canvas key-release event.

        Parameters
        ----------
        event : dict
            Event payload; ``event['key']`` names the key.
        """
        action = self.bindings.get(event.get("key", ""))
        if action is not None:
            self.release(action)

    def _on_wheel(self, event: dict) -> None:
        """Handle a canvas mouse-wheel event.

        Parameters
        ----------
        event : dict
            Event payload; ``event['dy']`` is the vertical scroll delta,
            positive scrolling down/away and negative scrolling up/toward,
            the same sign convention every ``rendercanvas`` backend already
            agrees on.
        """
        self._wheel_dy += float(event.get("dy", 0.0))

    def scroll(self, dy: float) -> None:
        """Feed a synthetic wheel step, for tests and scripted tours.

        Parameters
        ----------
        dy : float
            Same sign convention as a real wheel event: negative scrolls up.
        """
        self._wheel_dy += dy

    def _on_pointer_down(self, event: dict) -> None:
        """Handle a canvas left-click.

        Parameters
        ----------
        event : dict
            Event payload; ``event['button']`` is 1 for the left button,
            ``event['x']``/``event['y']`` are canvas pixels (top-left
            origin), not world units -- a game converts through its own
            camera, the same way it already does for drawing.
        """
        if event.get("button") == 1:
            self._click = (float(event.get("x", 0.0)), float(event.get("y", 0.0)))

    def click_at(self, x: float, y: float) -> None:
        """Feed a synthetic left-click, for tests and scripted tours.

        Parameters
        ----------
        x, y : float
            Canvas pixels, top-left origin -- same convention as a real
            ``pointer_down`` event.
        """
        self._click = (x, y)

    def click(self) -> tuple[float, float] | None:
        """Where the canvas was left-clicked during the frame being processed.

        Outside the nine-action controller on purpose, the same as
        :meth:`wheel_delta` -- a mouse is not a gamepad input.

        Returns
        -------
        tuple of float or None
            Canvas pixels, or ``None`` on a frame with no click.
        """
        return self._click

    def press(self, action: Action) -> None:
        """Mark an action as pressed.

        Parameters
        ----------
        action : Action
            The action. Repeated presses while already held do not re-trigger
            :meth:`just_pressed`, so key auto-repeat cannot double-fire a menu.
        """
        if action not in self._held:
            self._pressed.add(action)
        self._held.add(action)

    def release(self, action: Action) -> None:
        """Mark an action as released.

        Parameters
        ----------
        action : Action
            The action.
        """
        if action in self._held:
            self._released.add(action)
        self._held.discard(action)

    def tap(self, action: Action) -> None:
        """Press and release an action within one frame.

        Convenience for scripted tests and guided tours.

        Parameters
        ----------
        action : Action
            The action.
        """
        self.press(action)
        self._held.discard(action)
        self._released.add(action)

    def is_held(self, action: Action) -> bool:
        """Whether an action is currently down.

        Parameters
        ----------
        action : Action
            The action.

        Returns
        -------
        bool
            True while held.
        """
        return action in self._held

    def just_pressed(self, action: Action) -> bool:
        """Whether an action went down during the frame being processed.

        Parameters
        ----------
        action : Action
            The action.

        Returns
        -------
        bool
            True on the frame of the press only.
        """
        return action in self._pressed

    def just_released(self, action: Action) -> bool:
        """Whether an action came up during the frame being processed.

        Parameters
        ----------
        action : Action
            The action.

        Returns
        -------
        bool
            True on the frame of the release only.
        """
        return action in self._released

    def axis(self) -> tuple[float, float]:
        """The direction pad as a vector.

        Returns
        -------
        tuple of float
            ``(x, y)`` each in ``{-1, 0, 1}``. Y is positive downward, matching
            the camera's world convention.
        """
        x = float(self.is_held(Action.RIGHT)) - float(self.is_held(Action.LEFT))
        y = float(self.is_held(Action.DOWN)) - float(self.is_held(Action.UP))
        return x, y

    def wheel_delta(self) -> float:
        """How far the mouse wheel moved during the frame being processed.

        Outside the nine-action controller on purpose: a mouse is not a
        gamepad input and no game may *require* one, but reading a wheel is
        no different from reading a window resize -- an incidental fact
        about the host a game may use if it is there, never a control it can
        assume exists.

        Returns
        -------
        float
            Summed ``dy`` since the last :meth:`end_frame`; negative is
            scrolled up/toward, positive is scrolled down/away. Zero on a
            frame with no wheel activity, including every headless test that
            never calls :meth:`scroll`.
        """
        return self._wheel_dy

    def end_frame(self) -> None:
        """Clear the one-frame press, release, wheel and click state.

        Call once per frame, after the game has read its input.
        """
        self._pressed.clear()
        self._released.clear()
        self._wheel_dy = 0.0
        self._click = None


def bind(mapping: dict[str, Action], **overrides: Action) -> dict[str, Action]:
    """Build a binding table from the default with overrides applied.

    Parameters
    ----------
    mapping : dict
        Base bindings.
    **overrides : Action
        Key name to action.

    Returns
    -------
    dict
        A new binding table.
    """
    table = dict(mapping)
    table.update(overrides)
    return table


#: Type of a per-frame update callback.
UpdateFn = Callable[[float], None]
