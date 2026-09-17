"""A panel is told where the pointer is, not only where it was pressed.

The chrome dispatched presses, drags, releases, wheels, double-clicks and keys
into window bodies -- and never hover. The dbg window carried a `hover()`
method that nothing had ever called, which is the shape this kind of gap takes:
the panel is written as though the hook exists and the hook does not.

It matters as soon as a panel means to *show* something about whatever is under
the cursor. The labelling network highlights the dye cloud and the distance
lines of the position being hovered, in the 3-D view, which cannot be done from
presses: pressing a position would also mean something else, and a highlight
that needs a click is a highlight nobody finds.

Two properties, and the second is the one that is easy to get wrong: every
window that asked is told, whether or not the pointer is over it, so a panel
can put out what it lit up when the pointer leaves. Told only about pointers
inside itself, the last thing hovered stays lit for ever.
"""

from __future__ import annotations

from chimol.ui.gui import GuiWindow, InternalGui


def _gui() -> InternalGui:
    gui = InternalGui()
    gui.layout(800, 600)
    return gui


def test_a_window_body_is_told_where_the_pointer_is():
    seen: list[tuple] = []
    gui = _gui()
    gui.add_window(
        GuiWindow(
            key="panel",
            title="Panel",
            x=40.0,
            y=40.0,
            w=200.0,
            h=120.0,
            on_hover=lambda x, y, rect: seen.append((x, y)) or False,
        )
    )
    gui.mouse_move(80.0, 90.0)
    assert seen == [(80.0, 90.0)]


def test_it_is_told_about_pointers_outside_it_as_well():
    """So it can put out whatever it lit up."""
    seen: list[tuple] = []
    gui = _gui()
    gui.add_window(
        GuiWindow(
            key="panel",
            title="Panel",
            x=40.0,
            y=40.0,
            w=200.0,
            h=120.0,
            on_hover=lambda x, y, rect: seen.append((x, y)) or False,
        )
    )
    gui.mouse_move(700.0, 500.0)
    assert seen == [(700.0, 500.0)], "a panel that lights things up is never told to stop"


def test_the_body_rect_is_the_one_presses_get():
    """Hit-testing hover and press against different rectangles is a bug factory."""
    rects: list = []
    gui = _gui()
    window = GuiWindow(
        key="panel",
        title="Panel",
        x=40.0,
        y=40.0,
        w=200.0,
        h=120.0,
        on_hover=lambda x, y, rect: rects.append(rect) or False,
    )
    gui.add_window(window)
    gui.mouse_move(80.0, 90.0)
    assert rects and rects[0] == gui.window_body(window)


def test_a_panel_asking_for_a_repaint_gets_one():
    gui = _gui()
    gui.add_window(
        GuiWindow(
            key="panel",
            title="Panel",
            x=40.0,
            y=40.0,
            w=200.0,
            h=120.0,
            on_hover=lambda x, y, rect: True,
        )
    )
    assert gui.mouse_move(80.0, 90.0) is True


def test_a_panel_that_throws_does_not_take_the_frame_with_it():
    def angry(x, y, rect):
        raise RuntimeError("no")

    gui = _gui()
    gui.add_window(
        GuiWindow(key="panel", title="Panel", x=40.0, y=40.0, w=200.0, h=120.0, on_hover=angry)
    )
    gui.mouse_move(80.0, 90.0)  # must not raise


def test_a_hidden_window_is_not_told():
    seen: list = []
    gui = _gui()
    gui.add_window(
        GuiWindow(
            key="panel",
            title="Panel",
            x=40.0,
            y=40.0,
            w=200.0,
            h=120.0,
            visible=False,
            on_hover=lambda x, y, rect: seen.append(1) or False,
        )
    )
    gui.mouse_move(80.0, 90.0)
    assert seen == []
