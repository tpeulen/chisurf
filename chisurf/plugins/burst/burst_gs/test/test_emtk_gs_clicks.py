"""Real-input coverage of the native photon-by-photon kinetics tool: every control is operated with simulated input.

Only ``pointer_move`` / ``press`` / ``release`` / ``drag`` / ``wheel`` / ``key`` and the host's ``files_dropped`` reach the
window, at the rectangles the controls were drawn in (``app.item_rects`` for the buttons and the guide's targets,
``form_state.rects`` for the spec's fields) or at the text a button drew; the assertions read the visible outcome (the model,
the status line, the drawn strings, the files written). The control -> test list is in
``okf/plugins/emtk-ports/burst_gs/REPORT.md`` section 6a.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from chisurf.plugins.burst.burst_gs.gui import view_model
from chisurf.plugins.burst.burst_gs.gui.app import create_app
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


@pytest.fixture
def app():
    window = create_app()
    window.model.sim_n_bursts, window.model.sim_photons_per_burst, window.model.max_iterations = (
        30,
        60,
        200,
    )
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


def has(strings, label):
    """Whether a string equals *label* or is that caption behind a fold arrow ("v label", "> label")."""
    return any(s == label or s.endswith(" " + label) for s in strings)


def press_text(app, label, size=SIZE, last=True):
    click(app, text_rect(draw(app, size), label, last), size)


def rect(app, name):
    return app.item_rects.get(name) or app.gs_gui.form_state.rects[name]


def press(app, name, size=SIZE):
    draw(app, size)
    click(app, rect(app, name), size)


def shown(app, size=SIZE):
    return " ".join(draw(app, size).strings)


def type_into(app, name, text, size=SIZE, enter=True):
    draw(app, size)
    click(app, rect(app, name), size, fx=0.3)
    assert app.io.want_capture_keyboard, f"{name} did not take the keyboard"
    app.key(0x41, "a", CTRL_A)
    draw(app, size, frames=1)
    for ch in text:
        app.key(ord(ch), ch)
        draw(app, size, frames=1)
    if enter:
        app.key(keys.KEY_RETURN, "\r")
        draw(app, size, frames=2)


def simulate(app):
    """Tick Simulation Mode by a click."""
    press(app, "use_simulation")
    assert app.model.use_simulation


def fit(app, size=SIZE):
    press_text(app, "▶ Fit Kinetics", size)
    return settle(app, size)


def burs(tmp_path, *names):
    out = []
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("First Photon\tLast Photon\n")
        out.append(path)
    return out


# -- the simulation toggle, Fit and its states ---------------------------------------------------------------------------- #


def test_the_simulation_checkbox_switches_the_input_panels_and_enables_fit(app):
    strings = draw(app).strings
    assert has(strings, "Data Input & Channels") and not has(strings, "Simulation Parameters")
    assert "Add at least one .bur burst table, or tick Simulate." in shown(
        app
    )  # Fit is greyed with its hint
    click(app, text_rect(draw(app), "▶ Fit Kinetics"))
    assert not app.controller.running  # a click on the greyed button does nothing
    simulate(app)
    strings = draw(app).strings
    assert has(strings, "Simulation Parameters") and not has(strings, "Data Input & Channels")
    assert "Add at least one .bur burst table" not in shown(app)
    press(app, "use_simulation")
    assert not app.model.use_simulation and has(draw(app).strings, "Data Input & Channels")


def test_fit_click_gives_the_qt_tools_rates_status_report_and_tables(app, qt):
    simulate(app)
    app.model.sim_n_bursts, app.model.sim_photons_per_burst, app.model.max_iterations = (
        200,
        200,
        2000,
    )  # the Qt run's own
    press_text(app, "▶ Fit Kinetics")
    assert app.controller.running and "Fitting…" in shown(app) or app.controller.running
    settle(app)
    fit_ = app.model.analysis.fit
    assert np.asarray(fit_.rate_matrix) == pytest.approx(np.asarray(qt["matrix"]))
    assert fit_.log_likelihood == pytest.approx(qt["logL"])
    assert app.controller.status == qt["status"] and app.model.results_text == qt["report"]
    strings = draw(app).strings
    assert qt["status"] in " ".join(strings)
    assert (
        f"{fit_.rate_matrix[1, 0]:,.1f}" in strings and f"{fit_.rate_matrix[0, 1]:,.1f}" in strings
    )  # the Rates table cells
    assert {"Transition", "1 → 2", "2 → 1", "State", "Population"} <= set(strings)
    assert {"Fitted rates", "k(1→2)", "k(2→1)", "simulated"} <= set(strings)


def test_the_simulation_fields_are_typed_clamped_and_reach_the_simulated_rates(app):
    simulate(app)
    m = app.model
    for field, typed, expected in (
        ("sim_k_forward", "5000", 5000.0),
        ("sim_k_forward", "0", 0.1),
        ("sim_k_forward", "99999999", 1e7),
        ("sim_k_backward", "2000", 2000.0),
        ("sim_e1", "0.1", 0.1),
        ("sim_e1", "5", 1.0),
        ("sim_e2", "0.9", 0.9),
        ("sim_photon_rate_khz", "80", 80.0),
        ("sim_photon_rate_khz", "0", 0.1),
        ("sim_n_bursts", "20", 20),
        ("sim_n_bursts", "0", 1),
        ("sim_n_bursts", "999999", 100000),
        ("sim_photons_per_burst", "50", 50),
        ("sim_photons_per_burst", "1", 5),
        ("sim_seed", "7", 7),
        ("sim_seed", "-3", 0),
    ):
        type_into(app, field, typed)
        assert getattr(m, field) == pytest.approx(expected), (field, typed)
    for field, typed in (
        ("sim_n_bursts", "20"),
        ("sim_photons_per_burst", "40"),
        ("sim_k_forward", "5000"),
        ("sim_k_backward", "2000"),
        ("sim_e1", "0.1"),
        ("sim_e2", "0.9"),
        ("sim_photon_rate_khz", "80"),
    ):
        type_into(app, field, typed)
    assert (
        "5000.0" in draw(app).strings and "0.100" in draw(app).strings
    )  # the fields show what the model holds
    type_into(app, "max_iterations", "100")
    fit(app)
    assert app.model.analysis is not None
    labels, rates, truth = app.gs_gui.rate_bars()
    assert truth.tolist() == [5000.0, 2000.0]  # the simulated truth is what was typed


def test_the_same_seed_gives_the_same_fit_through_the_ui(app):
    simulate(app)
    type_into(app, "sim_n_bursts", "20")
    type_into(app, "sim_photons_per_burst", "40")
    type_into(app, "max_iterations", "100")
    results = []
    for _ in range(2):
        type_into(app, "sim_seed", "5")
        fit(app)
        results.append(np.array(app.model.analysis.fit.rate_matrix))
    assert results[0] == pytest.approx(results[1])


def test_the_model_fields_are_typed_and_the_number_of_states_changes_the_tables(app):
    simulate(app)
    type_into(app, "sim_n_bursts", "30")
    type_into(app, "sim_photons_per_burst", "60")
    m = app.model
    for field, typed, expected in (
        ("n_states", "3", 3),
        ("n_states", "9", 5),
        ("n_states", "1", 2),  # the spec's 2..5
        ("initial_rate", "500", 500.0),
        ("initial_rate", "0", 0.1),
        ("max_iterations", "100", 100),
        ("max_iterations", "1", 50),
        ("macro_time_resolution_ns", "50", 50.0),
        ("macro_time_resolution_ns", "-4", 0.0),
        ("transit_points", "10", 10),
        ("transit_points", "2", 5),
    ):
        # a field in a collapsed group is not drawn: every group starts open
        type_into(app, field, typed)
        assert getattr(m, field) == pytest.approx(expected), (field, typed)
    type_into(app, "macro_time_resolution_ns", "0")
    type_into(app, "n_states", "3")
    type_into(app, "max_iterations", "100")
    fit(app)
    strings = draw(app).strings
    assert app.model.analysis.fit.rate_matrix.shape == (3, 3)
    assert {"1 → 2", "1 → 3", "2 → 1", "2 → 3", "3 → 1", "3 → 2"} <= set(
        strings
    )  # six transitions in the Rates table
    assert {"k(1→2)", "k(3→2)"} <= set(strings)


def test_the_four_checkboxes_are_clicked(app):
    simulate(app)
    for field in ("fix_efficiencies", "scan_transition_time", "decode_states", "cross_check_h2mm"):
        before = getattr(app.model, field)
        press(app, field)
        assert getattr(app.model, field) is (not before), field
        press(app, field)
        assert getattr(app.model, field) is before, field


def test_scan_transition_time_and_decode_states_through_the_checkboxes_show_the_scan_plot(app):
    simulate(app)
    type_into(app, "sim_n_bursts", "30")
    type_into(app, "sim_photons_per_burst", "60")
    type_into(app, "max_iterations", "100")
    type_into(app, "transit_points", "6")
    press(app, "scan_transition_time")
    press(app, "decode_states")
    fit(app)
    strings = draw(app).strings
    assert app.model.analysis.transit_times.size == 6
    assert (
        "transition time (µs)" in strings and "Fitted rates" not in strings
    )  # the scan replaces the rates plot


def test_the_optimiser_and_container_choices_are_picked_from_their_lists(app):
    simulate(app)
    press(app, "use_simulation")  # the container is in the data panel
    press(app, "method")
    assert {"nelder-mead", "l-bfgs-b"} <= set(draw(app, frames=1).strings)
    click(app, text_rect(draw(app, frames=1), "l-bfgs-b"))
    assert app.model.method == "l-bfgs-b" and "l-bfgs-b" in draw(app).strings
    press(app, "file_type")
    click(app, text_rect(draw(app, frames=1), "PTU"))
    assert app.model.file_type == "PTU"
    press(app, "file_type")
    app.key(keys.KEY_ESCAPE, "")  # Escape closes the list, nothing chosen
    draw(app, frames=2)
    assert app.model.file_type == "PTU"


def test_the_data_fields_are_typed(app):
    for field, typed, expected in (
        ("donor_channels", "0, 8", "0, 8"),
        ("acceptor_channels", "1, 9", "1, 9"),
        ("data_dir", "/some/dir", "/some/dir"),
        ("min_photons", "30", 30),
        ("min_photons", "1", 2),
        ("max_bursts", "500", 500),
        ("max_bursts", "-1", 0),
    ):
        type_into(app, field, typed)
        assert getattr(app.model, field) == expected, (field, typed)
    assert "/some/dir" in draw(app).strings


def test_a_second_fit_with_new_settings_replaces_the_result(app):
    simulate(app)
    type_into(app, "sim_n_bursts", "30")
    type_into(app, "sim_photons_per_burst", "60")
    type_into(app, "max_iterations", "100")
    fit(app)
    first = np.array(app.model.analysis.fit.rate_matrix)
    type_into(app, "sim_k_forward", "6000")
    fit(app)
    assert not np.allclose(first, app.model.analysis.fit.rate_matrix)
    assert "6000.0" in draw(app).strings


# -- running: progress, Stop, inert controls ------------------------------------------------------------------------------ #


def slow_fit(monkeypatch, gate):
    original = view_model.BurstGsViewModel.compute

    def compute(self, progress=None):
        progress(0.4, "Optimising rates…")
        assert gate.wait(30)
        return original(self, progress=progress)

    monkeypatch.setattr(view_model.BurstGsViewModel, "compute", compute)


def test_progress_bar_stop_fit_and_the_cancelled_message(app, monkeypatch):
    gate = threading.Event()
    slow_fit(monkeypatch, gate)
    simulate(app)
    press_text(app, "▶ Fit Kinetics")
    end = time.monotonic() + 30
    while app.controller.progress_text != "Optimising rates…":
        assert time.monotonic() < end
        time.sleep(0.02)
    strings = draw(app).strings
    assert "Optimising rates…" in strings and app.next_frame_in() is not None
    press_text(app, "Stop fit")
    assert "Stopping kinetics fit …" in shown(app)
    gate.set()
    settle(app)
    assert "Kinetics fit cancelled." in shown(app) and app.model.analysis is None


def test_the_buttons_and_fields_are_inert_while_a_fit_is_running(app, monkeypatch, tmp_path):
    gate = threading.Event()
    slow_fit(monkeypatch, gate)
    simulate(app)
    press_text(app, "▶ Fit Kinetics")
    draw(app, frames=2)
    future = app.controller._future
    press_text(app, "▶ Fit Kinetics")
    assert app.controller._future is future
    press_text(app, "Open BUR files")
    assert app.controller.dialog is None
    k = app.model.sim_k_forward
    type_into(app, "sim_k_forward", "4000")
    assert app.model.sim_k_forward == k
    press(app, "fix_efficiencies")
    assert app.model.fix_efficiencies is False
    gate.set()
    settle(app)
    assert app.model.analysis is not None and app.model.sim_k_forward == k


def test_stop_does_nothing_when_idle(app):
    press_text(app, "Stop fit")
    assert not app.controller.running and app.controller.status == ""


def test_a_failed_fit_and_an_empty_result_are_reported_in_the_window(app, monkeypatch):
    simulate(app)
    monkeypatch.setattr(view_model.BurstGsViewModel, "compute", lambda self, progress=None: False)
    fit(app)
    assert "The fit did not produce a result — see the report." in shown(app)
    monkeypatch.setattr(
        view_model.BurstGsViewModel,
        "compute",
        lambda self, progress=None: (_ for _ in ()).throw(ValueError("singular Hessian")),
    )
    fit(app)
    assert "The fit failed: singular Hessian" in shown(app)


# -- burst tables: dialog, folder, drops, removal ------------------------------------------------------------------------- #


def test_open_bur_files_dialog_selects_files_by_clicks_and_open_adds_them(app, tmp_path):
    burs(tmp_path, "a.bur", "b.bur")
    (tmp_path / "notes.txt").write_text("x")
    press_text(app, "Open BUR files")
    strings = draw(app).strings
    assert (
        "Open burst tables" in strings
        and "a.bur" in strings
        and "b.bur" in strings
        and "notes.txt" not in strings
    )  # the BUR filter
    click(app, text_rect(draw(app), "a.bur"))
    click(app, text_rect(draw(app), "Open"))
    assert [Path(p).name for p in app.model.bur_files] == ["a.bur"]
    assert "Loaded .bur files: 1" in shown(app) and "Open burst tables" not in draw(app).strings


def test_the_open_dialog_cancel_and_close_buttons_add_nothing(app, tmp_path):
    burs(tmp_path, "a.bur")
    press_text(app, "Open BUR files")
    click(app, text_rect(draw(app), "Cancel"))
    assert "Cancel" not in draw(app).strings and not app.model.bur_files
    press_text(app, "Open BUR files")
    click(app, text_rect(draw(app), "×"))
    assert "Cancel" not in draw(app).strings and not app.model.bur_files


def test_add_burst_folder_dialog_adds_every_table_below_it(app, tmp_path):
    burs(tmp_path, "run/m1.bur", "run/sub/m2.bur")
    press_text(app, "Add burst folder")
    assert "Add burst folder" in draw(app).strings
    click(app, text_rect(draw(app), "[run]"))
    click(app, text_rect(draw(app), "Choose"))
    assert sorted(Path(p).name for p in app.model.bur_files) == ["m1.bur", "m2.bur"]


def test_a_dropped_table_or_folder_is_added_and_a_stray_file_is_reported(app, tmp_path):
    a, b = burs(tmp_path, "d/a.bur", "b.bur")
    stray = tmp_path / "notes.txt"
    stray.write_text("x")
    assert app.files_dropped([str(a.parent), str(b)])
    assert sorted(Path(p).name for p in app.model.bur_files) == ["a.bur", "b.bur"]
    assert "Loaded .bur files: 2" in shown(app)
    assert app.files_dropped([str(stray)])
    assert "No .bur burst table among the dropped paths." in shown(app)
    assert app.files_dropped([]) is False


def test_each_listed_table_has_a_remove_button_and_clear_removes_all_and_the_result(app, tmp_path):
    a, b = burs(tmp_path, "a.bur", "b.bur")
    app.files_dropped([str(a), str(b)])
    painter = draw(app)
    assert (
        "a.bur" in " ".join(painter.strings)
        and "b.bur" in " ".join(painter.strings)
        and painter.strings.count("Remove") == 2
    )
    click(app, text_rect(draw(app), "Remove", last=False))  # the first one's button
    assert [Path(p).name for p in app.model.bur_files] == ["b.bur"]
    simulate(app)
    fit(app)
    assert app.model.analysis is not None
    press_text(app, "Clear burst files")
    assert (
        app.model.bur_files == []
        and app.model.analysis is None
        and "1 → 2" not in draw(app).strings
    )


def test_a_fit_on_a_dropped_table_reports_the_load_failure_in_the_report(app, tmp_path):
    (table,) = burs(tmp_path, "m.bur")
    app.files_dropped([str(table)])
    fit(app)
    assert "Could not load the photons" in shown(app) and app.model.analysis is None


def test_mmfdb_datasets_picker_lists_a_dataset_selects_it_and_the_window_closes(app):
    class Client:
        def call(self, name, args=None):
            return {
                "datasets": [
                    {
                        "artifact_id": "a1",
                        "original_filename": "m.bur",
                        "artifact_kind": "burst_data",
                        "data_format": "bur",
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
    click(app, text_rect(draw(app), "m.bur [burst_data] (bur)"))
    assert app.controller.datasets.selection.artifact_id == "a1"
    click(app, text_rect(draw(app), "×"))
    assert "Select MMFDB dataset" not in draw(app).strings


# -- export ----------------------------------------------------------------------------------------------------------------- #


def test_export_is_greyed_before_a_fit_then_writes_the_csv_the_qt_tool_wrote(app, tmp_path):
    click(app, text_rect(draw(app), "💾  Export CSV"))
    assert app.controller.dialog is None  # greyed: nothing opens
    simulate(app)
    type_into(app, "sim_n_bursts", "20")
    type_into(app, "sim_photons_per_burst", "40")
    type_into(app, "max_iterations", "100")
    fit(app)
    press_text(app, "💾  Export CSV")
    strings = draw(app).strings
    assert "Export photon-by-photon kinetics" in strings and "kinetics.gs.csv" in strings
    click(app, text_rect(draw(app), "kinetics.gs.csv"), fx=0.3)
    app.key(0x41, "a", CTRL_A)
    for ch in "mine.csv":
        app.key(ord(ch), ch)
        draw(app, frames=1)
    click(app, text_rect(draw(app), "Save"))
    written = tmp_path / "mine.csv"
    lines = written.read_text().splitlines()
    assert (
        lines[0] == "quantity,value"
        and lines[1].startswith("k_12_per_s,")
        and any(l.startswith("bic,") for l in lines)
    )
    assert app.controller.status == "Wrote mine.csv" or app.controller.status.endswith("mine.csv")
    assert "mine.csv" in shown(app) and "Cancel" not in draw(app).strings


def test_the_export_dialog_cancel_writes_nothing(app, tmp_path):
    simulate(app)
    type_into(app, "sim_n_bursts", "20")
    type_into(app, "sim_photons_per_burst", "40")
    type_into(app, "max_iterations", "100")
    fit(app)
    press_text(app, "💾  Export CSV")
    click(app, text_rect(draw(app), "Cancel"))
    assert "Cancel" not in draw(app).strings and not list(tmp_path.glob("*.csv"))


# -- tables and plots ------------------------------------------------------------------------------------------------------ #


def small_fit(app):
    simulate(app)
    type_into(app, "sim_n_bursts", "30")
    type_into(app, "sim_photons_per_burst", "60")
    type_into(app, "max_iterations", "100")
    fit(app)


def test_a_click_on_a_table_row_and_header_changes_no_value_and_the_columns_have_tooltips(app):
    small_fit(app)
    before = np.array(app.model.analysis.fit.rate_matrix)
    click(app, text_rect(draw(app), "1 → 2"))
    for _ in range(2):  # a header click sorts, again flips
        header = [t[:4] for t in draw(app).texts if t[5].startswith("Transition")][0]
        click(app, header)
    assert np.array_equal(before, app.model.analysis.fit.rate_matrix) and not app.controller.running
    assert {"1 → 2", "2 → 1", "State"} <= set(draw(app).strings)


def test_the_fret_states_tab_is_clicked_and_shows_the_state_lines(app):
    small_fit(app)
    assert "FRET efficiency & fitted states" not in draw(app).strings
    click(app, text_rect(draw(app), "FRET states"))
    strings = draw(app).strings
    assert (
        "FRET efficiency" in strings
        and "Population / photon density" in strings
        and "state 1" in strings
    )
    click(app, text_rect(draw(app), "Kinetics dynamics"))
    assert "Fitted rates" in draw(app).strings


def tick_labels(painter):
    return [s for s in painter.strings if s.replace(".", "").replace("-", "").isdigit()]


def test_a_drag_pans_the_rates_plot(app):
    small_fit(app)
    painter = draw(app)
    x, y = text_rect(painter, "transition")[:2]
    cx, cy = 900.0, 600.0
    before = tick_labels(draw(app))
    app.pointer_move(cx, cy)
    draw(app, frames=2)
    app.press(cx, cy)
    draw(app, frames=1)
    for step in range(1, 8):
        app.drag(cx, cy - 25 * step)
        draw(app, frames=1)
    app.release()
    assert tick_labels(draw(app, frames=2)) != before


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the wheel never reaches an implot inside a DockManager window (works in a plain "
    "im.begin window); see REPORT.md 'emtk gaps'",
)
def test_the_wheel_zooms_the_rates_plot(app):
    small_fit(app)
    cx, cy = 900.0, 600.0
    before = tick_labels(draw(app))
    app.pointer_move(cx, cy)
    draw(app, frames=2)
    app.wheel(cx, cy, 3.0)
    assert tick_labels(draw(app, frames=2)) != before


# -- Guide and Help ---------------------------------------------------------------------------------------------------------- #


def test_guide_click_starts_the_tour_whose_close_prev_and_next_buttons_are_clicked(app):
    press(app, "guide")
    tour = app.gs_gui.tour
    assert tour.active and not tour.awaiting
    click(app, text_rect(draw(app), "Next ►"))
    assert tour.step_idx == 1 and tour.awaiting  # "Tick Simulate" waits for the checkbox
    click(app, text_rect(draw(app), "Next ►"))
    assert tour.step_idx == 1  # greyed
    simulate(app)  # the user ticks the highlighted checkbox
    assert not tour.awaiting
    click(app, text_rect(draw(app), "◄ Prev"))
    assert tour.step_idx == 0
    click(app, text_rect(draw(app), "Close Tour"))
    assert not tour.active


def test_escape_closes_the_tour_even_while_a_step_waits_for_its_control(app):
    press(app, "guide")
    click(app, text_rect(draw(app), "Next ►"))
    assert app.gs_gui.tour.awaiting
    app.key(keys.KEY_ESCAPE, "")
    draw(app, frames=2)
    assert not app.gs_gui.tour.active


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(app):
    tour = app.gs_gui.tour
    press(app, "guide")
    waited = []
    guard = 0
    while tour.active and guard < 40:
        guard += 1
        draw(app)
        target = tour.steps[tour.step_idx].get("target") or {}
        if tour.awaiting:
            if target.get("attr") == "use_simulation":
                simulate(app)
                waited.append("use_simulation")
            elif target.get("action") == "Fit":
                (
                    app.model.sim_n_bursts,
                    app.model.sim_photons_per_burst,
                    app.model.max_iterations,
                ) = 20, 40, 100
                press(app, "Fit")
                waited.append("Fit")
                settle(app)
            assert not tour.awaiting, (
                f"{tour.steps[tour.step_idx]['title']}: operating {target} did not release the step"
            )
        draw(app)
        painter = draw(app)
        click(
            app,
            text_rect(painter, "Finish ✓" if tour.step_idx == len(tour.steps) - 1 else "Next ►"),
        )  # every card button by click
    assert (
        waited == ["use_simulation", "Fit"] and not tour.active and app.model.analysis is not None
    )


def test_every_guide_target_is_a_real_control_that_can_be_clicked(app):
    small_fit(app)
    tour = app.gs_gui.tour
    drawn = set(app.item_rects) | set(app.gs_gui.form_state.rects)
    for step in tour.steps:
        key = tour._target_key(step.get("target"))
        if key:
            assert key in drawn, key


def test_help_click_opens_the_window_whose_buttons_and_escape_close_it(app):
    press(app, "help")
    window = app.gs_gui.help_window
    assert window.open
    painter = draw(app)
    assert {"Start Guided Tour", "Close"} <= set(painter.strings)
    click(app, text_rect(painter, "Start Guided Tour"))
    assert not window.open and app.gs_gui.tour.active
    app.gs_gui.tour.stop()
    press(app, "help")
    click(app, text_rect(draw(app), "Close"))
    assert not window.open
    press(app, "help")
    app.key(keys.KEY_ESCAPE, "")
    draw(app)
    assert not window.open


# -- the small window ---------------------------------------------------------------------------------------------------------- #


def test_the_flow_works_in_the_small_window_too(app):
    draw(app, SMALL)
    click(app, text_rect(draw(app, SMALL), "Use Simulation Mode"), SMALL, fx=0.1)
    assert app.model.use_simulation
    type_into(app, "sim_n_bursts", "20", SMALL)
    type_into(app, "sim_photons_per_burst", "40", SMALL)
    type_into(app, "max_iterations", "100", SMALL)
    click(app, text_rect(draw(app, SMALL), "▶ Fit Kinetics"), SMALL)
    settle(app, SMALL)
    assert app.model.analysis is not None and "1 → 2" in draw(app, SMALL).strings
    press_text(app, "Add burst folder", SMALL)
    assert "Choose" in draw(app, SMALL).strings
    click(app, text_rect(draw(app, SMALL), "Cancel"), SMALL)
    assert "Choose" not in draw(app, SMALL).strings
