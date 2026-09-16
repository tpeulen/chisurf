"""The canvas holds the pointer in the router's one slot, not in a boolean.

``CanvasRenderer._gui_grab`` was a bare flag: set where the chrome took a press,
read on every move, cleared on release -- and, when a release never came,
cleared by a heuristic at the top of the *next* press. It was the outermost of
the three capture layers (canvas, window framework, widget), each with its own
release path, and that is the seam BUGS/001 (the DOM's ``dblclick`` is a press
with no release) and BUGS/002 (a grab left standing swallowed the next click)
lived in.

Now the canvas owns a :class:`~emtk.router.Router`: the chrome is a
layer, the camera is the fallthrough, and the grab *is* the capture slot. What
these pin is the behaviour that arrangement buys, at the seam where the chrome
and the camera meet:

* the chrome that takes a press holds the pointer, and the release reaches it
  wherever the pointer has gone;
* a press while something is held means the release was lost, so the capture is
  torn down with a first-class ``cancel`` before the new press is routed;
* a press the chrome declines falls through to the camera, once;
* the wheel and the hover are *not* routed yet (two hit orders remain), and
  saying so here keeps the next step honest.
"""
from __future__ import annotations

import pytest

from emtk.events import LEFT_BUTTON, RIGHT_BUTTON
from emtk.router import Consumed, Event, OverlayStack, Pass, Router
from chimol.viewport.chrome_layer import ChromeLayer


class _Gui:
    """The chrome, reduced to what the layer asks of it."""

    def __init__(self, *, takes=True):
        self.takes = takes
        self.dragging = False
        self.log: list = []

    def mouse_press(self, x, y, right=False, modifiers=0, double=False):
        self.log.append(("press", x, y, right, double))
        if self.takes:
            self.dragging = True
        return self.takes

    def is_dragging(self):
        return self.dragging

    def drag(self, x, y):
        self.log.append(("drag", x, y))
        return True

    def release(self):
        self.log.append(("release",))
        self.dragging = False


class _Canvas:
    """A canvas, reduced to what the layer asks of it -- and a camera that counts."""

    def __init__(self, gui):
        self._internal_gui = gui
        self.updates = 0
        self.camera: list = []
        self._chrome_layer = ChromeLayer(self)
        stack = OverlayStack()
        stack.add(self._chrome_layer)
        self.router = Router(stack, fallthrough=self._camera_event)

    def width(self):
        return 800

    def height(self):
        return 600

    def update(self):
        self.updates += 1

    def _camera_event(self, ev):
        self.camera.append(ev.kind)
        return Consumed if ev.kind in ("press", "move", "release") else Pass


@pytest.fixture
def canvas():
    return _Canvas(_Gui())


def _press(x=10, y=10, button=LEFT_BUTTON, clicks=1):
    return Event("press", x, y, button=button, clicks=clicks)


def test_the_chrome_that_takes_a_press_holds_the_pointer(canvas):
    assert canvas.router.capturer is None
    assert canvas.router.dispatch(_press()) is Consumed
    assert canvas.router.capturer is canvas._chrome_layer
    assert canvas._chrome_layer.captured
    assert canvas.camera == []


def test_a_press_the_chrome_declines_falls_through_to_the_camera_once():
    canvas = _Canvas(_Gui(takes=False))
    assert canvas.router.dispatch(_press()) is Consumed
    assert canvas.camera == ["press"]
    assert canvas.router.capturer is None


def test_the_drag_goes_to_the_chrome_and_never_to_the_camera(canvas):
    canvas.router.dispatch(_press())
    canvas.router.dispatch(Event("move", 400, 400, buttons=1))
    assert ("drag", 400.0, 400.0) in canvas._internal_gui.log
    assert canvas.camera == []


def test_a_move_nobody_holds_is_the_cameras(canvas):
    canvas.router.dispatch(Event("move", 400, 400, buttons=1))
    assert canvas.camera == ["move"]
    assert ("drag", 400.0, 400.0) not in canvas._internal_gui.log


def test_the_release_reaches_the_chrome_wherever_the_pointer_went(canvas):
    canvas.router.dispatch(_press())
    canvas.router.dispatch(Event("release", 5000, 5000, button=LEFT_BUTTON))
    assert canvas._internal_gui.log[-1] == ("release",)
    assert canvas.router.capturer is None
    assert not canvas._chrome_layer.captured
    # And the camera never saw a release for a gesture that was not its own.
    assert canvas.camera == []


def test_a_release_nobody_holds_is_the_cameras(canvas):
    canvas.router.dispatch(Event("release", 10, 10, button=LEFT_BUTTON))
    assert canvas.camera == ["release"]
    assert ("release",) not in canvas._internal_gui.log


def test_a_second_press_cancels_the_lost_release_then_routes(canvas):
    """BUGS/001 + BUGS/002: the DOM's `dblclick` is a press with no release."""
    canvas.router.dispatch(_press())
    canvas.router.dispatch(_press(clicks=2))
    kinds = [entry[0] for entry in canvas._internal_gui.log]
    assert kinds == ["press", "release", "press"]
    # The second press was routed like any other, so the chrome holds the
    # pointer again rather than being left with a capture it cannot end.
    assert canvas.router.capturer is canvas._chrome_layer


def test_a_press_the_chrome_declines_after_a_lost_release_reaches_the_camera():
    gui = _Gui()
    canvas = _Canvas(gui)
    canvas.router.dispatch(_press())
    gui.takes = False
    canvas.router.dispatch(_press(x=400, y=400))
    assert gui.log[1] == ("release",)          # the standing capture torn down
    assert canvas.camera == ["press"]          # and the press still got through


def test_the_grab_flag_reads_and_writes_the_one_slot(canvas):
    assert canvas._chrome_layer.captured is False
    canvas._chrome_layer.grab()
    assert canvas.router.capturer is canvas._chrome_layer
    canvas._chrome_layer.let_go()
    assert canvas.router.capturer is None
    assert canvas._chrome_layer.captured is False


def test_a_canvas_without_a_chrome_routes_straight_to_the_camera():
    canvas = _Canvas(None)
    assert canvas.router.dispatch(_press()) is Consumed
    assert canvas.camera == ["press"]
    assert canvas._chrome_layer.bounds() is None
    assert canvas._chrome_layer.visible is False


def test_the_layer_owns_the_whole_surface_not_only_what_it_draws(canvas):
    """A modal scrim takes presses it does not draw under; so does an unfocus."""
    assert canvas._chrome_layer.contains(5000, 5000)
    assert canvas._chrome_layer.bounds() == (0.0, 0.0, 800.0, 600.0)


def test_the_context_menu_takes_the_pointer_it_never_pressed_for(canvas):
    """It opens on a release, so nothing captured for it -- `grab()` does."""
    canvas.router.dispatch(Event("release", 10, 10, button=RIGHT_BUTTON))
    canvas._chrome_layer.grab()
    assert canvas.router.capturer is canvas._chrome_layer
    canvas.router.dispatch(Event("move", 20, 20, buttons=0))
    assert canvas.camera == ["release"]         # the move stayed with the menu
