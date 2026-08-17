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

from chimol.plugins.dbg import window as dw
from chimol.render.frame_stats import FrameStats
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
    from chimol.commands import cmd

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
    from chimol.render.frame_stats import cpu_load

    _value, source = cpu_load()
    assert source in ("util", "load avg", "n/a")


def test_the_machine_line_is_assembled_from_the_standard_library():
    """No optional dependency, so it reads the same in a frozen build."""
    from chimol.render.frame_stats import machine_info

    assert machine_info()


def test_the_publishing_interval_is_slower_than_a_frame():
    """The module's own default keeps the historical contract.

    ``nerd_report_interval`` is what a running session actually reads (it is
    live-editable from the settings panel and ``set nerd_tick, ...``); this
    stays a check on the module's own default, unaffected by whatever a
    session has configured.
    """
    from chimol.render.frame_stats import REPORT_INTERVAL

    assert REPORT_INTERVAL >= 1.0 / 30.0


def test_the_live_interval_falls_back_to_the_default():
    """No config section, no key: the live getter still answers the default."""
    from chimol.core.settings.config import _DISPLAY_CONFIG
    from chimol.render.frame_stats import REPORT_INTERVAL, nerd_report_interval

    before = _DISPLAY_CONFIG.get("nerd")
    try:
        _DISPLAY_CONFIG.pop("nerd", None)
        assert nerd_report_interval() == pytest.approx(REPORT_INTERVAL)
    finally:
        if before is not None:
            _DISPLAY_CONFIG["nerd"] = before


def test_the_live_interval_is_clamped_to_the_floor():
    """A value typed too small in the panel cannot make the instrument
    dominate what it measures -- the whole point of a publishing interval."""
    from chimol.core.settings.config import _DISPLAY_CONFIG
    from chimol.render.frame_stats import MIN_REPORT_INTERVAL, nerd_report_interval

    before = dict(_DISPLAY_CONFIG.get("nerd") or {})
    try:
        _DISPLAY_CONFIG["nerd"] = {"tick_interval": 0.001}
        assert nerd_report_interval() == pytest.approx(MIN_REPORT_INTERVAL)
    finally:
        _DISPLAY_CONFIG["nerd"] = before


def test_the_live_interval_reads_a_configured_value():
    """A value inside the floor is honoured as-is."""
    from chimol.core.settings.config import _DISPLAY_CONFIG
    from chimol.render.frame_stats import nerd_report_interval

    before = dict(_DISPLAY_CONFIG.get("nerd") or {})
    try:
        _DISPLAY_CONFIG["nerd"] = {"tick_interval": 0.2}
        assert nerd_report_interval() == pytest.approx(0.2)
    finally:
        _DISPLAY_CONFIG["nerd"] = before


def test_nerd_lines_fit_the_fixed_width():
    """The "assert enough space" half of a fixed-width panel.

    `InternalGui._paint_nerd` no longer sizes the block to its longest
    current line -- reported directly as a panel that visibly resized under
    the reader while they were trying to read it. A fixed width only stays
    honest if something checks the content actually fits, so this stresses
    :meth:`FrameStats.lines` with the widest plausible values (a five-name
    pipeline list, three-digit millisecond figures, a long adapter/backend
    string, a six-digit instance count) and fails if any line would spill
    past the box -- a silent clip is a defect a person only ever notices by
    accident.
    """
    from chimol.chrome.gui import InternalGui

    stats = FrameStats()
    stats.enabled = True
    stats.frame_ms = 999.9
    stats.cpu_ms = 999.9
    stats.scene_ms = 999.9
    stats.chrome_ms = 999.9
    stats.last_draws = 999999
    stats.last_instances = 9_999_999
    stats.last_chrome_quads = 999999
    stats.last_chrome_bytes = 999999
    stats.last_objects = 9999
    stats.ambient_occlusion = "on"
    stats.pipelines = ("mesh", "chrome", "silhouette", "impostor", "text")
    stats.adapter = "AMD Radeon Pro W7900 Dual Slot Workstation Edition"
    stats.backend = "Metal"

    lines = stats.lines(fps=9999.9)
    # Inset by one char_w on each side (`_paint_nerd`'s `x + char_w`, box
    # width `width - char_w * 2`), so the usable room is two characters
    # narrower than the panel itself.
    usable = InternalGui.NERD_WIDTH_CHARS - 2
    overlong = [(len(one), one) for one in lines if len(one) > usable]
    assert not overlong, (
        f"NERD_WIDTH_CHARS ({InternalGui.NERD_WIDTH_CHARS}) is too narrow "
        f"for: {overlong}"
    )


# --------------------------------------------------------------------------
# The chrome
# --------------------------------------------------------------------------
def test_the_block_is_drawn_only_when_there_is_something_to_draw():
    """Off, or on with nothing published yet, must both draw nothing."""
    from chimol.chrome.gui import InternalGui

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
    from chimol.chrome.gui import InternalGui

    gui = InternalGui()
    gui.nerd = True
    gui.nerd_lines = ("one",)
    before = gui.chrome_fingerprint()
    gui.nerd_lines = ("two",)
    assert gui.chrome_fingerprint() != before


@pytest.mark.parametrize("lines", [("a",), ("a", "bb"), ("x" * 60, "y")])
def test_the_block_sizes_itself_to_its_longest_line(lines):
    """A plate narrower than its text is worse than no plate."""
    from chimol.chrome.gui import InternalGui

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


# --------------------------------------------------------------------------
# The keyboard: a window must never be able to take it away from the prompt
# --------------------------------------------------------------------------
def test_a_press_on_a_row_does_not_take_the_keyboard():
    """The regression this file exists to prevent.

    Focusing the panel on *any* press meant that clicking a row -- opening a
    panel, running a demo -- silently redirected every subsequent keystroke to
    an object that had nowhere to put it. The prompt stopped accepting text and
    nothing said why.
    """
    panel, _issued, _painter = _drawn("Panels")
    assert panel.wants_keys() is False


def test_the_panel_asks_for_keys_only_where_they_can_land():
    """Which is the Widgets tab, and only while a control is hosted."""
    panel, _issued, _painter = _drawn("Widgets")
    assert panel.wants_keys() is True
    panel.tab = dw.TABS.index("Frame")
    assert panel.wants_keys() is False


def test_a_focused_field_that_declines_a_key_lets_it_through():
    """"Not interested" and "nobody gets this" are different answers.

    The chrome used to return the field's answer either way, so a focused
    object that handled nothing was a black hole: Return never reached the
    command line and the viewport could not be typed into at all.
    """
    from chimol.hosts.keys import KEY_RETURN
    from chimol.chrome.gui import InternalGui

    class _Deaf:
        """A focusable object that consumes nothing."""

        def key(self, key, text="", modifiers=0) -> bool:
            """Decline every key."""
            return False

    gui = InternalGui()
    gui.command_line.visible = True
    gui.focus_field(_Deaf())
    assert gui.key_press(KEY_RETURN, "", 0) is True
    assert gui.command_line.focused is True


# --------------------------------------------------------------------------
# The graphs
# --------------------------------------------------------------------------
def _filled(frames: int = 30) -> FrameStats:
    """Stats carrying *frames* of plausible history."""
    stats = FrameStats()
    stats.enabled = True
    for index in range(frames):
        stats.frame_ms = 16.0 + (12.0 if index % 7 == 0 else 0.0)
        stats.scene_ms = 8.0
        stats.chrome_ms = 2.0
        stats.cpu_ms = 12.0
        stats.last_instances = 1000 + index
        stats._record()
    return stats


def test_history_is_only_kept_while_the_instrument_is_on():
    """An instrument nobody is reading must not accumulate either."""
    stats = FrameStats()
    stats.frame_ms = 16.0
    stats.begin()
    assert not any(stats.history[key] for key in stats.history)


def test_the_graphs_carry_one_sample_per_frame():
    """Averaged into the publishing interval, a single stutter disappears.

    That is the only reason to plot this rather than print a number, so the
    sampling has to stay per-frame even though the *snapshot* is taken twice a
    second.
    """
    stats = _filled(40)
    series = dict((key, samples) for key, _l, _u, samples in stats.graphs()
                  if key != "breakdown")
    assert len(series["fps"]) == 40
    assert len(series["frame_ms"]) == 40


def test_the_history_is_bounded():
    """A viewport left running for an hour must not grow a graph an hour long."""
    from chimol.render.frame_stats import HISTORY

    stats = _filled(HISTORY * 2)
    assert len(stats.graphs()[0][3]) == HISTORY


def test_the_snapshot_is_immutable():
    """A mutable series compares equal to itself after changing.

    The chrome caches on a fingerprint of what it draws, so handing it the live
    deques would freeze the graph at whatever it held when it was first read --
    and nothing would say so.
    """
    stats = _filled(5)
    first = stats.graphs()
    stats._record()
    assert stats.graphs() != first
    assert all(isinstance(one[3], tuple) for one in first)


def test_the_breakdown_carries_the_parts_that_add_up_to_the_frame():
    """Scene, chrome and wait, in the order they happen."""
    stats = _filled(5)
    breakdown = stats.graphs()[-1]
    assert breakdown[0] == "breakdown"
    assert [one[1] for one in breakdown[3]] == ["scene", "chrome", "wait"]


def test_a_stacked_graph_is_scaled_by_the_sum_not_the_tallest_part():
    """Scaling by the tallest part draws every bar off the top of the plot."""
    from chimol.chrome.gui import InternalGui

    gui = InternalGui()
    gui.layout(1200, 800)
    painter = RecordingPainter()
    graph = ("breakdown", "frame time", "ms", (
        ("scene_ms", "scene", (1, 2, 3), (10.0,)),
        ("chrome_ms", "chrome", (4, 5, 6), (10.0,)),
        ("wait_ms", "wait", (7, 8, 9), (10.0,)),
    ))
    gui._paint_nerd_graph(painter, 0.0, 0.0, 100.0, 12.0, graph)
    bars = [one for one in painter.fills if one[4] in ((1, 2, 3), (4, 5, 6), (7, 8, 9))]
    assert len(bars) == 3
    assert sum(one[3] for one in bars) <= gui.NERD_GRAPH_H + 0.5


def test_the_reference_lines_are_drawn_over_the_line():
    """Underneath they are hidden by the data they exist to be read against.

    A non-stacked graph (``fps`` here) is a real polyline through
    ``cmtk.begin_plot`` now, not a bar chart -- see
    ``InternalGui._paint_nerd_graph``'s docstring. The line is
    ``fill_triangle`` calls, the guide is still a ``fill_rect``, so draw order
    is read from ``RecordingPainter.calls`` (the one list every operation
    lands in, in order) rather than compared index-for-index within a single
    per-kind list the way the old bar-chart version of this test could.
    """
    from chimol.chrome.gui import InternalGui

    gui = InternalGui()
    gui.layout(1200, 800)
    painter = RecordingPainter()
    gui._paint_nerd_graph(
        painter, 0.0, 0.0, 100.0, 12.0,
        ("fps", "frame rate", "fps", (120.0, 55.0, 58.0)),
    )
    guide_colours = {colour for _v, colour in gui.NERD_GUIDES["fps"]}
    guide_indices = [
        i for i, call in enumerate(painter.calls)
        if call[0] == "fill_rect" and call[-1] in guide_colours
    ]
    line_indices = [i for i, call in enumerate(painter.calls) if call[0] == "fill_triangle"]
    assert guide_indices and line_indices
    assert min(guide_indices) > max(line_indices)


def test_a_graph_with_no_samples_still_draws_its_frame():
    """Before the first frame there is nothing to plot and something to say."""
    from chimol.chrome.gui import InternalGui

    gui = InternalGui()
    gui.layout(1200, 800)
    painter = RecordingPainter()
    gui._paint_nerd_graph(painter, 0.0, 0.0, 100.0, 12.0, ("fps", "rate", "fps", ()))
    assert "rate" in painter.strings


def test_the_block_grows_to_hold_its_graphs():
    """Drawn past the plate, the last graph is the one nobody sees."""
    from chimol.chrome.gui import InternalGui

    gui = InternalGui()
    gui.nerd = True
    gui.nerd_lines = ("one", "two")
    gui.layout(1400, 900)

    painter = RecordingPainter()
    gui._paint_nerd(painter)
    plain = painter.fills[0][3]

    gui.nerd_graphs = _filled(20).graphs()
    painter = RecordingPainter()
    gui._paint_nerd(painter)
    assert painter.fills[0][3] > plain


def test_the_first_cpu_reading_says_it_is_priming_rather_than_idle():
    """``cpu_percent`` measures since the previous call; the first has none.

    Reported as 0 %, that reads as an idle machine -- a wrong answer rather
    than a missing one.
    """
    import chimol.render.frame_stats as fs

    if not hasattr(fs, "_CPU_PRIMED"):
        pytest.skip("no psutil path")
    fs._CPU_PRIMED = False
    value, source = fs.cpu_load()
    assert source in ("priming", "load avg", "n/a")
    assert value == 0.0 or source != "priming"
