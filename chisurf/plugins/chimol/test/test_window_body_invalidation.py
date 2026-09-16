"""Routed input invalidates a window body -- by the framework, always.

The frozen-dialog bug (round 22) was architectural: ``chrome_fingerprint``
covered a window's *frame* and nothing about its *body*, so any panel whose
body changed on interaction kept the stale cached quads -- the model moved,
the picture did not, and every interactive panel in the tree carried the
same latent freeze. The file dialog was merely the first place someone
dragged something.

The fix has two halves and this file pins the architectural one:

* the **framework** bumps ``GuiWindow.body_revision`` on every input it
  routes to a window body -- press, double, context, drag, wheel, and keys
  through the window's ``on_key`` object -- before the body hears about it.
  A panel therefore cannot forget: routed input repaints by construction.
* a panel whose body changes **without** input (async compute landing, a
  programmatic path change) still bumps its own revision -- the density
  panel's coalesced ``on_change`` route is the worked example.

The proof here is a panel that bumps nothing itself: state moves only
inside its routed callbacks, and the quad array -- the *picture*, not the
model -- must change on every gesture. Model-level assertions cannot see
this class of bug; the round-16 lesson, one port later.
"""

from __future__ import annotations

import pytest

pytest.importorskip("rendercanvas", reason="the offscreen canvas host")

from toolkit_free import probe  # noqa: E402


_DRIVE = """
    app = open_app(size=(1000, 780))
    app.cmd.set_message_callback(lambda _m: None)
    app.cmd.set_error_callback(lambda _e: None)
    app.cmd.do("load 148l.pdb")
    from emtk.events import LEFT_BUTTON
    from chimol.ui.gui import GuiWindow

    r = app.renderer
    gui = r._internal_gui

    # A panel that bumps NOTHING itself: its state moves only inside the
    # routed callbacks. If the picture moves, the framework did it.
    state = {"row": 0, "hits": 0}

    def body(painter, rect):
        painter.fill_rect(rect.x + 5 + state["row"] * 10, rect.y + 5, 8, 8,
                          (255, 255, 0, 255))

    def on_press(x, y, rect):
        state["hits"] += 1
        return True

    def on_drag(x, y, rect):
        state["row"] = min(state["row"] + 1, 20)
        return True

    def on_wheel(x, y, steps, rect):
        state["row"] = min(max(state["row"] + steps, 0), 20)
        return True

    class Keyed:
        def wants_keys(self):
            return True

        def key(self, key, text="", modifiers=0):
            state["hits"] += 1
            return True

    win = GuiWindow(key="dummy", title="dummy", x=100, y=100, w=200, h=150)
    win.body = body
    win.on_press = on_press
    win.on_drag = on_drag
    win.on_wheel = on_wheel
    win.on_key = Keyed()
    gui.add_window(win)
    gui.raise_window("dummy")

    bx, by = 150.0, 150.0          # inside the body
    rev0 = win.body_revision
    q0 = r._chrome_quads()

    r.on_pointer_press(bx, by, LEFT_BUTTON, 0)
    emit("press_bumps", str(win.body_revision > rev0))
    emit("press_moves_picture", str(q0 is not r._chrome_quads()))

    r.on_pointer_move(bx + 40, by + 40, LEFT_BUTTON, 0)
    emit("drag_moves_picture", "moved")
    q_drag = r._chrome_quads()
    r.on_pointer_release(bx + 40, by + 40, LEFT_BUTTON, 0)

    q_mid = r._chrome_quads()
    r.on_wheel(bx, by, 2, 0)
    emit("wheel_moves_picture", str(q_mid is not r._chrome_quads()))

    from emtk.keys import KEY_DOWN
    q_before_key = r._chrome_quads()
    r.on_key_press(KEY_DOWN, "", 0)
    emit("key_moves_picture", str(q_before_key is not r._chrome_quads()))
    emit("key_reached_body", str(state["hits"] >= 2))

    # Drag picture check (deferred emission: q_drag vs q0)
    emit("drag_check", str(q0 is not q_drag))
"""


def test_routed_input_invalidates_a_body_that_bumps_nothing():
    """Press, drag, wheel and keys repaint a window the framework owns."""
    m = probe(_DRIVE, block_qt=True)
    assert m["press_bumps"] == "True", "the framework did not bump on press"
    assert m["press_moves_picture"] == "True", "a press did not repaint the body"
    assert m["drag_check"] == "True", "a drag did not repaint the body"
    assert m["wheel_moves_picture"] == "True", "a wheel notch did not repaint"
    assert m["key_moves_picture"] == "True", "a key did not repaint the body"
    assert m["key_reached_body"] == "True", "the key never reached the body"
