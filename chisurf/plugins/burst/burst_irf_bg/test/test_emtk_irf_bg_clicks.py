"""Real-input coverage of the native Burst IRF & Background tool: every control is operated with simulated input.

Only ``pointer_move`` / ``press`` / ``release`` / ``drag`` / ``wheel`` / ``key`` and the host's ``files_dropped`` reach the
window, at the rectangles the controls were drawn in (``app.item_rects`` for the buttons and the guide's targets,
``form_state.rects`` for the spec's fields) or at the text a button drew; the assertions read the visible outcome (the model,
the status line, the drawn strings, the files written). The control -> test list is in
``okf/plugins/emtk-ports/burst_irf_bg/REPORT.md`` section 6a.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest
from chisurf.plugins.burst.burst_irf_bg.gui import view_model
from chisurf.plugins.burst.burst_irf_bg.gui.app import create_app
from chisurf.plugins.burst.burst_irf_bg.test.demo_data import IRF_PEAK_NS, build
from emtk import keys
from emtk.testing import RecordingPainter

SIZE = (1200, 800)
SMALL = (800, 600)
CTRL_A = 0x04000000


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.chdir(tmp_path)


@pytest.fixture(scope="module")
def measurement(tmp_path_factory):
    return build(tmp_path_factory.mktemp("irfclicks") / "measurement")


@pytest.fixture
def app():
    window = create_app()
    yield window
    window.close()


def draw(app, size=SIZE, frames=2):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def settle(app, size=SIZE, timeout=120.0):
    end = time.monotonic() + timeout
    draw(app, size, frames=1)
    while app.controller.running and time.monotonic() < end:
        time.sleep(0.02)
        draw(app, size, frames=1)
    assert not app.controller.running
    return draw(app, size, frames=1)


def click(app, rect, size=SIZE, fx=0.5, clicks=1):
    x, y, w, h = rect
    app.pointer_move(x + w * fx, y + h / 2)
    draw(app, size, frames=1)
    app.press(x + w * fx, y + h / 2, clicks=clicks)
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=1)


def text_rect(painter, label, last=True):
    hits = [t[:4] for t in painter.texts if t[5] == label]
    assert hits, f"{label!r} is not drawn: {[t[5] for t in painter.texts][:80]}"
    return hits[-1] if last else hits[0]


def press_text(app, label, size=SIZE, last=True):
    click(app, text_rect(draw(app, size), label, last), size)


def rect(app, name):
    return app.item_rects.get(name) or app.irf_gui.form_state.rects[name]


def press(app, name, size=SIZE):
    draw(app, size)
    click(app, rect(app, name), size)


def shown(app, size=SIZE):
    return " ".join(draw(app, size).strings)


def key_text(app, text, size=SIZE, enter=True):
    app.key(0x41, "a", CTRL_A)
    draw(app, size, frames=1)
    for ch in text:
        app.key(ord(ch), ch)
        draw(app, size, frames=1)
    if enter:
        app.key(keys.KEY_RETURN, "\r")
        draw(app, size, frames=2)


def type_into(app, name, text, size=SIZE, enter=True):
    draw(app, size)
    click(app, rect(app, name), size, fx=0.3)
    assert app.io.want_capture_keyboard, f"{name} did not take the keyboard"
    key_text(app, text, size, enter)


def compute(app, size=SIZE):
    press(app, "irf_bg_run", size)
    return settle(app, size)


def load(app, measurement):
    app.files_dropped([str(measurement)])
    assert app.model.files == [str(measurement)]


# -- Compute, Stop, the result ------------------------------------------------------------------------------------------ #


def test_compute_without_files_says_why_and_a_click_on_a_loaded_demo_gives_the_qt_tools_rows(
    app, measurement, qt
):
    press(app, "irf_bg_run")
    assert "Please load TTTR files first." in shown(app) and not app.controller.running
    load(app, measurement)
    press(app, "irf_bg_run")
    assert app.controller.running and "Extracting IRF and background …" in shown(app)
    settle(app)
    import json

    rows = app.model.results_rows()
    assert json.loads(json.dumps(rows)) == qt["rows"]
    for row in rows:
        assert abs(row["prompt_ns"] - IRF_PEAK_NS) < 0.15  # the IRF the demo was made with
    strings = draw(app).strings
    assert strings.count("Extracted IRF + background for 2 detector(s).") == 1
    assert {
        "Detector",
        "Background (kHz)",
        "Prompt (ns)",
        "Non-burst",
        "Burst",
        "green",
        "red",
    } <= set(strings)
    assert all(f"{r['background_khz']:.3f}" in strings for r in rows)  # the table cells
    assert (
        "Micro time (ns)" in strings
        and "IRF (normalised)" in strings
        and "No IRF data available." not in " ".join(strings)
    )


def test_stop_computation_cancels_and_keeps_the_previous_results(app, measurement, monkeypatch):
    load(app, measurement)
    compute(app)
    before = dict(app.model._display)
    gate = threading.Event()
    original = view_model.IrfBackgroundViewModel.compute
    monkeypatch.setattr(
        view_model.IrfBackgroundViewModel,
        "compute",
        lambda self, cancel_check=None: (
            gate.wait(30),
            cancel_check and cancel_check(),
            original(self, cancel_check),
        )[2],
    )
    press(app, "irf_bg_run")
    draw(app, frames=1)
    assert app.controller.running and app.next_frame_in() is not None
    press_text(app, "Stop computation")
    assert "Stopping …" in shown(app)
    gate.set()
    settle(app)
    assert "Computation cancelled." in shown(app) and app.model._display == before


def test_stop_does_nothing_when_idle(app):
    press_text(app, "Stop computation")
    assert not app.controller.running and app.controller.status == ""


def test_everything_is_inert_while_a_computation_runs(app, measurement, monkeypatch):
    load(app, measurement)
    gate = threading.Event()
    original = view_model.IrfBackgroundViewModel.compute
    monkeypatch.setattr(
        view_model.IrfBackgroundViewModel,
        "compute",
        lambda self, cancel_check=None: (gate.wait(30), original(self, cancel_check))[1],
    )
    press(app, "irf_bg_run")
    draw(app, frames=2)
    future = app.controller._future
    press(app, "irf_bg_run")
    assert app.controller._future is future
    press_text(app, "Open TTTR files")
    assert app.controller.dialog is None
    k = app.model.min_photons
    type_into(app, "min_photons", "99")
    assert app.model.min_photons == k
    press_text(app, "Clear files")
    assert app.model.files == [str(measurement)]
    gate.set()
    settle(app)
    assert app.model.has_results() and app.model.min_photons == k


def test_a_broken_file_reports_its_error_in_the_window(app, tmp_path):
    bad = tmp_path / "broken.ptu"
    bad.write_bytes(b"not a measurement")
    app.files_dropped([str(bad)])
    press(app, "irf_bg_run")
    settle(app)
    assert "Error:" in shown(app) and not app.model.has_results()


# -- the five parameters ------------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "field,typed,expected",
    [
        ("min_photons", "80", 80),
        ("min_photons", "1", 2),
        ("min_photons", "999999", 100000),
        ("photon_window", "12", 12),
        ("photon_window", "0", 2),
        ("photon_window", "99999", 10000),
        ("time_window_ms", "2.5", 2.5),
        ("time_window_ms", "0", 0.001),
        ("time_window_ms", "5000", 1000.0),
        ("baseline_quantile", "0.3", 0.3),
        ("baseline_quantile", "2", 0.9),
        ("baseline_quantile", "-1", 0.0),
        ("micro_time_binning", "8", 8),
        ("micro_time_binning", "0", 1),
        ("micro_time_binning", "500", 64),
    ],
)
def test_each_parameter_is_typed_and_clamped_to_the_qt_ranges(app, field, typed, expected):
    type_into(app, field, typed)
    assert getattr(app.model, field) == pytest.approx(expected), (field, typed)
    shown_value = {"time_window_ms": f"{expected:.3f}", "baseline_quantile": f"{expected:.2f}"}.get(
        field, f"{expected}"
    )
    assert shown_value in draw(app).strings  # the field shows what the model holds


def test_a_parameter_changes_what_the_extraction_finds(app, measurement):
    load(app, measurement)
    compute(app)
    first = {r["detector"]: r["n_bg"] for r in app.model.results_rows()}
    type_into(app, "min_photons", "20000")  # no burst is that long: every photon is "non-burst"
    compute(app)
    second = {r["detector"]: r["n_bg"] for r in app.model.results_rows()}
    assert all(second[k] > first[k] for k in first)


def test_the_binning_field_and_the_channel_editors_microtime_binning_are_one_value(app):
    type_into(app, "micro_time_binning", "4")
    reading = app.controller.channel_definition.model.data["tttr_reading"]
    assert reading["micro_time_binning"] == 4
    press_text(app, "Channel definition", last=False)
    strings = draw(app).strings
    assert (
        "Microtime binning:" in strings and "4" in strings
    )  # the editor shows the value typed in the tool


# -- the channel definition window (the shared editor) ----------------------------------------------------------------------------- #


def open_editor(app):
    """Show the Channel definition dock tab: the one-page shared editor."""
    press_text(app, "Channel definition", last=False)
    assert "TTTR Reading Routine:" in draw(app).strings


def detector_cell(app, detector, key):
    """Where a cell of the editor's Detectors table is drawn (its own geometry of the last frame)."""
    draw(app)
    control = app.controller.channel_definition._detector_table.control
    index = next(i for i, record in enumerate(control.records) if record["id"] == detector)
    position = control.order().index(index)
    _x, body_y, _w, _h = control._body_box
    x = control._header_box[0]
    for column, width in zip(control._shown, control._widths):
        if column.key == key:
            return (
                x,
                body_y + (position - control.bar.top) * control._row_h,
                width,
                control._row_h,
            )
        x += width
    raise AssertionError(key)


def type_into_cell(app, detector, key, text):
    """Double-click a cell of the Detectors table, type over its text and press Enter."""
    click(app, detector_cell(app, detector, key), clicks=2)
    assert app.controller.channel_definition._detector_table.control.editing is not None
    app.key(keys.KEY_END, "")
    for _ in range(24):  # the cell opens with its text: empty it
        app.key(keys.KEY_BACKSPACE, "")
        draw(app, frames=1)
    key_text(app, text)


def test_the_channel_definition_button_opens_the_editor_and_a_typed_routing_reaches_the_detectors(
    app,
):
    assert "TTTR Reading Routine:" not in draw(app).strings
    open_editor(app)
    strings = draw(app).strings
    assert {"Channels", "Micro Time Ranges", "green", "red", "▼ Detectors"} <= set(strings)
    type_into_cell(app, "green", "chs", "5")
    assert app.model._channels()["green"]["chs"] == [5]
    assert "5" in draw(app).strings


def test_a_typed_list_of_routing_channels_arrives_as_a_list(app):
    """The table cell keeps the text as it is typed, so the comma of '0, 8' is not eaten (the old field re-formatted it)."""
    open_editor(app)
    type_into_cell(app, "green", "chs", "0, 8, 2")
    assert app.model._channels()["green"]["chs"] == [0, 8, 2]
    assert "0, 8, 2" in draw(app).strings


def test_the_ptu_reading_section_lists_its_fields(app):
    open_editor(app)
    assert {
        "File Type:",
        "Macrotime res. (ns):",
        "Microtime res. (ps):",
        "Microtime binning:",
        "Read",
    } <= set(draw(app).strings)


# -- Send to MLE and the pattern export ----------------------------------------------------------------------------------------------- #


def test_send_to_mle_before_a_result_then_with_a_receiver_as_the_qt_tool_does(measurement, qt):
    received = []
    window = create_app(
        mle_receiver=lambda patterns: (received.append(sorted(patterns)), len(patterns))[1]
    )
    try:
        press(window, "send_to_mle")
        assert window.controller.status == qt["early"] == "Compute the IRF and background first."
        assert "Compute the IRF and background first." in shown(window)
        load(window, measurement)
        compute(window)
        press(window, "send_to_mle")
        assert window.controller.status == qt["sent"]
        assert received == [qt["received"]] and qt["sent"] in shown(window)
    finally:
        window.close()


def test_send_to_mle_without_a_receiver_points_at_the_export(app, measurement):
    load(app, measurement)
    compute(app)
    press(app, "send_to_mle")
    assert (
        "Open inside Burst Analysis to feed MLE, or export the patterns for scripted use."
        in shown(app)
    )


def test_export_mle_patterns_needs_a_result_then_writes_the_npz_with_every_pattern(
    app, measurement, tmp_path
):
    press_text(app, "Export MLE patterns")
    assert "Compute the IRF and background first." in shown(app) and app.controller.dialog is None
    load(app, measurement)
    compute(app)
    press_text(app, "Export MLE patterns")
    strings = draw(app).strings
    assert "Export MLE patterns" in strings and "irf_background.npz" in strings
    click(app, text_rect(draw(app), "irf_background.npz"), fx=0.3)
    key_text(app, "mine.npz", enter=False)
    click(app, text_rect(draw(app), "Save"))
    out = tmp_path / "mine.npz"
    with np.load(out) as data:
        assert {"green/irf", "green/bg", "red/irf", "red/bg"} <= set(data.files)
        for name in app.model.mle_patterns():
            assert np.allclose(data[f"{name}/irf"], app.model.mle_patterns()[name]["irf"])
    assert "MLE patterns exported:" in shown(app) and "Cancel" not in draw(app).strings


def test_the_export_dialog_cancel_and_close_write_nothing(app, measurement, tmp_path):
    load(app, measurement)
    compute(app)
    for closer in ("Cancel", "×"):
        press_text(app, "Export MLE patterns")
        click(app, text_rect(draw(app), closer))
        assert "Cancel" not in draw(app).strings
    assert not list(tmp_path.glob("*.npz"))


# -- files: dialog, folder, drops, MMFDB, remove, clear ----------------------------------------------------------------------------------- #


def test_open_tttr_files_dialog_lists_measurements_and_open_adds_the_clicked_one(app, measurement):
    import os

    os.chdir(measurement.parent)
    (measurement.parent / "notes.txt").write_text("x")
    press_text(app, "Open TTTR files")
    strings = draw(app).strings
    assert (
        "Select TTTR files" in strings
        and measurement.name in strings
        and "notes.txt" not in strings
    )  # the TTTR filter
    click(app, text_rect(draw(app), measurement.name))
    click(app, text_rect(draw(app), "Open"))
    assert app.model.files == [str(measurement)]
    assert "Files loaded: 1" in shown(app) and "Select TTTR files" not in draw(app).strings


def test_the_open_dialog_cancel_and_close_buttons_add_nothing(app, measurement):
    import os

    os.chdir(measurement.parent)
    for closer in ("Cancel", "×"):
        press_text(app, "Open TTTR files")
        click(app, text_rect(draw(app), closer))
        assert "Cancel" not in draw(app).strings
    assert app.model.files == []


def test_add_tttr_folder_dialog_adds_the_measurement_in_it(app, measurement):
    import os

    os.chdir(measurement.parent.parent)
    press_text(app, "Add TTTR folder")
    assert "Add TTTR folder" in draw(app).strings
    click(app, text_rect(draw(app), f"[{measurement.parent.name}]"))
    click(app, text_rect(draw(app), "Choose"))
    assert app.model.files == [str(measurement)]


def test_a_dropped_measurement_folder_or_container_is_handled_as_the_qt_tool_does(
    app, measurement, tmp_path
):
    folder = tmp_path / "pair"
    folder.mkdir()
    spc = folder / "m.spc"
    spc.write_bytes(measurement.read_bytes())
    (folder / "m.pto").write_bytes(
        b""
    )  # the container beside the vendor file is not a second measurement
    (folder / "notes.txt").write_text("x")
    assert app.files_dropped([str(folder)])
    assert app.model.files == [str(spc)]
    assert app.files_dropped([]) is False


def test_each_listed_file_has_a_remove_button_and_clear_files_drops_files_and_results(
    app, measurement, tmp_path
):
    other = tmp_path / "other.spc"
    other.write_bytes(measurement.read_bytes())
    app.files_dropped([str(measurement), str(other)])
    painter = draw(app)
    assert painter.strings.count("Remove") == 2 and "Files loaded: 2" in " ".join(painter.strings)
    compute(app)
    click(app, text_rect(draw(app), "Remove", last=False))
    assert (
        app.model.files == [str(other)]
        if str(other) < str(measurement)
        else len(app.model.files) == 1
    )
    assert (
        "File removed; recompute to refresh pooled results." in shown(app)
        and not app.model.has_results()
    )
    compute(app)
    press_text(app, "Clear files")
    assert app.model.files == [] and not app.model.has_results()
    assert "Files and results cleared." in shown(app) and "No IRF data available." in " ".join(
        draw(app).strings
    )


def test_mmfdb_datasets_picker_lists_a_dataset_selects_it_and_the_window_closes(app):
    class Client:
        def call(self, name, args=None):
            return {
                "datasets": [
                    {
                        "artifact_id": "a1",
                        "original_filename": "m000.spc",
                        "artifact_kind": "raw_data",
                        "data_format": "spc",
                    }
                ],
                "total": 1,
            }

    app.controller.datasets.client = Client()
    press_text(app, "MMFDB datasets")
    for _ in range(50):
        draw(app, frames=1)
        if app.controller.datasets._pending is None:
            break
        time.sleep(0.02)
    draw(app)
    assert "Select MMFDB dataset" in draw(app).strings
    click(app, text_rect(draw(app), "m000.spc [raw_data] (spc)"))
    assert app.controller.datasets.selection.artifact_id == "a1"
    click(app, text_rect(draw(app), "×"))
    assert "Select MMFDB dataset" not in draw(app).strings


# -- tables and plots ------------------------------------------------------------------------------------------------------------------- #


def test_a_click_on_a_row_and_on_the_headers_sorts_and_changes_no_result(app, measurement):
    load(app, measurement)
    compute(app)
    before = {r["detector"]: r["background_khz"] for r in app.model.results_rows()}
    click(app, text_rect(draw(app), "green"))
    for _ in range(2):  # a header click sorts, again flips
        header = [t[:4] for t in draw(app).texts if "Backgr" in t[5]][0]
        click(app, header)
    assert before == {r["detector"]: r["background_khz"] for r in app.model.results_rows()}
    assert {"green", "red"} <= set(draw(app).strings)


def tick_labels(painter):
    return [
        s for s in painter.strings if s.replace(".", "").replace("-", "").replace("e", "").isdigit()
    ]


def test_a_drag_pans_the_irf_plot(app, measurement):
    load(app, measurement)
    compute(app)
    x, y, w, h = app.item_rects["irf_series"]
    cx, cy = x + w / 2, y + h / 2
    before = tick_labels(draw(app))
    app.pointer_move(cx, cy)
    draw(app, frames=2)
    app.press(cx, cy)
    draw(app, frames=1)
    for step in range(1, 8):
        app.drag(cx - 25 * step, cy)
        draw(app, frames=1)
    app.release()
    assert tick_labels(draw(app, frames=2)) != before


def test_the_wheel_zooms_the_irf_plot(app, measurement):
    load(app, measurement)
    compute(app)
    x, y, w, h = app.item_rects["irf_series"]
    cx, cy = x + w / 2, y + h / 2
    before = tick_labels(draw(app))
    app.pointer_move(cx, cy)
    draw(app, frames=2)
    app.wheel(cx, cy, 3.0)
    assert tick_labels(draw(app, frames=2)) != before


def test_the_dock_tabs_switch_between_the_parameters_and_the_channel_editor(app):
    assert "Burst Search & Baseline" in draw(app).strings
    click(app, text_rect(draw(app), "Channel definition", last=False))
    strings = draw(app).strings
    assert "TTTR Reading Routine:" in strings and "Burst Search & Baseline" not in strings
    click(app, text_rect(draw(app), "IRF parameters"))
    assert (
        "Burst Search & Baseline" in draw(app).strings
        and "TTTR Reading Routine:" not in draw(app).strings
    )


# -- Guide and Help ----------------------------------------------------------------------------------------------------------------------- #


def test_guide_click_starts_the_tour_whose_close_prev_and_next_buttons_are_clicked(app):
    press(app, "guide")
    tour = app.irf_gui.tour
    assert tour.active and not tour.awaiting
    click(app, text_rect(draw(app), "Next ►"))
    assert tour.step_idx == 1
    click(app, text_rect(draw(app), "◄ Prev"))
    assert tour.step_idx == 0
    click(app, text_rect(draw(app), "Close Tour"))
    assert not tour.active


def test_the_tour_is_walked_to_the_end_and_waits_for_the_extract_button(app, measurement):
    tour = app.irf_gui.tour
    load(app, measurement)
    press(app, "guide")
    waited = []
    guard = 0
    while tour.active and guard < 40:
        guard += 1
        draw(app)
        if tour.awaiting:
            target = tour._target_key(tour.steps[tour.step_idx].get("target"))
            waited.append(target)
            click(app, text_rect(draw(app), "Next ►"))
            assert (
                tour.step_idx == tour.step_idx and tour.awaiting
            )  # greyed until the control is pressed
            press(app, target)
            settle(app)
            assert not tour.awaiting
        draw(app)
        painter = draw(app)
        click(
            app,
            text_rect(painter, "Finish ✓" if tour.step_idx == len(tour.steps) - 1 else "Next ►"),
        )
    assert waited == ["irf_bg_run"] and not tour.active and app.model.has_results()


def test_escape_closes_the_tour_while_a_step_waits(app):
    tour = app.irf_gui.tour
    tour.start(next(i for i, st in enumerate(tour.steps) if st.get("await")))
    draw(app)
    assert tour.awaiting
    app.key(keys.KEY_ESCAPE, "")
    draw(app, frames=2)
    assert not tour.active


def test_help_click_opens_the_window_whose_buttons_and_escape_close_it(app):
    press(app, "help")
    window = app.irf_gui.help_window
    assert window.open
    painter = draw(app)
    assert {"Start Guided Tour", "Close"} <= set(painter.strings)
    click(app, text_rect(painter, "Start Guided Tour"))
    assert not window.open and app.irf_gui.tour.active
    app.irf_gui.tour.stop()
    press(app, "help")
    click(app, text_rect(draw(app), "Close"))
    assert not window.open
    press(app, "help")
    app.key(keys.KEY_ESCAPE, "")
    draw(app)
    assert not window.open


# -- the small window ----------------------------------------------------------------------------------------------------------------------- #


def test_the_flow_works_in_the_small_window_too(app, measurement):
    draw(app, SMALL)
    app.files_dropped([str(measurement)])
    type_into(app, "baseline_quantile", "0.3", SMALL)
    assert app.model.baseline_quantile == 0.3
    click(app, rect(app, "irf_bg_run"), SMALL)
    settle(app, SMALL)
    assert app.model.has_results() and {"green", "red"} <= set(draw(app, SMALL).strings)
    press_text(app, "Open TTTR files", SMALL)
    assert "Select TTTR files" in draw(app, SMALL).strings
    click(app, text_rect(draw(app, SMALL), "Cancel"), SMALL)
    assert "Select TTTR files" not in draw(app, SMALL).strings
