"""The wheel belongs to whatever the pointer is over.

It was a ladder in the *renderer*: is the pointer over an open menu? over the
info panel? over the sequence strip? over a window that happens to carry an
``on_wheel``? -- and anything not on that list dollied the molecule *behind*
the thing being pointed at. Two consequences, both reported: the wheel over an
editor zoomed the scene instead of scrolling the text, and whether a panel
scrolled at all depended on it having opted in.

The rule is one rule and it lives with the chrome, which is the only thing that
knows what is where: :meth:`InternalGui.wheel_at` asks its parts in the order
they are drawn and answers whether one of them took the notch. The camera is
what happens when none of them did.
"""

from __future__ import annotations

import pytest
from chimol.ui.gui import GuiRow, GuiWindow, InternalGui


def _gui(width: int = 900, height: int = 700) -> InternalGui:
    gui = InternalGui()
    gui.set_rows([GuiRow(name="all", is_header=True), GuiRow(name="thing")])
    gui.layout(width, height)
    return gui


def _panel(gui, key="panel", **kwargs):
    window = GuiWindow(key=key, title=key, x=60.0, y=90.0, w=260.0, h=180.0, **kwargs)
    gui.add_window(window)
    gui.layout(900, 700)
    return window


def test_a_window_body_takes_the_notch_even_with_nothing_to_scroll():
    """Otherwise the molecule moves behind the panel being pointed at."""
    gui = _gui()
    window = _panel(gui)
    body = gui.window_body(window)
    assert gui.wheel_at(body.x + 10, body.y + 10, -1) is True


def test_a_window_that_scrolls_is_given_the_notch():
    seen: list[int] = []
    gui = _gui()
    window = _panel(gui, on_wheel=lambda x, y, steps, rect: seen.append(steps) or True)
    body = gui.window_body(window)
    gui.wheel_at(body.x + 10, body.y + 10, -2)
    assert seen == [-2]


def test_a_body_that_declines_still_keeps_it():
    """A panel saying "not for me" is not the camera saying "mine"."""
    gui = _gui()
    window = _panel(gui, on_wheel=lambda x, y, steps, rect: False)
    body = gui.window_body(window)
    assert gui.wheel_at(body.x + 10, body.y + 10, -1) is True


def test_a_body_that_throws_does_not_hand_the_notch_to_the_camera():
    def angry(x, y, steps, rect):
        raise RuntimeError("no")

    gui = _gui()
    window = _panel(gui, on_wheel=angry)
    body = gui.window_body(window)
    assert gui.wheel_at(body.x + 10, body.y + 10, -1) is True


def test_the_object_list_takes_it():
    gui = _gui()
    body = gui.window_body(gui.objects_window)
    assert body.w > 0
    assert gui.wheel_at(body.x + 4, body.y + 4, -1) is True


def test_an_open_menu_keeps_every_notch():
    """Including one that lands beside the menu: the molecule must not move."""
    from chimol.ui.menus.bar import MenuEntry

    gui = _gui()
    gui.menubar = [("File", tuple(MenuEntry(f"Item {index}", "help") for index in range(40)))]
    gui.layout(900, 700)
    gui.open_menubar(0)
    assert gui.wheel_at(500.0, 400.0, -1) is True


def test_the_scene_gets_the_notch_when_the_pointer_is_on_the_scene():
    gui = _gui()
    for y in range(120, 660, 20):
        for x in range(20, 880, 20):
            if not gui.wheel_at(x, y, 0) and not gui.wants(x, y):
                return  # found somewhere the camera owns
    raise AssertionError("no part of the viewport is left for the camera")


def test_the_renderer_no_longer_keeps_a_list_of_the_chromes_parts():
    """The ladder is gone: the renderer asks one question."""
    import inspect

    from chimol.viewport.canvas import CanvasRenderer

    source = inspect.getsource(CanvasRenderer.on_wheel)
    assert "wheel_at" in source
    for gone in ("info_contains", "sequence_strip_contains", "wheel_window", "has_menu"):
        assert gone not in source, f"the renderer still knows about {gone}"


# --------------------------------------------------------------------------- #
# ...for every panel, not the ones somebody remembered
# --------------------------------------------------------------------------- #
EVERY_PANEL = """
app = open_app(size=(1200, 820))
cmd, gui, viewer = app.cmd, app.viewer.gui, app.viewer
cmd.do("load 148l.pdb")
cmd.do("panels_all on")
app.renderer._draw()

def view():
    return tuple(round(float(v), 4) for v in viewer.get_view_state())

leaked = []
scrolled = []
for win in list(gui.windows):
    if not win.visible or win.collapsed:
        continue
    body = gui.window_body(win)
    if body.w <= 0 or body.h <= 0:
        continue
    before = view()
    app.renderer.on_wheel(body.x + body.w / 2, body.y + body.h / 2, -1)
    if view() != before:
        leaked.append(win.key)
    if win.on_wheel is not None:
        scrolled.append(win.key)
emit("panels", ",".join(sorted(w.key for w in gui.windows if w.visible)))
emit("leaked", ",".join(sorted(leaked)) or "none")
emit("with_wheel", ",".join(sorted(scrolled)))
"""


@pytest.fixture(scope="module")
def every_panel():
    from toolkit_free import probe

    return probe(EVERY_PANEL, timeout=600)


def test_no_panel_lets_a_notch_reach_the_camera(every_panel):
    """The property, over every panel the viewer can open at once."""
    assert every_panel["panels"], "no panels were open, so this proves nothing"
    assert every_panel["leaked"] == "none", f"the molecule zoomed under: {every_panel['leaked']}"


def test_the_panels_that_scroll_take_the_notch_themselves(every_panel):
    """A list, a tree, a form and an editor all scroll; they all say so."""
    with_wheel = set(every_panel["with_wheel"].split(","))
    for key in ("objects", "hierarchy", "settings", "history"):
        assert key in with_wheel, f"{key} scrolls but never sees a wheel"
