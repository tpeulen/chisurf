"""chimol's viewport on a plain ``rendercanvas`` surface -- the Qt-free host.

What this is
------------
:class:`CanvasView` is the second host for :class:`~.canvas_base.CanvasRenderer`
and the **default** one. It owns a ``rendercanvas`` window rather than being a
``QWidget``, and it translates that canvas' events -- which are the
jupyter-rfb/DOM vocabulary a browser also speaks -- into the engine's own
``on_pointer_press`` and friends.

It draws through the same ``_draw`` as the Qt widget, because it *is* the same
``_draw``: the only things this class adds are a canvas, five event handlers and
the two size accessors that differ between owning a window and being one.

Choosing a backend
------------------
Explicitly, and **never** through ``rendercanvas.auto``. That helper's final
fallback tries to ``import PyQt5`` and selects its Qt backend if the import
succeeds -- so on any machine with Qt installed, "automatic" means Qt, which is
exactly the outcome this host exists to avoid. :func:`canvas_module` therefore
names the backend it wants: an OS window when one is available, and the
offscreen canvas otherwise.

The offscreen canvas is not a degraded mode for the purposes of this file: it
renders every frame the window would, which is what makes the Qt-free path
testable on a build machine with no display.
"""
from __future__ import annotations

import importlib
import os

from ..host.events import (
    NO_BUTTON,
    NO_MODIFIER,
    button_from_canvas,
    modifiers_from_canvas,
)
from ..host.keys import key_from_dom
from .canvas_base import CanvasRenderer

__all__ = [
    "DEFAULT_WINDOW_SIZE",
    "INTERACTIVE_BACKENDS",
    "CanvasView",
    "canvas_module",
    "is_available",
    "renderer_factory",
]

#: The window chimol opens when nothing says otherwise. Wide, because the object
#: panel takes a column out of it and a narrow window leaves the molecule a
#: strip.
DEFAULT_WINDOW_SIZE = (1280, 860)

#: Backends that put a real window on a real screen without a GUI toolkit, most
#: preferred first. Only ``glfw`` today; it needs the ``glfw`` PyPI package,
#: which is a small ctypes wrapper over a C library and pulls in nothing else.
INTERACTIVE_BACKENDS = ("glfw",)

#: One notch of a ``rendercanvas`` wheel event. Its ``dy`` follows the DOM's
#: ``WheelEvent.deltaY``, which is **positive downwards** where Qt's angle delta
#: is positive away from the user -- so the sign is flipped on the way in, or
#: the wheel zooms the wrong way and nothing but a hand on a mouse notices.
WHEEL_NOTCH = 100.0


def canvas_module(backend: str | None = None):
    """Import and return the ``rendercanvas`` backend module to draw on.

    Parameters
    ----------
    backend : str, optional
        A ``rendercanvas`` backend name (``"glfw"``, ``"offscreen"``, ``"qt"``,
        ...). ``CHIMOL_CANVAS`` is consulted when this is ``None``, and after
        that an interactive backend is tried before the offscreen one.

    Returns
    -------
    module
        A module exposing ``RenderCanvas`` and ``loop``.

    Notes
    -----
    ``rendercanvas.auto`` is deliberately not used; see this module's docstring.
    A named backend is imported as asked and its failure is *raised*, because a
    backend that was requested and silently swapped is the kind of thing that
    turns "the window did not open" into an afternoon.
    """
    name = (backend or os.environ.get("CHIMOL_CANVAS", "")).strip()
    if name:
        return importlib.import_module(f"rendercanvas.{name}")
    for candidate in INTERACTIVE_BACKENDS:
        try:
            return importlib.import_module(f"rendercanvas.{candidate}")
        except Exception:
            continue
    return importlib.import_module("rendercanvas.offscreen")


def is_available() -> bool:
    """Whether this machine can draw chimol without a GUI toolkit.

    Returns
    -------
    bool
        Whether a WebGPU adapter exists. The canvas itself is not probed here:
        the offscreen backend always imports, so the adapter is the only thing
        that can be missing.
    """
    from .gpu import native

    if not native.is_available():
        return False
    try:
        from .gpu import api as wgpu

        return wgpu.gpu.request_adapter_sync(power_preference="high-performance") is not None
    except Exception:
        return False


#: What a US keyboard produces with shift held. The canvas backend does not
#: apply it: ``rendercanvas``'s GLFW handler says so in its own comment --
#: *"if the user holds shift while pressing 5, [this] will result in 5, and not
#: in the % that you'd expect on a US keyboard"* -- because GLFW wants a
#: separate char callback for text, which the backend does not wire up.
#:
#: So every shifted symbol was unreachable from the in-viewport command line.
#: ``_`` is the one that matters most here: chimol's own settings and commands
#: are full of it (``mouse_selection_mode``, ``cartoon_tube_radius``), and
#: without this the prompt silently typed ``-`` instead.
#:
#: US layout, deliberately: it is the layout the symbols above are named for,
#: and guessing at others would be worse than a known, documented assumption.
#: A user on another layout still gets letters (handled separately) and every
#: unshifted key.
_SHIFT_MAP = {
    "`": "~", "1": "!", "2": "@", "3": "#", "4": "$", "5": "%",
    "6": "^", "7": "&", "8": "*", "9": "(", "0": ")",
    "-": "_", "=": "+", "[": "{", "]": "}", "\\": "|",
    ";": ":", "'": '"', ",": "<", ".": ">", "/": "?",
}


class CanvasView(CanvasRenderer):
    """Draw a chimol scene into a ``rendercanvas`` window, with no toolkit.

    Parameters
    ----------
    controller : object, optional
        The :class:`~.view.MolView` driving this renderer.
    parent : object, optional
        Accepted for signature parity with the Qt backend; unused, because
        there is no widget tree to be a child of.
    canvas : object, optional
        An already-built ``rendercanvas`` canvas to draw into. Given one, no
        backend is selected and no window is created -- which is how a test
        drives this class on the offscreen canvas.
    backend : str, optional
        Backend name for :func:`canvas_module`, when *canvas* is not given.
    size : tuple of int, optional
        Window size in logical pixels.
    title : str, optional
        Window title.
    """

    #: What this host delivers to the engine, as the keys
    #: :data:`chimol.testing.parity.HOST_FEATURES` names. Declared rather than
    #: inferred: every host has *some* method that could be handed a double
    #: click, so inspection cannot tell one that is wired to the canvas from one
    #: that is never called. A canvas emits all of these, which is why this is
    #: the reference half of the browser comparison.
    #:
    #: ``labels`` and ``ray_image`` are **absent on purpose**: they are the two
    #: overlays still rasterised with a painter (:meth:`_composite_overlay`), so
    #: the toolkit-free desktop host does not have them either. Claiming them
    #: here would make the browser look behind where it is level.
    supported_features = frozenset({
        "press", "double_click", "move", "release", "wheel", "wheel_modifiers",
        "key", "resize", "context_menu", "picking", "box_select",
    })

    def __init__(
        self,
        controller: object = None,
        parent: object = None,
        *,
        canvas: object = None,
        backend: str | None = None,
        size: tuple[int, int] = DEFAULT_WINDOW_SIZE,
        title: str = "chimol",
    ) -> None:
        self._parent = parent
        if canvas is None:
            module = canvas_module(backend)
            canvas = module.RenderCanvas(size=size, title=title)
            self._loop = getattr(module, "loop", None)
            #: Which backend drew this. Recorded rather than inferred from the
            #: loop: the offscreen canvas ships a *stub* loop that runs and
            #: returns immediately, so "has a loop" is true of a canvas nobody
            #: can see and is the wrong question to ask about interactivity.
            self._backend_name = module.__name__.rsplit(".", 1)[-1]
        else:
            self._loop = None
            self._backend_name = type(canvas).__module__.rsplit(".", 1)[-1]
        self._canvas = canvas
        self.init_viewport(controller)
        self._connect_events()
        # The canvas is created at its logical size and the camera is still on
        # the default viewport until something resizes it. An offscreen canvas
        # never emits a resize, so ask once rather than wait for an event that
        # is not coming.
        self.resize_viewport(*self._physical_size())

    # -- what owning a canvas answers differently ----------------------------

    def _surface(self):
        """The canvas this draws into."""
        return self._canvas

    def width(self) -> int:
        """Viewport width in **logical** pixels.

        Overrides :meth:`CameraState.width`, which reports the *device* pixels
        the projection is built from. The chrome lays itself out in logical
        pixels and every pointer event arrives in them, so a host that answers
        this in device pixels draws a panel that hit-tests half a window away.

        Returns
        -------
        int
        """
        try:
            return max(int(self._canvas.get_logical_size()[0]), 1)
        except Exception:
            return max(int(self._width), 1)

    def height(self) -> int:
        """Viewport height in logical pixels; see :meth:`width`.

        Returns
        -------
        int
        """
        try:
            return max(int(self._canvas.get_logical_size()[1]), 1)
        except Exception:
            return max(int(self._height), 1)

    def close(self) -> None:
        """Close the window."""
        try:
            self._canvas.close()
        except Exception:
            pass

    def is_closed(self) -> bool:
        """Whether the window has been closed.

        Returns
        -------
        bool
        """
        try:
            return bool(self._canvas.get_closed())
        except Exception:
            return False

    def is_interactive(self) -> bool:
        """Whether this canvas can be looked at and driven.

        Returns
        -------
        bool
            ``False`` for the offscreen canvas, which renders every frame the
            window would and shows none of them.
        """
        return self._loop is not None and self._backend_name != "offscreen"

    def draw_frame(self):
        """Render one frame now, rather than when the loop next gets to it.

        Returns
        -------
        numpy.ndarray or None
            The rendered image where the backend can hand one back -- the
            offscreen canvas' ``draw()`` does, and its ``force_draw()`` returns
            ``None``, which is a difference worth asking for by name: a caller
            that takes the ``None`` for "nothing was drawn" concludes the
            renderer is broken when it has just rendered a frame.
        """
        draw = getattr(self._canvas, "draw", None)
        if callable(draw):
            return draw()
        return self._canvas.force_draw()

    def run(self) -> None:
        """Pump the canvas' event loop until the window closes."""
        loop = self._loop
        if loop is not None:
            loop.run()

    # -- the canvas' events, translated --------------------------------------

    def _connect_events(self) -> None:
        """Register handlers for every event the viewport acts on."""
        add = getattr(self._canvas, "add_event_handler", None)
        if add is None:  # pragma: no cover - a canvas with no event system
            return
        add(self._on_pointer_down, "pointer_down")
        add(self._on_double_click, "double_click")
        add(self._on_pointer_move, "pointer_move")
        add(self._on_pointer_up, "pointer_up")
        add(self._on_wheel, "wheel")
        add(self._on_key_down, "key_down")
        add(self._on_key_up, "key_up")
        add(self._on_resize, "resize")

    @staticmethod
    def _buttons_mask(event: dict) -> int:
        """Fold a canvas event's held-button tuple into the engine's mask.

        Parameters
        ----------
        event : dict
            A ``rendercanvas`` pointer event.

        Returns
        -------
        int
        """
        mask = NO_BUTTON
        for button in event.get("buttons") or ():
            mask |= button_from_canvas(button)
        return mask

    def _on_pointer_down(self, event: dict) -> None:
        """Route a press."""
        self.on_pointer_press(
            float(event["x"]),
            float(event["y"]),
            button_from_canvas(event.get("button", 0)),
            modifiers_from_canvas(event.get("modifiers")),
        )

    def _on_double_click(self, event: dict) -> None:
        """Route the second press of a double click.

        The panel opens its menus on one (`DblClk Menu` in the mouse-mode
        block), and a canvas delivers it as its own event type in addition to
        the ordinary press -- so this only has to say *double*.
        """
        self.on_pointer_press(
            float(event["x"]),
            float(event["y"]),
            button_from_canvas(event.get("button", 0)),
            modifiers_from_canvas(event.get("modifiers")),
            double=True,
        )

    def _on_pointer_move(self, event: dict) -> None:
        """Route a move."""
        self.on_pointer_move(
            float(event["x"]),
            float(event["y"]),
            self._buttons_mask(event),
            modifiers_from_canvas(event.get("modifiers")),
        )

    def _on_pointer_up(self, event: dict) -> None:
        """Route a release."""
        self.on_pointer_release(
            float(event["x"]),
            float(event["y"]),
            button_from_canvas(event.get("button", 0)),
            modifiers_from_canvas(event.get("modifiers")),
        )

    def _on_wheel(self, event: dict) -> None:
        """Turn a canvas wheel delta into notches and route it."""
        raw = float(event.get("dy") or 0.0) or float(event.get("dx") or 0.0)
        if not raw:
            return
        # Away from zero: a trackpad sends many small deltas rather than whole
        # notches, and truncating those makes the gesture do nothing at all.
        steps = int(-raw / WHEEL_NOTCH)
        if steps == 0:
            steps = -1 if raw > 0 else 1
        self.on_wheel(
            float(event.get("x", 0.0)),
            float(event.get("y", 0.0)),
            steps,
            modifiers_from_canvas(event.get("modifiers")),
        )

    #: How long a key must be held before it starts repeating, and how fast it
    #: repeats after that, in seconds. The platform defaults people are used to.
    KEY_REPEAT_DELAY = 0.40
    KEY_REPEAT_INTERVAL = 0.035

    def _on_key_up(self, event: dict) -> None:
        """Stop repeating the key that was released.

        Parameters
        ----------
        event : dict
            A ``rendercanvas`` key event.
        """
        self._stop_key_repeat()

    def _stop_key_repeat(self) -> None:
        """Cancel any pending repeat."""
        timer = getattr(self, "_repeat_timer", None)
        if timer is not None:
            timer.stop()
        self._repeat_key = None

    def _start_key_repeat(self, key: int, text: str, modifiers: int) -> None:
        """Repeat a held key, because the canvas backend will not.

        ``rendercanvas``'s GLFW backend drops ``glfw.REPEAT`` outright -- its
        ``_on_key`` handles ``PRESS`` and ``RELEASE`` and returns on anything
        else -- so holding backspace in the command line deleted exactly one
        character however long it was held. That is upstream behaviour, not
        something chimol can configure, so the repeat is generated here.

        Parameters
        ----------
        key : int
            The key constant.
        text : str
            The character it produced, if any.
        modifiers : int
            The modifier mask at the time of the press.
        """
        from ..host.widget import Timer  # noqa: PLC0415

        timer = getattr(self, "_repeat_timer", None)
        if timer is None:
            timer = Timer()
            timer.timeout.connect(self._repeat_tick)
            self._repeat_timer = timer
        self._repeat_key = (key, text, modifiers)
        self._repeat_started = False
        timer.setSingleShot(True)
        timer.start(int(self.KEY_REPEAT_DELAY * 1000))

    def _repeat_tick(self) -> None:
        """Deliver one repeat and schedule the next."""
        held = getattr(self, "_repeat_key", None)
        if held is None:
            return
        self.on_key_press(*held)
        timer = self._repeat_timer
        timer.setSingleShot(True)
        timer.start(int(self.KEY_REPEAT_INTERVAL * 1000))

    def _on_key_down(self, event: dict) -> None:
        """Route a key press.

        A canvas names keys the way a browser does: ``"ArrowLeft"`` for the ones
        that act, and the character itself for the ones that type. So a
        single-character name *is* the text, and everything else translates
        through :func:`~chimol.host.keys.key_from_dom`.
        """
        name = str(event.get("key", "") or "")
        text = name if len(name) == 1 else ""
        # Apply shift ourselves; the backend hands us the unshifted key. Letters
        # upper-case, symbols through the US map -- see :data:`_SHIFT_MAP`.
        if text and "Shift" in (event.get("modifiers") or ()):
            text = text.upper() if text.isalpha() else _SHIFT_MAP.get(text, text)
        key = key_from_dom(name)
        modifiers = modifiers_from_canvas(event.get("modifiers"))
        self.on_key_press(key, text, modifiers)
        # Only keys that *do* something when repeated: a held modifier or a
        # held Escape must not fire a hundred times.
        from ..host.keys import KEY_ESCAPE, KEY_ENTER, KEY_RETURN  # noqa: PLC0415

        if key not in (KEY_ESCAPE, KEY_ENTER, KEY_RETURN) and (text or key):
            self._start_key_repeat(key, text, modifiers)

    def _on_resize(self, event: dict) -> None:
        """Track the framebuffer size the projection is built from."""
        self.resize_viewport(*self._physical_size())

    # -- driving it without a pointer ----------------------------------------

    def click(self, x: float, y: float, button: int, modifiers: int = NO_MODIFIER) -> None:
        """Synthesise a press and a release at one point.

        For a script and for a test: the viewport's click behaviour is decided
        on *release* (PyMOL keeps a separate row for clicks), so poking
        :meth:`on_pointer_press` alone proves nothing about what a click does.

        Parameters
        ----------
        x, y : float
            Where to click, in logical pixels.
        button : int
            One of :mod:`chimol.host.events`' ``*_BUTTON`` constants.
        modifiers : int, optional
            A mask of its ``*_MODIFIER`` constants.
        """
        self.on_pointer_press(x, y, button, modifiers)
        self.on_pointer_release(x, y, button, modifiers)

    def key(self, text: str, modifiers: int = NO_MODIFIER) -> bool:
        """Type one character into the viewport.

        Parameters
        ----------
        text : str
            The character.
        modifiers : int, optional
            A mask of the ``*_MODIFIER`` constants.

        Returns
        -------
        bool
            Whether it was consumed.
        """
        return self.on_key_press(key_from_dom(text), text, modifiers)


def renderer_factory(
    *,
    backend: str | None = None,
    size: tuple[int, int] = DEFAULT_WINDOW_SIZE,
    title: str = "chimol",
):
    """Return a factory ``MolView`` can build this renderer from.

    Parameters
    ----------
    backend : str, optional
        A ``rendercanvas`` backend name; see :func:`canvas_module`.
    size : tuple of int, optional
        Window size in logical pixels.
    title : str, optional
        Window title.

    Returns
    -------
    callable
        Accepts ``controller`` and ``parent``, which is the whole of the
        contract ``MolView.__init__`` uses when it builds a backend.
    """

    def factory(controller: object = None, parent: object = None) -> CanvasView:
        """Build a :class:`CanvasView` bound to *controller*."""
        return CanvasView(
            controller, parent, backend=backend, size=size, title=title
        )

    return factory
