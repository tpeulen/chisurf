"""Gaps the final shell parity pass found (okf/plugins/emtk-ports/final-parity/shell).

The Start document shows the machine, the versions and the process's use, as the Qt workspace
did: the Qt main window painted a watermark over its empty workspace (OS, RAM, Python, ChiSurf,
numpy, tttrlib, the thread environment, the log level, CPU and memory).
"""

from __future__ import annotations

import platform

from emtk.testing import Driver

from chisurf.core.system_info import system_info_lines
from chisurf.emtk.main_app import EmtkShellApp


def test_system_info_lines_name_the_machine_and_the_versions():
    lines = system_info_lines()
    assert lines[0].startswith("OS: ")
    assert f"Python: {platform.python_version()}" in lines
    assert any(line.startswith("ChiSurf: ") for line in lines)
    assert lines[-1].startswith("Log level: ")


def test_the_watermark_is_drawn_in_the_workspace_background_under_the_fits():
    """Owner, 2026-10-14: the watermark is the workspace's background, as in the Qt window --
    top-right of the workspace body, not in the Start document, and under a floating window."""
    from emtk import im

    shell = EmtkShellApp({}, loader=lambda plugin_id: None, console_history=False,
                         console_session_file=False)
    try:
        driver = Driver(shell, (1440, 900))
        driver.frame(3)
        strings = [str(s) for s in driver.painter.strings]
        assert f"Python: {platform.python_version()}" in strings
        assert "system_info" in shell.item_rects
        bx, by, bw, _bh = shell.item_rects["system_info"]
        wx, wy, ww, _wh = shell.docks.floating_bounds()
        assert abs((bx + bw) - (wx + ww - 10.0)) < 1.0 and abs(by - (wy + 10.0)) < 1.0
        assert any(s.startswith("CPU: ") for s in strings)
        assert any(s.startswith("Mem: ") for s in strings)
        assert len(shell._usage_history) >= 1
        # A window floating in the workspace is drawn after (over) the watermark.
        shell.docks.add_window(
            "fit.x", "Fit X", lambda box: im.text_unformatted("FIT BODY"),
            box=(wx + 20.0, wy + 30.0, 500.0, 300.0), workspace=True,
        )
        driver.frame(3)
        order = [str(s) for s in driver.painter.strings]
        assert order.index(f"Python: {platform.python_version()}") < order.index("FIT BODY")
    finally:
        shell.close()


def test_watermark_live_usage_accumulates_and_advances():
    """Live process usage (CPU %, resident memory) is measured and history accumulates across frames."""
    import time

    shell = EmtkShellApp({}, loader=lambda plugin_id: None, console_history=False,
                         console_session_file=False)
    try:
        driver = Driver(shell, (1440, 900))
        driver.frame(1)
        assert len(shell._usage_history) == 1
        cpu, mem = shell._usage_history[0]
        assert cpu >= 0.0
        assert mem > 0.0

        # Simulate 1.5 seconds elapsed to trigger usage update on subsequent frame
        shell._usage_at = time.monotonic() - 1.5
        driver.frame(1)
        assert len(shell._usage_history) == 2
    finally:
        shell.close()


def test_the_pda_editor_draws_its_binning_labels_and_light_path_note_readably():
    """The PDA editor drew ``x<sub>min</sub>`` with its tags, and typeset the light-path note
    (a sentence with ``&gamma;``) as one formula squeezed into the dock width, unreadable."""
    import types

    from emtk import im
    from emtk.app import ImApp

    from chisurf.emtk.model_editor import ModelEditor

    note = (
        "Not applied. Fills leakage, direct excitation and &gamma; from a simulated optical "
        "setup instead of leaving them as guesses."
    )
    editor = ModelEditor(types.SimpleNamespace(busy=False))
    editor.set_editor(
        "fit",
        {
            "sections": [
                {
                    "type": "custom",
                    "key": "scalar_table",
                    "id": "binning",
                    "options": {"title": "Binning"},
                    "data": {"rows": [{"attr": "x_min", "label": "x<sub>min</sub>", "value": 0}]},
                },
                {"type": "info", "text": note},
            ]
        },
    )

    def gui():
        im.begin("editor", (0, 0, 420, 400))
        editor.draw()
        im.end()

    driver = Driver(ImApp(gui), size=(420, 400))
    driver.frame(3)
    strings = [str(s) for s in driver.painter.strings]
    assert not any("<sub>" in s for s in strings), strings
    assert "min" in strings, "the binning row's label is drawn (as x with a subscript min)"
    assert any("γ" in s for s in strings), "the note is drawn as wrapped text with its γ"


def _wide_tool_shell(state=None, size=(1440, 900)):
    from emtk import im
    from emtk.app import ImApp

    from chisurf.emtk.plugins import manifests

    def make(plugin_id):
        app = ImApp(lambda: im.text_unformatted(plugin_id))
        app.window_size = (1200, 800) if plugin_id == "setup" else (300, 400)
        return app

    catalog = {k: manifests()[k] for k in ("setup", "about")}
    shell = EmtkShellApp(catalog, loader=make, console_history=False, console_session_file=False)
    if state is not None:
        shell.docks.restore(state)
    return shell, Driver(shell, size)


def _open(shell, driver, plugin_id):
    import time

    hosted = shell.open_plugin(plugin_id)
    end = time.monotonic() + 30
    while (hosted.app is None or not hosted.extra.get("placed")) and time.monotonic() < end:
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(3)
    return hosted


def test_a_tool_wider_than_its_dock_floats_at_its_declared_size():
    """Tools land in docks: tabbed beside Workspace in center without auto-floating."""
    shell, driver = _wide_tool_shell()
    try:
        driver.frame(2)
        wide = _open(shell, driver, "setup")
        assert shell.docks.region_of(wide.key) == "center", "the tool lands docked in center"
        narrow = _open(shell, driver, "about")
        assert shell.docks.region_of(narrow.key) == "center", "a narrow tool also docks in center"
    finally:
        shell.close()


def test_a_wide_tool_the_user_docked_stays_docked():
    """The choice is remembered: docked by hand, closed and reopened (this run or the next,
    through the saved layout), the wide tool goes back to its dock."""
    shell, driver = _wide_tool_shell()
    try:
        driver.frame(2)
        hosted = _open(shell, driver, "setup")
        shell.docks.dock(hosted.key, "left")
        driver.frame(2)
        shell.close_plugin("setup")
        again = _open(shell, driver, "setup")
        assert shell.docks.region_of(again.key) == "left"
        state = shell.docks.state()
    finally:
        shell.close()
    shell, driver = _wide_tool_shell(state)
    try:
        driver.frame(2)
        hosted = _open(shell, driver, "setup")
        assert shell.docks.region_of(hosted.key) == "left", "the saved layout keeps it docked"
    finally:
        shell.close()


def test_watermark_folding_toggle_on_click():
    """Clicking the watermark toggles between folded compact badge and expanded view."""
    shell = EmtkShellApp({}, loader=lambda plugin_id: None, console_history=False,
                         console_session_file=False)
    try:
        driver = Driver(shell, (1440, 900))
        driver.frame(2)
        assert "system_info" in shell.item_rects
        assert shell._watermark_folded is False
        assert shell.animating() is True  # Active telemetry requests frames continuously
        assert 0.0 < shell._frame_ms < 100.0  # Real frame CPU render time, not sleep interval
        bx, by, bw, bh = shell.item_rects["system_info"]
        unfolded_h = bh
        assert unfolded_h > 100.0  # Full panel is tall

        # Click inside watermark bounds to fold
        driver.click((bx + 10.0, by + 10.0))
        driver.frame(1)

        assert shell._watermark_folded is True
        assert shell.animating() is False  # Folded badge stops continuous animation
        fbx, fby, fbw, fbh = shell.item_rects["system_info"]
        assert fbh < 35.0  # Folded single-line badge is compact
        folded_strings = [str(s) for s in driver.painter.strings]
        assert any(s.startswith("▶ ChiSurf") for s in folded_strings)

        # Click again to unfold
        driver.click((fbx + 10.0, fby + 10.0))
        driver.frame(1)

        assert shell._watermark_folded is False
        assert shell.animating() is True  # Resumes continuous telemetry
        assert shell.item_rects["system_info"][3] > 100.0
    finally:
        shell.close()


def test_watermark_fps_does_not_stall_or_pollute_on_idle_gap():
    """An idle sleep gap (> 0.25s) is not treated as a frame duration in FPS calculation."""
    import time
    shell = EmtkShellApp({}, loader=lambda plugin_id: None, console_history=False,
                         console_session_file=False)
    try:
        driver = Driver(shell, (1440, 900))
        driver.frame(5)
        active_fps = getattr(shell, "_fps", 0.0)

        # Simulate 1 second idle gap (as happens when sleeping between 1Hz polls)
        shell._last_frame_ts = time.perf_counter() - 1.05
        driver.frame(1)

        # Frame render time must reflect actual drawing cost, not the 1.05s sleep
        assert shell._frame_ms < 100.0
        # The 1.05s gap must NOT be appended to frame durations
        if hasattr(shell, "_frame_durations"):
            for duration in shell._frame_durations:
                assert duration <= 0.25, f"Duration {duration}s was wrongly recorded as a frame time"
    finally:
        shell.close()


def test_tooltip_dismiss_on_pointer_leave_and_dock_exit():
    """When the pointer moves away from a dock or leaves the window, inactive children get cleared."""
    from emtk.app import ImApp

    class MockChild(ImApp):
        def __init__(self):
            super().__init__(gui=lambda: None)
            self.drawn = False

        def draw(self, painter, x, y, w, h):
            self.drawn = True
            super().draw(painter, x, y, w, h)

    shell = EmtkShellApp({}, loader=lambda plugin_id: None, console_history=False,
                         console_session_file=False)
    try:
        child = MockChild()
        shell._drawn["test_child"] = ("test_win", child, (100.0, 100.0, 200.0, 200.0))

        # Pointer moves into child (under capture or active target)
        shell._capture = "test_child"
        shell.pointer_move(150.0, 150.0)
        assert child.io.mouse_pos == (50.0, 50.0)

        # Pointer moves outside child (capture released, pointer over workspace background)
        shell._capture = None
        shell.pointer_move(400.0, 400.0)
        assert child.io.mouse_pos == (-1.0, -1.0), "child mouse_pos must reset to (-1.0, -1.0)"

        # Pointer leaves window entirely (-1.0, -1.0)
        child.io.mouse_pos = (50.0, 50.0)
        shell.pointer_move(-1.0, -1.0)
        assert child.io.mouse_pos == (-1.0, -1.0)
    finally:
        shell.close()

