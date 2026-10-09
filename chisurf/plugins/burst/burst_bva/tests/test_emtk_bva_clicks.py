"""Real-input coverage of the native BVA tool: every control is operated with simulated pointer, keyboard and host events.

Only ``pointer_move`` / ``press`` / ``release`` / ``drag`` / ``wheel`` / ``key`` and the host's ``files_dropped`` reach the
window, at the rectangles the controls were drawn in (``app.item_rects``) or at the text a button drew; the assertions read
the visible outcome (the model, the status line, the drawn strings, the files written). The control -> test list is in
``okf/plugins/emtk-ports/burst_bva/REPORT.md`` section 6a.
"""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from emtk import keys
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.burst_2cde.tests.demo_folder import build
from chisurf.plugins.burst.burst_bva.core import computation as core
from chisurf.plugins.burst.burst_bva.gui.app import create_app

from .test_emtk_bva_parity import _qt_facts, _std

SIZE = (1200, 800)
SMALL = (800, 600)
CTRL_A = 0x04000000


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))


@pytest.fixture
def measurement(tmp_path):
    return build(tmp_path / "measurement")  # <tmp>/measurement/burstwise


@pytest.fixture
def app():
    window = create_app()
    window.model.auto_update = False
    window.model.donor_channels_text, window.model.acceptor_channels_text = "0", "1"
    yield window
    window.close()


def draw(app, size=SIZE, frames=2):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def settle(app, size=SIZE, timeout=90.0):
    """Draw frames until the computation (and a queued second one) has been delivered."""
    end = time.monotonic() + timeout
    draw(app, size, frames=1)
    while app.controller.running and time.monotonic() < end:
        time.sleep(0.02)
        draw(app, size, frames=1)
    assert not app.controller.running
    return draw(app, size, frames=1)


def click(app, rect, size=SIZE, fx=0.5, clicks=1):
    """Press and release the pointer on *rect* (a frame is drawn between, as a host does)."""
    x, y, w, h = rect
    app.pointer_move(x + w * fx, y + h / 2)
    draw(app, size, frames=1)
    app.press(x + w * fx, y + h / 2, clicks=clicks)
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=1)


def text_rect(painter, label, last=True):
    hits = [t[:4] for t in painter.texts if t[5] == label]
    assert hits, f"{label!r} is not drawn: {[t[5] for t in painter.texts][:60]}"
    return hits[-1] if last else hits[0]


def press(app, name, size=SIZE):
    draw(app, size)
    click(app, app.item_rects[name], size)


def type_into(app, name, text, size=SIZE, enter=True):
    """Click the field, select its content, type, and press Enter."""
    draw(app, size)
    click(app, app.item_rects[name], size, fx=0.3)
    assert app.io.want_capture_keyboard, f"{name} did not take the keyboard"
    app.key(0x41, "a", CTRL_A)
    draw(app, size, frames=1)
    for ch in text:
        app.key(ord(ch), ch)
        draw(app, size, frames=1)
    if enter:
        app.key(keys.KEY_RETURN, "\r")
        draw(app, size, frames=2)


def drag_field(app, name, dx, size=SIZE, steps=6):
    """Press on a drag field and move the pointer sideways by *dx* pixels in *steps* moves."""
    draw(app, size)
    x, y, w, h = app.item_rects[name]
    cx, cy = x + w / 2, y + h / 2
    app.pointer_move(cx, cy)
    draw(app, size, frames=2)
    app.press(cx, cy)
    draw(app, size, frames=1)
    for step in range(1, steps + 1):
        app.drag(cx + dx * step / steps, cy)
        draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=2)


def run_and_wait(app, folder):
    app.model.set_folder(folder)
    press(app, "run")
    return settle(app)


def tab(app, name, size=SIZE):
    draw(app, size)
    click(app, app.item_rects[name], size)


# -- the action row --------------------------------------------------------------------------------------------- #


def test_run_click_computes_bva_as_the_qt_tool_did_and_writes_the_companions(
    app, measurement, tmp_path
):
    """Folder typed into its field, Run clicked: the per-burst Std equals the Qt tool's on the same folder."""
    qt = _qt_facts(build(tmp_path / "qt_a"), build(tmp_path / "qt_b", seed=9))
    type_into(app, "folder_path", str(measurement), enter=False)
    assert app.model.analysis_folder == measurement
    press(app, "run")
    assert app.model.is_running and "Reading burst data …" in draw(app).strings
    settle(app)
    assert _std(app.model.df) == pytest.approx(np.asarray(qt["first"]), nan_ok=True)
    assert app.model.status_text == qt["status"]
    assert "Done – 60 bursts with Std > 0 on 60 total" in draw(app).strings
    assert sorted(p.name for p in (measurement / "bv4").glob("*")) == qt["companions"]


def test_run_without_a_folder_says_so_in_the_window(app):
    press(app, "run")
    assert app.model.df is None
    assert "Select a data folder first." in draw(app).strings


def test_a_second_run_is_unchanged_and_points_at_restart_whose_click_recomputes(app, measurement):
    run_and_wait(app, measurement)
    first = app.model.df
    press(app, "run")
    assert "Unchanged — kept the previous BVA result" in " ".join(
        draw(app).strings
    )  # the status wraps
    assert app.model.restart_attention and app.model.df is first and not app.controller.running
    press(app, "restart")
    assert app.model.is_running
    settle(app)
    assert app.model.df is not first and not app.model.restart_attention
    assert app.model.status_text.startswith("Done – 60 bursts")


def test_stop_click_cancels_the_running_computation_and_run_then_computes(
    app, measurement, monkeypatch
):
    gate = threading.Event()
    original = core.compute_bva
    monkeypatch.setattr(core, "compute_bva", lambda *a, **k: (gate.wait(20), original(*a, **k))[1])
    app.model.set_folder(measurement)
    press(app, "run")
    draw(app, frames=1)
    assert app.controller.running
    assert app.next_frame_in() is not None  # frames keep coming while it runs
    press(app, "stop")
    assert app.model.status_text == "Stopping the BVA analysis …"
    gate.set()
    settle(app)
    assert app.model.df is None and app.model.status_text == "BVA cancelled."
    assert "BVA cancelled." in draw(app).strings
    press(app, "run")
    settle(app)
    assert app.model.df is not None


def test_stop_does_nothing_when_idle_and_run_and_restart_do_nothing_while_running(
    app, measurement, monkeypatch
):
    press(app, "stop")  # idle: no computation to stop
    assert app.model.status_text == "Ready" and not app.controller.running
    gate = threading.Event()
    original = core.compute_bva
    monkeypatch.setattr(core, "compute_bva", lambda *a, **k: (gate.wait(20), original(*a, **k))[1])
    app.model.set_folder(measurement)
    press(app, "run")
    draw(app, frames=1)
    future = app.controller._future
    press(app, "restart")  # running: ignored
    press(app, "run")
    assert app.controller._future is future
    gate.set()
    settle(app)
    assert app.model.df is not None


def test_a_failed_run_shows_its_error_in_the_window(app, tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    app.model.set_folder(empty)
    monkeypatch.setattr(
        core, "read_burst_analysis", lambda *a, **k: (_ for _ in ()).throw(ValueError("no bursts"))
    )
    press(app, "run")
    settle(app)
    assert "BVA failed: no bursts" in draw(app).strings


def test_clear_click_removes_the_result_and_the_scatter(app, measurement):
    run_and_wait(app, measurement)
    assert {"Bursts", "Profile mean"} <= set(draw(app).strings)
    press(app, "clear")
    assert app.model.df is None and app.model.status_text == "Plot cleared"
    strings = draw(app).strings
    assert "Plot cleared" in strings and "Bursts" not in strings and "Static line" in strings
    press(app, "run")  # the cache was invalidated: a Run recomputes
    settle(app)
    assert app.model.df is not None


def test_save_defaults_click_writes_the_ini_and_a_new_window_restores_it(app, measurement):
    drag_field(app, "photons_per_slice", 30)
    pps = app.model.photons_per_slice
    assert pps != 10
    app.model.set_folder(measurement)
    press(app, "save_defaults")
    assert app.model.status_text == "Settings saved" and "Settings saved" in draw(app).strings
    ini = app.controller.settings_path
    assert ini.is_file() and f"photons_per_slice = {pps}" in ini.read_text()
    other = create_app()
    try:
        assert other.model.photons_per_slice == pps and other.model.analysis_folder == measurement
    finally:
        other.close()


# -- the folder, by typing, by dialog, by drop -------------------------------------------------------------------- #


def test_the_folder_field_takes_typed_text_and_backspace_clears_it(app):
    type_into(app, "folder_path", "/some/where", enter=False)
    assert str(app.model.analysis_folder) == "/some/where"
    assert "/some/where" in draw(app).strings
    type_into(app, "folder_path", "", enter=False)  # Ctrl+A, nothing typed
    app.key(keys.KEY_BACKSPACE, "")
    draw(app)
    assert app.model.analysis_folder is None


def test_folder_click_opens_the_dialog_and_choosing_a_folder_by_clicks_sets_it(
    app, measurement, monkeypatch
):
    monkeypatch.chdir(measurement.parent)
    press(app, "folder")
    strings = draw(app).strings
    assert "Select Data Folder" in strings and "Cancel" in strings and "Choose" in strings
    assert str(measurement.parent) in draw(app).strings  # the dialog lists the working folder
    click(app, text_rect(draw(app), "[burstwise]"))  # a click selects the folder
    click(app, text_rect(draw(app), "Choose"))
    assert app.model.analysis_folder == measurement
    assert "Choose" not in draw(app).strings  # the dialog closed
    assert app.model.status_text == f"Data folder: {measurement}"


def test_the_folder_dialog_cancel_and_close_buttons_change_nothing(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    press(app, "folder")
    click(app, text_rect(draw(app), "Cancel"))
    assert "Cancel" not in draw(app).strings and app.model.analysis_folder is None
    press(app, "folder")
    click(app, text_rect(draw(app), "×"))
    assert "Cancel" not in draw(app).strings and app.model.analysis_folder is None


def test_a_dropped_folder_is_taken_and_a_stray_file_is_reported(app, measurement, tmp_path):
    stray = tmp_path / "notes.txt"
    stray.write_text("x")
    assert app.files_dropped([str(stray)])
    assert "BVA reads a burst-analysis folder; notes.txt is not one." in draw(app).strings
    assert app.model.analysis_folder is None
    assert app.files_dropped([str(measurement)])
    assert app.model.analysis_folder == measurement
    assert (
        "Data folder:" in " ".join(draw(app).strings)
        and app.model.status_text == f"Data folder: {measurement}"
    )
    press(app, "run")  # the dropped folder is what runs
    settle(app)
    assert app.model.df is not None


def test_an_empty_drop_is_not_taken(app):
    assert app.files_dropped([]) is False
    assert app.model.analysis_folder is None


# -- save plot ---------------------------------------------------------------------------------------------------- #


def test_save_plot_click_opens_the_dialog_and_a_typed_name_writes_a_png_of_the_window(
    app, measurement, tmp_path, monkeypatch
):
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.chdir(out)
    run_and_wait(app, measurement)
    press(app, "save_plot")
    strings = draw(app).strings
    assert "Save Plot" in strings and "bva_plot.png" in strings and "Cancel" in strings
    click(app, text_rect(draw(app), "bva_plot.png"), fx=0.3)
    app.key(0x41, "a", CTRL_A)
    for ch in "my_bva.png":
        app.key(ord(ch), ch)
        draw(app, frames=1)
    click(app, text_rect(draw(app), "Save"))
    draw(app, frames=3)  # the picture is written on the next frame
    written = out / "my_bva.png"
    assert written.is_file(), list(out.iterdir())
    assert written.read_bytes().startswith(b"\x89PNG")
    assert app.model.status_text == f"Plot saved: {written}"
    assert "Cancel" not in draw(app).strings


def test_save_plot_dialog_cancel_writes_nothing(app, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    press(app, "save_plot")
    click(app, text_rect(draw(app), "Cancel"))
    draw(app, frames=3)
    assert "Cancel" not in draw(app).strings and not list(tmp_path.glob("*.png"))


# -- the settings tab: four drag fields, two checkboxes ------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name,start,dx",
    [
        ("window_length", 0.01, 60),
        ("photons_per_slice", 10, 40),
        ("bins_x", 51, 40),
        ("bins_y", 51, 40),
    ],
)
def test_each_drag_field_changes_its_value_and_the_drawn_text(app, name, start, dx):
    assert getattr(app.model, name) == pytest.approx(start)
    drag_field(app, name, dx)
    after = getattr(app.model, name)
    assert after > start, (name, after)
    drag_field(app, name, -2 * dx)
    assert getattr(app.model, name) < after
    value = getattr(app.model, name)
    shown = f"{value:.4f} s" if name == "window_length" else f"{value:.0f}"
    assert shown in draw(app).strings  # the field shows the new value


@pytest.mark.parametrize(
    "name,low,high",
    [
        ("window_length", 0.0001, 10.0),
        ("photons_per_slice", 1, 500),
        ("bins_x", 10, 500),
        ("bins_y", 10, 500),
    ],
)
def test_a_drag_stops_at_the_range_limits_of_the_qt_tool(app, name, low, high):
    drag_field(app, name, -3000, steps=30)
    assert getattr(app.model, name) == pytest.approx(low)
    drag_field(app, name, 20000, steps=40)
    assert getattr(app.model, name) == pytest.approx(high)


def test_a_bins_drag_redraws_the_profile_without_a_recompute(app, measurement):
    run_and_wait(app, measurement)
    before = app.model.get_plot_data()
    result = app.model.df
    drag_field(app, "bins_x", -20)
    after = app.model.get_plot_data()
    assert (
        app.model.bins_x < 51
        and after["profile_x"].tolist() != before["profile_x"].tolist()
        and app.model.df is result
    )
    assert not app.controller.running


def test_show_static_line_checkbox_toggles_the_line_in_the_plot(app):
    assert "Static line" in draw(app).strings
    press(app, "show_static_line")
    assert app.model.show_static_line is False and "Static line" not in draw(app).strings
    press(app, "show_static_line")
    assert app.model.show_static_line is True and "Static line" in draw(app).strings


def test_auto_update_checkbox_and_a_parameter_drag_recompute_without_writing(app, measurement):
    press(app, "auto_update")
    assert app.model.auto_update is True
    app.model.set_folder(measurement)  # auto update computes on a new folder
    settle(app)
    first = app.model.df
    assert first is not None and not (measurement / "bv4").exists()
    drag_field(app, "photons_per_slice", 30)
    settle(app)
    assert (
        app.model.df is not first and not (measurement / "bv4").exists()
    )  # recomputed, nothing written
    assert app.model.photons_per_slice > 10
    press(app, "auto_update")
    assert app.model.auto_update is False
    result = app.model.df
    drag_field(app, "photons_per_slice", -20)
    assert not app.controller.running and app.model.df is result  # off: the drag recomputes nothing


# -- the channel definitions tab ------------------------------------------------------------------------------------ #


def test_the_tabs_are_clickable_and_each_shows_its_own_controls(app):
    strings = draw(app).strings
    assert "Analysis Parameters" in strings and "Detector Routing" not in strings
    tab(app, "Channel Definitions")
    strings = draw(app).strings
    assert "Detector Routing" in strings and "Analysis Parameters" not in strings
    assert app.bva_gui.selected_settings_tab == "Channel Definitions"
    tab(app, "BVA Settings")
    assert (
        "Analysis Parameters" in draw(app).strings
        and app.bva_gui.selected_settings_tab == "BVA Settings"
    )


def test_donor_and_acceptor_channels_are_typed_and_reach_the_analysis_settings(app):
    tab(app, "Channel Definitions")
    type_into(app, "donor_channels", "0,8", enter=False)
    type_into(app, "acceptor_channels", "1, 9", enter=False)
    settings = app.model.bva_settings()
    assert settings["donor_channels"] == [0, 8] and settings["acceptor_channels"] == [1, 9]
    assert "0,8" in draw(app).strings


def test_microtime_gates_are_typed_and_a_bad_range_is_refused_with_a_message(app):
    tab(app, "Channel Definitions")
    type_into(app, "donor_microtime", "10:20, 30:40", enter=False)
    assert app.model.bva_settings()["donor_micro_time_ranges"] == [(10, 20), (30, 40)]
    assert "Invalid microtime range" not in " ".join(
        draw(app).strings
    )  # typing "1", "10", "10:" was invalid on the way
    assert "10:20, 30:40" in draw(app).strings
    type_into(app, "acceptor_microtime", "100:50", enter=False)
    assert app.model.acceptor_micro_time_ranges == [(0, 32768)]
    assert "Invalid microtime range; use increasing start:end pairs." in draw(app).strings


def test_the_file_type_field_is_typed_and_drops_the_read_burst_table(app, measurement):
    run_and_wait(app, measurement)
    assert app.model.burst_df is not None
    tab(app, "Channel Definitions")
    type_into(app, "file_type", "PTU", enter=False)
    assert app.model.file_type == "PTU" and app.model.burst_df is None and app.model.df is None


def test_a_channel_edit_with_auto_update_recomputes(app, measurement):
    press(app, "auto_update")
    app.model.set_folder(measurement)
    settle(app)
    first = app.model.df
    tab(app, "Channel Definitions")
    type_into(app, "donor_microtime", "0:16384", enter=False)
    settle(app)
    assert app.model.df is not first


# -- the plot ------------------------------------------------------------------------------------------------------- #


def tick_labels(painter):
    return [s for s in painter.strings if s.replace(".", "").replace("-", "").isdigit()]


def test_the_region_rectangle_is_dragged_by_its_edge(app):
    draw(app)
    x, y, w, h = app.item_rects["bva_plot"]
    start = list(app.bva_gui.region_rect)
    left = text_rect(draw(app), "E: 0.20")  # the tag sits at the left edge of the region
    px, py = left[0] + left[2] / 2, y + h / 2
    app.pointer_move(px, py)
    draw(app, frames=2)
    app.press(px, py)
    draw(app, frames=1)
    for step in range(1, 8):
        app.drag(px + 12 * step, py)
        draw(app, frames=1)
    app.release()
    draw(app, frames=2)
    assert app.bva_gui.region_rect != start, "dragging the region edge did not move it"
    assert app.bva_gui.region_rect[0] > start[0]


def test_a_drag_in_the_plot_pans_it(app):
    draw(app)
    before = tick_labels(draw(app))
    x, y, w, h = app.item_rects["bva_plot"]
    cx, cy = x + w * 0.7, y + h * 0.2  # away from the region rectangle
    app.pointer_move(cx, cy)
    draw(app, frames=2)
    app.press(cx, cy)
    draw(app, frames=1)
    for step in range(1, 8):
        app.drag(cx - 20 * step, cy)
        draw(app, frames=1)
    app.release()
    assert tick_labels(draw(app, frames=2)) != before


def test_the_wheel_zooms_the_plot(app):
    draw(app)
    before = tick_labels(draw(app))
    x, y, w, h = app.item_rects["bva_plot"]
    app.pointer_move(x + w * 0.7, y + h * 0.2)
    draw(app, frames=2)
    app.wheel(x + w * 0.7, y + h * 0.2, 3.0)
    assert tick_labels(draw(app, frames=2)) != before


def test_the_plot_tab_is_clickable_and_the_plot_stays_drawn(app):
    tab(app, "Plot")
    assert "Mean Proximity Ratio" in draw(app).strings


# -- Guide and Help ------------------------------------------------------------------------------------------------- #


def test_guide_click_starts_the_tour_whose_buttons_work(app):
    press(app, "guide")
    tour = app.bva_gui.tour
    assert tour.active and tour.step_idx == 0
    assert not tour.awaiting
    click(app, text_rect(draw(app), "Next ►"))
    assert tour.step_idx == 1
    click(app, text_rect(draw(app), "Close Tour"))
    assert not tour.active


def test_the_tour_waits_for_the_folder_and_run_buttons_and_is_walked_to_the_end(
    app, measurement, monkeypatch
):
    monkeypatch.chdir(measurement.parent)
    tour = app.bva_gui.tour
    press(app, "guide")
    waited = []
    guard = 0
    while tour.active and guard < 30:
        guard += 1
        draw(app)
        key = tour._target_key(tour.steps[tour.step_idx].get("target"))
        if tour.awaiting:
            waited.append(key)
            click(app, app.item_rects[key])  # the user operates the highlighted control
            assert not tour.awaiting, f"pressing {key} did not release the step"
            if key == "folder":
                click(app, text_rect(draw(app), "Cancel"))
            else:
                app.controller.stop()
                settle(app)
        draw(app)
        if tour.step_idx == len(tour.steps) - 1:
            tour.next()  # the last step closes the tour
        else:
            click(app, text_rect(draw(app), "Next ►"))
    assert waited == ["folder", "run"] and not tour.active


def test_the_tour_next_button_is_disabled_until_the_awaited_control_is_used(app):
    tour = app.bva_gui.tour
    press(app, "guide")
    click(app, text_rect(draw(app), "Next ►"))  # step 1 awaits the Folder button
    assert tour.step_idx == 1 and tour.awaiting
    click(app, text_rect(draw(app), "Next ►"))
    assert tour.step_idx == 1  # greyed: the click moved nothing


def test_help_click_opens_the_window_whose_buttons_and_escape_close_it(app):
    press(app, "help")
    window = app.bva_gui.help_window
    assert window.open
    painter = draw(app)
    assert {"Start Guided Tour", "Close"} <= set(painter.strings)
    click(app, text_rect(painter, "Start Guided Tour"))
    assert not window.open and app.bva_gui.tour.active
    app.bva_gui.tour.stop()
    press(app, "help")
    click(app, text_rect(draw(app), "Close"))
    assert not window.open
    press(app, "help")
    app.key(keys.KEY_ESCAPE, "")
    draw(app)
    assert not window.open


# -- the small window ----------------------------------------------------------------------------------------------- #


def test_the_flow_works_in_the_small_window_too(app, measurement):
    draw(app, SMALL)
    app.model.set_folder(measurement)
    click(app, app.item_rects["run"], SMALL)
    settle(app, SMALL)
    assert (
        app.model.df is not None
        and "Done – 60 bursts with Std > 0 on 60 total" in draw(app, SMALL).strings
    )
    drag_field(app, "bins_x", 30, SMALL)
    assert app.model.bins_x > 51
    click(app, app.item_rects["clear"], SMALL)
    assert app.model.df is None
    tab(app, "Channel Definitions", SMALL)
    assert "Detector Routing" in draw(app, SMALL).strings
