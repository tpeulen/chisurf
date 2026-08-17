"""Draggable windows drawn inside the viewport.

The mechanism the rest of the UI work needs: chimol's panels are moving out of
Qt docks and into the scene so the desktop app and the browser run one code
path, and a panel that cannot be moved or folded is not a replacement for a
dock.

Behaviour is Dear ImGui's, taken from its source rather than from memory --
`junk/imgui/imgui.cpp`: a 32x32 floor, a 1-pixel border, a 4-pixel grab reach
outside the corner so a resize is catchable, and collapse on a double-click of
the title bar. The *look* only: chimol's chrome is retained, so the
immediate-mode core was deliberately not adopted.
"""
from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chimol.renderer.internal_gui import (  # noqa: E402
    GuiWindow,
    InternalGui,
)

SIZE = (780, 460)


@pytest.fixture
def gui():
    panel = InternalGui()
    panel.add_window(GuiWindow(key="map", title="Density", x=40, y=80,
                               w=300, h=170, lines=["Contour levels"]))
    panel.add_window(GuiWindow(key="hier", title="Hierarchy", x=380, y=150,
                               w=260, h=140, lines=["148l"]))
    panel.layout(*SIZE)
    return panel


def _zones(panel, key):
    win = panel.window(key)
    frame = panel.window_frame(win)
    title_y = frame.y + panel.WINDOW_TITLE_H / 2
    return {
        "title": (frame.x + frame.w / 2, title_y),
        "collapse": (frame.x + 4, title_y),
        "close": (frame.x + frame.w - 4, title_y),
        "resize": (frame.x + frame.w - 2, frame.y + frame.h - 2),
        "body": (frame.x + frame.w / 2, frame.y + frame.h / 2),
    }


def test_every_decoration_is_reachable(gui):
    """A decoration that is drawn and not hit-testable is one you cannot press."""
    expected = {"title": 0, "body": 1, "resize": 2, "collapse": 3, "close": 4}
    for name, (x, y) in _zones(gui, "hier").items():
        hit = gui.hit_test(x, y)
        assert hit.kind == "window", f"{name} is not reachable"
        assert hit.key == "hier"
        assert hit.row == expected[name], f"{name} reported row {hit.row}"


def test_a_click_on_the_scene_is_not_taken(gui):
    """The windows must not swallow the whole viewport."""
    assert gui.hit_test(120, 400).kind != "window"


def test_dragging_the_title_bar_moves_the_window(gui):
    x, y = _zones(gui, "map")["title"]
    win = gui.window("map")
    before = (win.x, win.y)

    assert gui.mouse_press(x, y)
    assert gui.is_dragging()
    assert gui.drag(x + 60, y + 40)
    gui.release()

    assert (win.x, win.y) == (before[0] + 60, before[1] + 40)
    assert not gui.is_dragging()


def test_the_corner_grip_resizes(gui):
    x, y = _zones(gui, "hier")["resize"]
    win = gui.window("hier")
    before = (win.w, win.h)

    gui.mouse_press(x, y)
    gui.drag(x + 50, y + 30)
    gui.release()

    assert win.w == pytest.approx(before[0] + 50)
    assert win.h == pytest.approx(before[1] + 30)


def test_a_window_declares_its_own_floor(gui):
    """`GuiWindow.min_h`/`min_w`: a panel's floor, honoured by the framework.

    Architecture-wide: the resize drag and the restored layout both clamp to
    the window's own minimum, never below the 32-pixel framework floor. A
    panel that knows the height its controls need (the density stack) sets
    it once, and no host can squeeze it past that.
    """
    gui.add_window(GuiWindow(key="tall", title="Tall", x=40, y=300,
                             w=200, h=200, min_h=140.0, min_w=150.0,
                             lines=["needs room"]))
    gui.layout(*SIZE)
    x, y = _zones(gui, "tall")["resize"]
    gui.mouse_press(x, y)
    gui.drag(x - 900, y - 900)
    gui.release()
    win = gui.window("tall")
    assert win.h == pytest.approx(140.0), "the drag went below the panel's floor"
    assert win.w == pytest.approx(150.0)
    # A restored layout that remembers a smaller size is clamped the same way.
    win.desired_h = 60.0
    win.h = 60.0
    gui.layout(*SIZE)
    assert win.h == pytest.approx(140.0), "the layout restored a size below the floor"
    # And a floor below the framework's is the framework's.
    gui.add_window(GuiWindow(key="tiny", title="Tiny", x=40, y=500,
                             w=200, h=100, min_h=10.0, lines=["x"]))
    gui.layout(*SIZE)
    x, y = _zones(gui, "tiny")["resize"]
    gui.mouse_press(x, y)
    gui.drag(x - 900, y - 900)
    gui.release()
    assert gui.window("tiny").h == pytest.approx(gui.WINDOW_MIN_H)


def test_a_window_cannot_be_shrunk_below_the_floor(gui):
    x, y = _zones(gui, "hier")["resize"]
    gui.mouse_press(x, y)
    gui.drag(x - 900, y - 900)
    gui.release()

    win = gui.window("hier")
    assert win.w == pytest.approx(gui.WINDOW_MIN_W)
    assert win.h == pytest.approx(gui.WINDOW_MIN_H)


def test_a_window_cannot_be_dragged_out_of_reach(gui):
    """There is no window manager underneath to get it back."""
    x, y = _zones(gui, "map")["title"]
    gui.mouse_press(x, y)
    gui.drag(x + 5000, y + 5000)
    gui.release()

    win = gui.window("map")
    frame = gui.window_frame(win)
    assert 0 <= win.x <= SIZE[0] - frame.w
    assert 0 <= win.y <= SIZE[1] - frame.h


def test_clicking_a_window_raises_it(gui):
    assert gui.windows[-1].key == "hier"
    x, y = _zones(gui, "map")["body"]
    gui.mouse_press(x, y)
    gui.release()
    assert gui.windows[-1].key == "map"


def test_the_front_window_wins_where_they_overlap(gui):
    """Two windows over one point: the click goes to the one on top."""
    top = gui.window("hier")
    bottom = gui.window("map")
    bottom.x, bottom.y, bottom.w, bottom.h = top.x, top.y, top.w, top.h
    gui.layout(*SIZE)

    hit = gui.hit_test(*_zones(gui, "hier")["body"])
    assert hit.key == "hier"


def test_collapse_folds_to_the_title_bar(gui):
    x, y = _zones(gui, "hier")["collapse"]
    gui.mouse_press(x, y)
    gui.release()

    win = gui.window("hier")
    assert win.collapsed
    assert gui.window_frame(win).h == pytest.approx(gui.WINDOW_TITLE_H)
    # The height is kept, so unfolding restores the size rather than a default.
    assert win.h == pytest.approx(140)
    assert gui.window_body(win).h == 0


def test_double_clicking_the_title_bar_collapses(gui):
    """ImGui's own gesture, and the one people try first."""
    x, y = _zones(gui, "hier")["title"]
    gui.mouse_press(x, y, double=True)
    gui.release()
    assert gui.window("hier").collapsed


def test_close_hides_the_window(gui):
    x, y = _zones(gui, "hier")["close"]
    gui.mouse_press(x, y)
    gui.release()

    assert not gui.window("hier").visible
    assert gui.hit_test(x, y).kind != "window", "a hidden window still takes clicks"


def test_windows_are_left_out_of_an_export(gui):
    """`png` saves a picture of the scene; a floating tool is not the molecule."""
    assert gui._window_hit(*_zones(gui, "hier")["title"]) is not None
    gui.draw_windows = False
    assert gui._window_hit(*_zones(gui, "hier")["title"]) is None

    drawn: list[str] = []

    class _Painter:
        def fill_rect(self, *a, **k):
            drawn.append("rect")

        def stroke_rect(self, *a, **k):
            drawn.append("rect")

        def text(self, *a, **k):
            drawn.append("text")

        def push_clip(self, *a, **k):
            pass

        def pop_clip(self, *a, **k):
            pass

    gui._paint_windows(_Painter())
    assert not drawn, "the windows were drawn into an export"


def test_the_mouse_window_is_wide_enough_for_its_own_title_row(gui):
    """The window is sized from its widest row, not from its widest-looking one.

    The mouse block has two rows competing for width: the binding grid, which
    needs a label column plus four button cells, and the *title* row, which
    needs a label column, one cell of right-aligned "Mouse Mode", and then the
    mode name beside it. The longest mode name is sixteen characters -- one
    more than the grid leaves -- so a width taken from the grid alone is a
    character short in nine of the ten modes.

    What that looked like is why this is asserted rather than eyeballed: the
    overflow was clipped at the window edge, so "3-Button Viewing" drew as
    "3-Button Viewin" and the ``Wheel`` heading lost its ``l``. It reads as a
    font or a rendering fault, not as a window one character too narrow, and it
    was present at *every* viewport size -- so no amount of resizing revealed
    it either.
    """
    from chimol.mouse_modes import MODE_NAMES
    from chimol.renderer.internal_gui import char_width

    gui.layout(900, 640)

    char_w = char_width(gui.FONT_PT)
    widest_mode = max(len(name) for name in MODE_NAMES.values())
    # label column + one cell + the longest mode name, plus the padding either
    # side -- the title row's own requirement, derived here independently of
    # the code under test.
    needed = gui.PAD + (10.0 + 5.0 + widest_mode) * char_w + gui.PAD

    # A hair of tolerance: `needed` is recomputed here from the same floats in
    # a different order, so it lands 2e-14 above the value under test.
    assert gui.mouse_window.w >= needed - 1e-9, (
        f"the mouse window is {gui.mouse_window.w:.1f}px but its title row "
        f"needs {needed:.1f}px, so the mode name is clipped"
    )


def test_a_window_opened_before_the_first_frame_keeps_its_size(gui):
    """The clamp must not fire against a viewport that does not exist yet.

    Every window is created before the frame it will be drawn in is laid out,
    so at that moment the chrome's remembered size is ``0 x 0``. ``layout_windows``
    clamped ``w``/``h`` **in place** against it, and the clamp only ever shrinks
    -- so a window opened at that instant collapsed to ``WINDOW_MIN_W`` at the
    origin and stayed there for the rest of the session, however large the
    window later became.

    What that looked like is why it took so long to find: the panel was drawn
    at its collapsed rectangle, so its close button was nowhere near where the
    user was clicking, and "nothing closes this window" was the symptom of a
    geometry bug rather than of the close paths, which were all working.
    """
    panel = GuiWindow(key="probe", title="Probe", x=24.0, y=90.0, w=420.0, h=300.0)
    gui.add_window(panel)

    gui.layout_windows(0, 0)            # the pre-first-frame viewport
    assert (panel.x, panel.y, panel.w, panel.h) == (24.0, 90.0, 420.0, 300.0)

    gui.layout_windows(900, 600)
    assert panel.w == 420.0, "a real viewport should leave the asked-for size alone"


def test_a_window_shrinks_to_fit_and_grows_back(gui):
    """Clamping is a view of the size, not a replacement for it.

    A narrow viewport must squeeze a window in, and widening it again must give
    the width back -- otherwise every transient narrow moment permanently
    shrinks the layout, which is the same defect as above arriving slowly.
    """
    panel = GuiWindow(key="probe", title="Probe", x=10.0, y=40.0, w=420.0, h=200.0)
    gui.add_window(panel)
    gui.layout_windows(900, 600)
    assert panel.w == 420.0

    gui.layout_windows(300, 600)
    assert panel.w < 420.0, "it must fit the narrow viewport"

    gui.layout_windows(900, 600)
    assert panel.w == 420.0, "and come back when there is room again"


def test_reset_windows_restores_the_authored_layout(gui):
    """The escape hatch for a layout that has gone wrong.

    Both halves matter: restoring the windows fixes this session, and clearing
    the saved states is what stops the bad layout returning on the next run,
    since a placement is re-applied from that file whenever a window is added.
    """
    panel = gui.window("map")
    panel.x, panel.y, panel.visible, panel.collapsed = -400.0, -400.0, False, True
    panel.anchor = None

    assert gui.reset_windows() >= 1
    assert (panel.x, panel.y) == (40.0, 80.0)
    assert panel.visible and not panel.collapsed
    assert gui._window_states == {}


def test_a_toolbar_button_reports_the_state_of_the_panel_it_opens(gui):
    """A toggle button has to answer for the panel, not for its own last press.

    Read from the panel, so the light stays honest when it is closed by other
    means -- Escape, a click outside, or its own close box -- which is exactly
    when a remembered press would lie.
    """
    gui.info_visible = False
    assert gui.toolbar_checked("info_panel toggle") is False
    gui.info_visible = True
    assert gui.toolbar_checked("info_panel toggle") is True

    # An action, not a state: it must say so rather than answering False.
    assert gui.toolbar_checked("open") is None

    # `Cfg` runs `config`, an alias for `settings_panel`; keyed on the command
    # the button actually runs.
    gui.add_window(GuiWindow(key="settings", title="Settings", visible=True))
    assert gui.toolbar_checked("config") is True
    gui.window("settings").visible = False
    assert gui.toolbar_checked("config") is False
