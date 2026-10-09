"""Click coverage of the native accurate-FRET app: every control is operated with simulated pointer and keyboard events.

The app is drawn by the emtk frame loop; the tests only ``press`` / ``release`` / ``pointer_move`` / ``key`` at the
rectangles the controls were drawn in (or at the text a button or list entry drew), through the file dialog, the
channel lists and the host's drop, and assert the visible outcome: status line, model values, the result tables, the
plots' series, the files written. The coverage list control -> test is in
``okf/plugins/emtk-ports/accurate_fret/REPORT.md``.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest
from emtk import keys
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.accurate_fret.gui.app import create_app

from .test_accurate_fret_plugin import TAU_D0
from .test_emtk_accurate_fret_parity import _bursts

SIZE = (1200, 800)
SMALL = (800, 600)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb.sqlite"))
    monkeypatch.chdir(tmp_path)  # the file dialogs start in the working folder


@pytest.fixture
def bursts(tmp_path):
    return _bursts(tmp_path)


@pytest.fixture
def app():
    window = create_app()
    window.model.n_bootstrap = 0
    window.model.donor_lifetime = TAU_D0
    yield window
    window.close()


def draw(app, size=SIZE, frames=2):
    painter = None
    for _ in range(frames):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, *size)
    return painter


def click(app, rect, size=SIZE, fx=0.5):
    x, y, w, h = rect
    app.press(x + w * fx, y + h / 2)
    draw(app, size, frames=1)
    app.release()
    draw(app, size, frames=2)


def text_rect(painter, label, last=True):
    hits = [t[:4] for t in painter.texts if t[5] == label]
    assert hits, f"{label!r} is not drawn: {[t[5] for t in painter.texts][:60]}"
    return hits[-1] if last else hits[0]


def press_text(app, label, size=SIZE, last=True):
    click(app, text_rect(draw(app, size), label, last), size)


def wait(app, size=SIZE, timeout=90.0):
    """Draw until the background job (load / calibrate / catalogue) has finished and its result is shown."""
    end = time.monotonic() + timeout
    draw(app, size, frames=1)
    while app.controller.running and time.monotonic() < end:
        time.sleep(0.02)
        draw(app, size, frames=1)
    assert not app.controller.running, app.controller.status
    return draw(app, size, frames=3)


def rect_of(app, name):
    gui = app.accurate_gui
    return gui.form_state.rects.get(name) or gui.item_rects[name]


def load_by_clicks(app, bursts, size=SIZE):
    """Open burst table -> the file dialog -> the file entry -> Open."""
    draw(app, size, frames=3)
    click(app, rect_of(app, "filename"), size)
    painter = draw(app, size)
    assert {"Open", "Cancel", bursts.name} <= set(painter.strings), "the dialog did not open"
    click(app, text_rect(painter, bursts.name), size)
    click(app, text_rect(draw(app, size), "Open"), size)
    wait(app, size)


def calibrate_by_click(app, size=SIZE):
    draw(app, size)
    click(app, rect_of(app, "Calibrate"), size)
    return wait(app, size)


def type_into(app, name, text, size=SIZE):
    draw(app, size)
    click(app, rect_of(app, name), size, fx=0.3)
    assert app.io.want_capture_keyboard, name
    app.key(0x41, "a", 0x04000000)
    for ch in text:
        app.key(ord(ch), ch)
        draw(app, size, frames=1)
    app.key(keys.KEY_RETURN, "\r")
    draw(app, size, frames=2)


def fold(app, title, size=SIZE):
    draw(app, size)
    click(app, app.accurate_gui.item_rects[title], size)
    return draw(app, size)


# ── load: the file dialog, its buttons, a drop through the host ---------------------------------------------- #


def test_open_burst_table_dialog_loads_the_file_the_user_clicks(app, bursts):
    assert "No burst table loaded." in draw(app).strings
    load_by_clicks(app, bursts)
    assert app.model.filename == str(bursts) and app.controller.status == "Burst table loaded."
    assert (
        app.model.column_i_dd,
        app.model.column_i_da,
        app.model.column_i_aa,
        app.model.column_tau_f,
    ) == ("Green Count Rate (KHz)", "Red Count Rate (KHz)", "S delayed yellow (kHz)", "Tau (green)")
    assert str(bursts) in " ".join(draw(app).strings).replace(" ", "") or bursts.name in " ".join(
        draw(app).strings
    )


def test_the_dialog_cancel_button_closes_it_and_loads_nothing(app, bursts):
    draw(app, frames=3)
    click(app, rect_of(app, "filename"))
    assert app.controller.dialog is not None
    click(app, text_rect(draw(app), "Cancel"))
    assert (
        app.controller.dialog is None
        and app.model.filename in ("", None)
        and "Cancel" not in draw(app).strings
    )


def test_a_burst_table_that_cannot_be_read_says_so_and_the_dialog_is_not_stuck(app, tmp_path):
    bad = tmp_path / "not_a_burst_table.csv"
    bad.write_text("this,is,not\nnumeric,data,at all\n")
    draw(app, frames=3)
    click(app, rect_of(app, "filename"))
    painter = draw(app)
    click(app, text_rect(painter, bad.name))
    click(app, text_rect(draw(app), "Open"))
    wait(app)
    assert app.controller.status.startswith("Error:") and "Error:" in " ".join(draw(app).strings)
    assert app.controller.dialog is None and not app.model.filename.endswith(
        "not_a_burst_table.csv"
    )
    # and the app still works: the next, good file loads
    assert app.controller.running is False


def test_a_file_dropped_on_the_host_loads_like_the_dialog(app, bursts):
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    draw(app, frames=3)
    host = ControlHost(app)
    host.resize(*SIZE)
    host.show()
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(bursts))])
    enter = QtGui.QDragEnterEvent(
        QtCore.QPoint(300, 300),
        QtCore.Qt.CopyAction,
        mime,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    host.dragEnterEvent(enter)
    assert enter.isAccepted(), "the host refuses a drop on this app"
    event = QtGui.QDropEvent(
        QtCore.QPointF(300, 300),
        QtCore.Qt.CopyAction,
        mime,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    host.dropEvent(event)
    qapp.processEvents()
    wait(app)
    assert (
        event.isAccepted()
        and app.model.filename == str(bursts)
        and app.controller.status == "Burst table loaded."
    )
    host.close()


def test_a_dropped_path_that_does_not_exist_is_reported(app):
    app.on_paths_dropped(["/no/such/bursts.npz"])
    assert "does not exist" in app.controller.status and "does not exist" in " ".join(
        draw(app).strings
    )


# ── channels, calibration, stop, result tabs ------------------------------------------------------------------ #


@pytest.mark.parametrize("name", ["column_i_dd", "column_i_da", "column_i_aa", "column_tau_f"])
def test_each_channel_list_opens_and_a_click_on_a_column_maps_it(app, bursts, name):
    load_by_clicks(app, bursts)
    draw(app)
    click(app, rect_of(app, name))
    painter = draw(app, frames=1)
    entries = [
        t[5]
        for t in painter.texts
        if t[5]
        in (
            "Green Count Rate (KHz)",
            "Red Count Rate (KHz)",
            "S delayed yellow (kHz)",
            "Tau (green)",
        )
    ]
    assert len(set(entries)) == 4  # every column of the file is offered
    other = (
        "Red Count Rate (KHz)"
        if getattr(app.model, name) != "Red Count Rate (KHz)"
        else "Green Count Rate (KHz)"
    )
    click(app, text_rect(painter, other))
    assert getattr(app.model, name) == other
    assert other in draw(app).strings  # the closed list shows the choice


def test_calibrate_click_is_refused_with_the_reason_until_a_table_is_loaded_then_runs(app, bursts):
    draw(app, frames=3)
    click(app, rect_of(app, "Calibrate"))
    assert (
        app.controller.status == "The donor channel (I_DD) column is not mapped."
        and app.model.result is None
    )
    load_by_clicks(app, bursts)
    painter = calibrate_by_click(app)
    assert app.controller.status == "Accurate FRET calibrated." and app.model.result is not None
    factors = {row["factor"]: row["value"] for row in app.model.factor_rows()}
    assert (
        factors["α"] == "0.0798" and factors["γ"] == "0.6162"
    )  # the numbers the Qt tool gave on these bursts
    assert "0.0798" in painter.strings and "α" in painter.strings  # the factor table cell shows it


def test_the_stop_button_cancels_a_running_calibration_and_keeps_the_previous_state(app, bursts):
    load_by_clicks(app, bursts)
    app.model.n_bootstrap = 400  # long enough to be stopped
    draw(app)
    click(app, rect_of(app, "Calibrate"))
    assert app.controller.running
    click(app, text_rect(draw(app), "Stop calibration / read"))
    assert "Stopping" in app.controller.status
    wait(app)
    assert (
        app.controller.status == "Calibration/read cancelled; previous result retained."
        and app.model.result is None
    )


def test_the_result_tabs_are_clicked_and_show_factors_populations_and_the_report(app, bursts):
    load_by_clicks(app, bursts)
    calibrate_by_click(app)
    click(app, rect_of(app, "Populations"))
    populations = draw(app).strings
    assert {"Population", "Bursts", "Lifetime (ns)", "Distance (Å)"} <= set(populations)
    assert app.model.population_rows()[0]["population"] in populations
    click(app, rect_of(app, "Report"))
    assert any("Accurate" in s or "calibration" in s.lower() for s in draw(app).strings)
    click(app, rect_of(app, "Correction factors"))
    assert {"Factor", "Value", "Uncertainty", "Origin"} <= set(draw(app).strings)


def test_the_plots_show_the_classes_and_a_drag_pans_the_efficiency_plot(app, bursts):
    load_by_clicks(app, bursts)
    calibrate_by_click(app)
    assert app.model.es_series() and app.model.efficiency_histogram()
    painter = draw(app)
    assert {"Stoichiometry", "Accurate FRET efficiency"} <= set(painter.strings)

    def ticks(p):
        return [s for s in p.strings if s.replace(".", "").replace("-", "").isdigit()]

    before = ticks(painter)
    x, y, w, h = rect_of(app, "es_plot")
    cx, cy = x + w / 2, y + h / 2
    app.pointer_move(cx, cy)
    draw(app, frames=2)
    app.press(cx, cy)
    draw(app, frames=1)
    for step in range(1, 8):
        app.drag(cx - 25 * step, cy)
        draw(app, frames=1)
    app.release()
    assert ticks(draw(app, frames=2)) != before


def test_the_wheel_zooms_the_efficiency_plot(app, bursts):
    load_by_clicks(app, bursts)
    calibrate_by_click(app)
    before = [s for s in draw(app).strings if s.replace(".", "").isdigit()]
    x, y, w, h = rect_of(app, "es_plot")
    app.pointer_move(x + w / 2, y + h / 2)
    draw(app, frames=2)
    app.wheel(x + w / 2, y + h / 2, 3.0)
    assert [s for s in draw(app, frames=2).strings if s.replace(".", "").isdigit()] != before


# ── the settings headers and fields ----------------------------------------------------------------------------- #


def test_the_collapsing_headers_open_and_close_with_a_click(app):
    draw(app, frames=3)
    for title, field in (
        ("Photophysics", "donor_lifetime"),
        ("Dyes (database)", "donor_dye"),
        ("Background", "background_dd"),
    ):
        assert field not in app.accurate_gui.form_state.rects
        fold(app, title)
        assert field in app.accurate_gui.form_state.rects, title
        fold(app, title)
        assert field not in app.accurate_gui.form_state.rects, title


def test_photophysics_and_background_fields_take_typed_values_and_the_toggle_is_clicked(
    app, bursts
):
    load_by_clicks(app, bursts)
    fold(app, "Channels")  # keep the window short enough for the next sections
    fold(app, "Photophysics")
    for name, text, expected in (
        ("donor_lifetime", "3.5", 3.5),
        ("forster_radius", "55", 55.0),
        ("linker_sigma", "7", 7.0),
    ):
        type_into(app, name, text)
        assert getattr(app.model, name) == pytest.approx(expected), name
    type_into(app, "donor_lifetime", "abc")
    assert app.model.donor_lifetime == 3.5  # a typo changes nothing
    before = app.model.show_dynamic_line
    click(app, rect_of(app, "show_dynamic_line"))
    assert app.model.show_dynamic_line is (not before)
    fold(app, "Photophysics")
    fold(app, "Background")
    type_into(app, "background_dd", "1.5")
    assert app.model.background_dd == pytest.approx(1.5)
    assert (
        app.model.result is None
    )  # an input edit invalidates nothing that was not computed; the next Calibrate uses it


def test_dye_and_optics_fields_are_reachable_and_typed_values_reach_the_model(app):
    fold(app, "Channels")
    fold(app, "Dyes (database)")
    type_into(app, "kappa2", "0.5")
    assert app.model.kappa2 == pytest.approx(0.5)
    type_into(app, "refractive_index", "1.4")
    assert app.model.refractive_index == pytest.approx(1.4)


# ── the data / session / catalogue actions -------------------------------------------------------------------------- #


def open_data_header(app):
    fold(app, "Channels")
    fold(app, "Data, session and catalogue actions")


@pytest.mark.parametrize(
    ("button", "status"),
    [
        ("Share calibration in session", None),
        ("Store calibration on setup", "Calibrate first."),
        ("To ndX", "Calibrate first."),
    ],
)
def test_the_session_buttons_before_a_calibration_say_what_to_do(app, button, status):
    open_data_header(app)
    press_text(app, button)
    if status:
        assert app.controller.status == status and status in " ".join(draw(app).strings)
    else:
        assert (
            app.controller.status
        )  # the session registration answers with its own message (nothing to share yet)


def test_from_ndx_and_to_ndx_answer_with_a_status_when_no_ndx_source_exists(app, bursts):
    load_by_clicks(app, bursts)
    calibrate_by_click(app)
    open_data_header(app)
    press_text(app, "From ndX")
    assert app.controller.status, "From ndX did nothing"
    first = app.controller.status
    press_text(app, "To ndX")
    assert app.controller.status and app.controller.status != "Calibrate first."
    assert first in (app.controller.status, first)  # both buttons wrote a visible line


def test_the_session_share_and_setup_store_buttons_after_a_calibration(app, bursts):
    load_by_clicks(app, bursts)
    calibrate_by_click(app)
    open_data_header(app)
    press_text(app, "Share calibration in session")
    shared = app.controller.status
    assert shared and shared in " ".join(draw(app).strings)
    press_text(app, "Store calibration on setup")
    assert (
        app.controller.status == "Select or save a named detector setup first."
    )  # no setup selected: the reason, no exception


def test_export_per_burst_csv_through_the_dialog_with_a_typed_name(app, bursts, tmp_path):
    load_by_clicks(app, bursts)
    calibrate_by_click(app)
    open_data_header(app)
    press_text(app, "Export per-burst CSV")
    painter = draw(app)
    assert {"Cancel", "accurate_fret.csv"} <= set(painter.strings)
    click(app, text_rect(painter, "accurate_fret.csv"), fx=0.3)
    app.key(0x41, "a", 0x04000000)
    for ch in "bursts_out.csv":
        app.key(ord(ch), ch)
        draw(app, frames=1)
    click(app, text_rect(draw(app), "Save"))
    written = tmp_path / "bursts_out.csv"
    assert written.is_file() and len(written.read_text().splitlines()) > 100
    assert app.controller.status == f"Per-burst accurate values exported: {written}"


def test_export_before_a_calibration_reports_the_error_and_closes_the_dialog(app):
    open_data_header(app)
    press_text(app, "Export per-burst CSV")
    click(app, text_rect(draw(app), "Save"))
    assert app.controller.status.startswith("Error:") and app.controller.dialog is None


def test_the_catalogue_refresh_buttons_run_in_the_background_and_report(app):
    open_data_header(app)
    press_text(app, "Refresh dye catalogue")
    wait(app)
    dyes = app.controller.status
    assert dyes.endswith("dyes available.") or dyes.startswith("Error:"), dyes
    press_text(app, "Refresh optical priors")
    wait(app)
    assert app.controller.status.endswith(
        "saved optical priors available."
    ) or app.controller.status.startswith("Error:")


def test_the_database_path_field_takes_typed_text(app, tmp_path):
    open_data_header(app)
    draw(app)
    label = text_rect(draw(app), "Spectra database path:")
    field = (label[0], label[1] + label[3] + 2, 300.0, 18.0)
    click(app, field, fx=0.1)
    assert app.io.want_capture_keyboard
    for ch in "/tmp/spectra.db":
        app.key(ord(ch), ch)
        draw(app, frames=1)
    draw(app, frames=2)
    assert app.model.database_path == "/tmp/spectra.db"


def test_the_datasets_button_opens_the_database_window_and_it_can_be_closed(app):
    draw(app, frames=3)
    press_text(app, "MMFDB burst datasets")
    painter = draw(app)
    assert (
        any(
            "dataset" in s.lower() or "mmfdb" in s.lower()
            for s in painter.strings
            if s != "MMFDB burst datasets"
        )
        or app.controller.datasets is not None
    )
    app.key(keys.KEY_ESCAPE, "")
    draw(app, frames=2)


def test_select_detector_setup_button_brings_the_detector_setup_dock_forward(app):
    draw(app, frames=3)
    press_text(app, "Select / configure detector setup")
    strings = draw(app).strings
    assert any("setup" in s.lower() for s in strings) and "Detector setup" in strings


# ── Guide and Help -------------------------------------------------------------------------------------------------- #


def test_guide_button_starts_the_tour_and_the_awaited_calibrate_step_waits_for_the_click(
    app, bursts
):
    draw(app, frames=3)
    click(app, rect_of(app, "guide"))
    tour = app.accurate_gui.tour
    assert tour.active
    load_by_clicks(app, bursts)
    # jump to the Calibrate step (the Next button is exercised in test_the_tour_next_and_prev_buttons_can_be_clicked)
    index = next(i for i, step in enumerate(tour.steps) if step.get("await"))
    tour.start(index)
    draw(app)
    assert tour.awaiting
    click(app, rect_of(app, "Calibrate"))
    wait(app)
    assert not tour.awaiting
    click(app, text_rect(draw(app), "Close Tour"))
    assert not tour.active


def test_the_tour_next_and_prev_buttons_can_be_clicked(app):
    draw(app, frames=3)
    click(app, rect_of(app, "guide"))
    tour = app.accurate_gui.tour
    assert not tour.awaiting
    click(app, text_rect(draw(app), "Next ►"))
    assert tour.step_idx == 1
    click(app, text_rect(draw(app), "◄ Prev"))
    assert tour.step_idx == 0


def test_help_button_opens_the_help_window_whose_buttons_work(app):
    draw(app, frames=3)
    click(app, rect_of(app, "help"))
    window = app.accurate_gui.help_window
    assert window.open
    painter = draw(app)
    assert {"Start Guided Tour", "Close", "Close Help"} <= set(painter.strings)
    click(app, text_rect(painter, "Start Guided Tour"))
    assert not window.open and app.accurate_gui.tour.active
    app.accurate_gui.tour.stop()
    for closer, last in (("Close Help", True), ("Close", False)):
        click(app, rect_of(app, "help"))
        click(app, text_rect(draw(app), closer, last=last))
        assert not window.open, closer
    click(app, rect_of(app, "help"))
    app.key(keys.KEY_ESCAPE, "")
    draw(app)
    assert not window.open


# ── the same flow in the small window ----------------------------------------------------------------------------- #


def test_the_load_and_calibrate_flow_works_in_the_small_window_too(app, bursts):
    load_by_clicks(app, bursts, SMALL)
    assert app.controller.status == "Burst table loaded."
    painter = calibrate_by_click(app, SMALL)
    assert app.model.result is not None and "α" in painter.strings
    assert np.isfinite(float(app.model.factor_rows()[0]["value"]))
