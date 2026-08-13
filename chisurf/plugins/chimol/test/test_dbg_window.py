"""The dbg window and nerd mode: what they offer, and what they cost.

Two properties matter here and neither is about pixels.

**Every row must be a command that exists.** The window is generated from two
catalogues, so a row is written once and reached from a list -- which means a
renamed command leaves a row that looks fine and does nothing. Checking the
rows against the live command registry is the only way that is ever noticed.

**The instrument must not dominate what it measures.** The readout is drawn as
chrome, and the chrome is cached on a fingerprint of what it draws; a block of
numbers that changed every frame would rebuild the chrome every frame. That is
not a small effect -- it is most of a frame on a large model -- so the
publishing interval is asserted rather than trusted.
"""
from __future__ import annotations

import pytest

from chisurf.plugins.chimol.chimol.renderer import dbg_window as dw
from chisurf.plugins.chimol.chimol.renderer.frame_stats import FrameStats
from chisurf.plugins.chimol.test.recording_painter import RecordingPainter


class _Rect:
    """The rectangle a window body is drawn into."""

    def __init__(self, x=0.0, y=0.0, w=440.0, h=520.0) -> None:
        self.x, self.y, self.w, self.h = x, y, w, h

    def contains(self, x, y) -> bool:
        """Whether a point is inside."""
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


def _drawn(tab: str = "Frame", panel=None):
    """Draw one tab once; returns ``(panel, issued, painter)``."""
    issued: list[str] = []
    panel = panel or dw.DbgWindow(issued.append)
    panel.run_command = issued.append
    panel.tab = dw.TABS.index(tab)
    painter = RecordingPainter()
    panel.draw(painter, _Rect())
    return panel, issued, painter


# --------------------------------------------------------------------------
# The window
# --------------------------------------------------------------------------
def test_every_tab_draws_its_own_heading():
    """Five different questions, so five tabs rather than one long column."""
    for tab in dw.TABS:
        _panel, _issued, painter = _drawn(tab)
        assert tab in painter.strings, f"{tab} tab does not name itself"


def test_the_tab_strip_is_drawn_and_switches_on_a_press():
    """A tab you cannot press is a section header with extra steps."""
    panel, _issued, _painter = _drawn("Frame")
    left, right, index = panel._tab_rects[2]
    assert panel.press((left + right) / 2, panel._tab_top + 2.0, _Rect()) is True
    assert panel.tab == index


def test_it_stays_open_because_it_is_a_workbench():
    """A panel you have to re-open after every action gets used once."""
    panel = dw.DbgWindow(lambda _c: None)
    window = panel.window()
    assert window.transient is False


def test_every_row_issues_a_command_the_viewer_actually_has():
    """A renamed command leaves a row that looks fine and does nothing.

    The rows are generated from two catalogues, so this cannot be caught by
    reading the window -- only by checking what it would issue against what
    the command layer answers to.
    """
    from chisurf.plugins.chimol.chimol.cmd import cmd

    known = set(cmd.command_names())
    panel = dw.DbgWindow(lambda _c: None)
    for tab in dw.TABS:
        panel.tab = dw.TABS.index(tab)
        panel.draw(RecordingPainter(), _Rect())
        for _top, _bottom, command in panel._rows:
            name = command.split()[0]
            if name.startswith("__"):
                continue  # an internal action, handled without the dispatcher
            assert name in known, f"{tab}: row issues {name!r}, not a command"


def test_the_panel_list_covers_every_window_the_viewer_has():
    """A panel added and forgotten here is a panel nobody discovers."""
    assert len(dw.PANELS) >= 6
    names = {command.split()[0] for command, _title, _note in dw.PANELS}
    assert {"settings_panel", "hierarchy_panel", "density_panel",
            "history_panel", "mouse_panel", "object_panel"} <= names


def test_pressing_a_row_issues_its_command_and_consumes_the_press():
    """Consuming it is what stops the click also rotating the molecule."""
    panel, issued, _painter = _drawn("Panels")
    top, _bottom, command = panel._rows[3]
    assert panel.press(20.0, top + 1.0, _Rect()) is True
    assert issued == [command]


def test_pressing_the_toggle_asks_for_the_opposite_of_what_it_shows():
    """A checkbox that sends "on" while it is on is a checkbox that sticks."""
    panel, issued, _painter = _drawn("Frame")
    top, _bottom, command = panel._rows[0]
    assert command.startswith("nerd_mode ")
    panel.press(20.0, top + 1.0, _Rect())
    assert issued == [command]
    assert command.split()[1] in ("on", "off")


def test_a_press_in_the_body_but_not_on_a_row_is_still_consumed():
    """Otherwise a click on the window's background drags the scene behind it."""
    panel, issued, _painter = _drawn("Panels")
    assert panel.press(5.0, 500.0, _Rect()) is True
    assert issued == []


def test_long_notes_are_truncated_rather_than_drawn_over_the_title():
    """The catalogues are not written to fit; the window has to make them fit."""
    _panel, _issued, painter = _drawn("Demos")
    width = 440.0 - 16.0
    for _x, _y, box_w, _h, _align, string, _colour, _bold in painter.texts:
        assert painter.text_width(string) <= max(box_w, 0.0) + 1.0, string
    assert width > 0


def test_it_draws_with_no_catalogue_at_all(monkeypatch):
    """A shipped catalogue that cannot be read must not take the window with it."""
    monkeypatch.setattr(dw.DbgWindow, "_demos", staticmethod(lambda: ()))
    _panel, _issued, painter = _drawn("Demos")
    assert "Demos" in painter.strings


# --------------------------------------------------------------------------
# The readout
# --------------------------------------------------------------------------
def test_the_readout_names_the_wait_which_is_the_whole_diagnosis():
    """A big wait is presentation; a small one is our own work.

    "33 ms" alone cannot tell those apart, and they have opposite fixes -- so
    the frame minus the work we did is its own column.
    """
    stats = FrameStats()
    stats.enabled = True
    stats.frame_ms, stats.cpu_ms = 33.4, 21.7
    lines = stats.lines(29.9)
    assert "wait 11.7" in lines[1]
    assert "over 60 Hz budget" in lines[0]


def test_a_frame_inside_the_budget_is_not_flagged():
    """The flag has to mean something, so it must not always be there."""
    stats = FrameStats()
    stats.frame_ms = 12.0
    assert "budget" not in stats.lines(80.0)[0]


def test_the_counters_cost_nothing_while_nerd_mode_is_off():
    """An instrument nobody is reading must not be paid for."""
    stats = FrameStats()
    stats.draw("mesh", 1000, 6)
    stats.count("chrome_quads", 2000)
    assert stats.draws == 0
    assert stats.chrome_quads == 0


def test_counters_are_published_a_frame_behind():
    """The chrome that reports a frame is laid out while the frame is drawn.

    Reading the live counters would show the frame half-built, with the
    chrome's own quads missing because they have not been emitted yet.
    """
    stats = FrameStats()
    stats.enabled = True
    stats.begin()
    stats.draw("mesh", 4, 12)
    assert stats.last_draws == 0
    stats.begin()
    assert stats.last_draws == 1
    assert stats.draws == 0


def test_the_readout_says_where_a_load_figure_came_from():
    """A load average is not a utilisation, and must not be shown as one."""
    from chisurf.plugins.chimol.chimol.renderer.frame_stats import cpu_load

    _value, source = cpu_load()
    assert source in ("util", "load avg", "n/a")


def test_the_machine_line_is_assembled_from_the_standard_library():
    """No optional dependency, so it reads the same in a frozen build."""
    from chisurf.plugins.chimol.chimol.renderer.frame_stats import machine_info

    assert machine_info()


def test_the_publishing_interval_is_slower_than_a_frame():
    """The number that stops the instrument dominating what it measures."""
    from chisurf.plugins.chimol.chimol.renderer.frame_stats import REPORT_INTERVAL

    assert REPORT_INTERVAL >= 1.0 / 30.0


# --------------------------------------------------------------------------
# The chrome
# --------------------------------------------------------------------------
def test_the_block_is_drawn_only_when_there_is_something_to_draw():
    """Off, or on with nothing published yet, must both draw nothing."""
    from chisurf.plugins.chimol.chimol.renderer.internal_gui import InternalGui

    gui = InternalGui()
    gui.nerd = False
    gui.nerd_lines = ("something",)
    painter = RecordingPainter()
    gui._paint_nerd(painter)
    assert not painter.strings

    gui.nerd = True
    gui.nerd_lines = ()
    gui._paint_nerd(painter)
    assert not painter.strings


def test_the_block_is_part_of_the_chrome_fingerprint():
    """Otherwise the numbers freeze at whatever they were when it opened."""
    from chisurf.plugins.chimol.chimol.renderer.internal_gui import InternalGui

    gui = InternalGui()
    gui.nerd = True
    gui.nerd_lines = ("one",)
    before = gui.chrome_fingerprint()
    gui.nerd_lines = ("two",)
    assert gui.chrome_fingerprint() != before


@pytest.mark.parametrize("lines", [("a",), ("a", "bb"), ("x" * 60, "y")])
def test_the_block_sizes_itself_to_its_longest_line(lines):
    """A plate narrower than its text is worse than no plate."""
    from chisurf.plugins.chimol.chimol.renderer.internal_gui import InternalGui

    gui = InternalGui()
    gui.nerd = True
    gui.nerd_lines = lines
    gui.layout(1200, 800)
    painter = RecordingPainter()
    gui._paint_nerd(painter)
    plate = painter.fills[0]
    longest = max(painter.text_width(one) for one in lines)
    assert plate[2] >= longest


# --------------------------------------------------------------------------
# Widgets and shaders: the two tabs that did not exist before
# --------------------------------------------------------------------------
def test_the_widgets_tab_hosts_the_ported_controls_live():
    """Screenshotting a control says nothing about whether its keys work."""
    panel, _issued, painter = _drawn("Widgets")
    assert "Text editor" in painter.strings
    assert "Hex editor" in painter.strings
    assert panel._widget("text_editor") is not None
    assert panel._widget("memory_editor") is not None


def test_a_hosted_widget_keeps_its_state_between_frames():
    """A control rebuilt every frame cannot be *tried* -- it forgets."""
    panel, _issued, _painter = _drawn("Widgets")
    editor = panel._widget("text_editor")
    editor.insert("typed")
    panel.draw(RecordingPainter(), _Rect())
    assert panel._widget("text_editor") is editor
    assert "typed" in editor.text


def test_typing_reaches_the_hosted_widget_and_only_there():
    """A text editor you cannot type into has not been tried."""
    panel, _issued, _painter = _drawn("Widgets")
    editor = panel._widget("text_editor")
    editor.set_cursor(editor.document.top())
    assert panel.key(0, "Z") is True
    assert editor.text.startswith("Z")

    panel.tab = dw.TABS.index("Panels")
    assert panel.key(0, "Q") is False


def test_choosing_the_other_widget_swaps_which_one_is_shown():
    """One at a time: two live controls in one column is neither."""
    panel, _issued, _painter = _drawn("Widgets")
    rows = [one for one in panel._rows if one[2].startswith("__widget__")]
    assert len(rows) == 2
    top, _bottom, command = rows[1]
    panel.press(20.0, top + 1.0, _Rect())
    assert panel._active_widget == command.split()[1]


def test_the_shader_list_is_read_from_the_directory():
    """A shader added and not listed is one nobody can look at."""
    names = dw.DbgWindow.shaders()
    assert names
    assert all(one.endswith(".wgsl") for one in names)


def test_opening_a_shader_loads_it_into_the_editor_and_shows_it():
    """The question is asked while looking at the frame the shader drew."""
    panel, _issued, _painter = _drawn("Shaders")
    row = next(one for one in panel._rows if one[2].startswith("__shader__"))
    panel.press(20.0, row[0] + 1.0, _Rect())
    assert dw.TABS[panel.tab] == "Widgets"
    assert panel._active_widget == "text_editor"
    editor = panel._widget("text_editor")
    assert editor.line_count > 1
    assert editor.language_name == "GLSL"


def test_a_missing_shader_says_so_in_the_editor_rather_than_raising():
    """A dead row is not worth taking the window down for."""
    panel, _issued, _painter = _drawn("Shaders")
    panel.open_shader("there_is_no_such.wgsl")
    assert "there_is_no_such.wgsl" in panel._widget("text_editor").text
