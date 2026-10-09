"""Click coverage of the native κ² calculator: every control is operated with simulated pointer and keyboard events.

Only ``press`` / ``release`` / ``pointer_move`` / ``wheel`` / ``key`` at the rectangles the controls were drawn in (or
at the text a button drew) reach the window; the assertions read the visible outcome (model values, status line,
statistics table, dialog, windows). The coverage list control -> test is in
``okf/plugins/emtk-ports/kappa2_dist/REPORT.md``.
"""

from __future__ import annotations

import numpy as np
import pytest
from emtk import keys

from .test_emtk_kappa2_dist_verify import (  # noqa: F401  (hermetic is an autouse fixture)
    REPO,
    SIZE,
    SMALL,
    click,
    draw,
    hermetic,
    make_app,
    pick_model,
    settle,
    type_into,
)


@pytest.fixture
def app():
    np.random.seed(7)
    return make_app()


def text_rect(painter, label, last=True):
    """The rectangle of the drawn text *label* (a button caption or a list entry)."""
    hits = [t[:4] for t in painter.texts if t[5] == label]
    assert hits, f"{label!r} is not drawn: {[t[5] for t in painter.texts][:50]}"
    return hits[-1] if last else hits[0]


def press_text(app, label, size=SIZE, last=True):
    click(app, text_rect(draw(app, size), label, last), size)


def arrow(app, name, direction, size=SIZE):
    """Click the upper (+1) or lower (-1) arrow of a field and wait for the recomputation."""
    draw(app, size)
    x, y, w, h = app.item_rects[f"{name}.stepper"]
    np.random.seed(7)
    app.press(x + w / 2, y + h * (0.25 if direction > 0 else 0.75))
    draw(app, size, frames=1)
    app.release()
    settle(app, size)


# ── the eight spin fields -------------------------------------------------------------------------------- #

STEPS = {
    "r_0": 0.01,
    "r_Dinf": 0.01,
    "r_Ainf": 0.01,
    "r_ADinf": 0.001,
    "kappa2_true": 0.01,
    "fret_efficiency": 0.01,
    "step": 0.1,
    "n_bins": 1,
}


@pytest.mark.parametrize("name", list(STEPS))
def test_each_arrow_steps_its_field_by_the_qt_step_and_recomputes(app, name):
    m = app.tool._model
    if name == "fret_efficiency":
        type_into(app, name, "0.5")  # the default 0.001 is already the Qt minimum
    start = getattr(m, name)
    mean = m.k2_mean
    arrow(app, name, +1)
    assert getattr(m, name) == pytest.approx(start + STEPS[name]), name
    arrow(app, name, -1)
    arrow(app, name, -1)
    assert getattr(m, name) == pytest.approx(start - STEPS[name]), name
    arrow(app, name, +1)
    assert getattr(m, name) == pytest.approx(start)
    assert (
        m.k2_mean != 0.0 and mean != 0.0
    )  # the distribution was recomputed on every click (no stale zero)


def test_an_arrow_stops_at_the_qt_limit(app):
    m = app.tool._model
    type_into(app, "r_Dinf", "0.4")
    arrow(app, "r_Dinf", +1)
    assert m.r_Dinf == 0.4
    type_into(app, "n_bins", "5")
    arrow(app, "n_bins", -1)
    assert m.n_bins == 5


def test_every_edit_recomputes_the_statistics_table_and_the_plot(app):
    before = {r["quantity"]: r["value"] for r in app.kappa2_gui.result_rows()}
    type_into(app, "r_Dinf", "0.3")
    after = {r["quantity"]: r["value"] for r in app.kappa2_gui.result_rows()}
    assert (
        after["SD R_app/R_DA"] != before["SD R_app/R_DA"]
        and after["SD₂ (donor)"] != before["SD₂ (donor)"]
    )
    shown = draw(app).strings
    assert after["SD R_app/R_DA"] in shown  # the table cell shows the new value


def test_clicking_away_commits_a_typed_value(app):
    m = app.tool._model
    draw(app)
    click(app, app.item_rects["r_0"], fx=0.3)
    app.key(0x41, "a", 0x04000000)
    for ch in "0.3":
        app.key(ord(ch), ch)
        draw(app, frames=1)
    assert m.r_0 == 0.38
    np.random.seed(7)
    click(app, app.item_rects["step"], fx=0.3)
    settle(app)
    assert m.r_0 == 0.3


# ── the model choice and the checkbox ------------------------------------------------------------------ #


def test_the_model_combo_lists_three_entries_and_each_can_be_clicked(app):
    m = app.tool._model
    for label, value in (
        ("DWT (Diffusion)", "diffusion"),
        ("Isotropic", "isotropic"),
        ("WIC (Cone)", "cone"),
    ):
        pick_model(app, label)
        assert m.model_type == value
        assert label in draw(app).strings  # the closed combo shows the choice
    assert m.k2_sd == pytest.approx(
        0.2192, abs=0.02
    )  # back on the cone model: the cone's spread, not the isotropic 0.72


def test_escape_closes_the_open_model_list_without_choosing(app):
    draw(app)
    click(app, app.item_rects["model_type"])
    assert {"DWT (Diffusion)", "Isotropic"} <= set(draw(app, frames=1).strings)
    app.key(keys.KEY_ESCAPE, "")
    draw(app, frames=2)
    assert app.tool._model.model_type == "cone"


def test_the_rad_known_checkbox_is_clicked_and_recomputes(app):
    m = app.tool._model
    draw(app)
    np.random.seed(7)
    click(app, app.item_rects["rAD_known"])
    settle(app)
    assert m.rAD_known is True
    np.random.seed(7)
    click(app, app.item_rects["rAD_known"])
    settle(app)
    assert m.rAD_known is False
    assert m.k2_mean == pytest.approx(
        0.66644, abs=1e-5
    )  # the unchecked seed-7 value the Qt tool showed


# ── Compute, Save, Guide, Help ------------------------------------------------------------------------------- #


def test_the_compute_button_recomputes_and_is_disabled_while_a_run_is_in_flight(app):
    draw(app)
    first = app.tool._model.k2_mean
    np.random.seed(5)
    press_text(app, "Compute")
    settle(app)
    assert app.tool._model.k2_mean != first
    app.kappa2_gui.on_compute()
    assert app.tool.busy
    runs = []
    app.kappa2_gui.on_compute = lambda: runs.append(1)
    press_text(app, "Compute")  # disabled while busy: the click does nothing
    assert runs == []
    settle(app)


def open_save_dialog(app, monkeypatch, tmp_path, size=SIZE):
    monkeypatch.chdir(tmp_path)
    draw(app, size)
    click(app, app.item_rects["save"], size)
    painter = draw(app, size)
    assert {"Cancel", "kappa2.csv"} <= set(painter.strings), (
        "the Save click did not open the dialog"
    )
    return painter


def test_save_click_opens_the_dialog_and_its_cancel_button_closes_it_writing_nothing(
    app, monkeypatch, tmp_path
):
    open_save_dialog(app, monkeypatch, tmp_path)
    click(app, text_rect(draw(app), "Cancel"))
    assert "Cancel" not in draw(app).strings
    assert not list(tmp_path.glob("*.csv")) and app.tool.status == ""


def test_the_save_dialog_window_has_a_close_button_that_dismisses_it(app, monkeypatch, tmp_path):
    open_save_dialog(app, monkeypatch, tmp_path)
    click(app, text_rect(draw(app), "×"))
    assert "Cancel" not in draw(app).strings and not list(tmp_path.glob("*.csv"))


def test_save_with_a_typed_file_name_writes_the_csv_and_the_status_line_says_so(
    app, monkeypatch, tmp_path
):
    open_save_dialog(app, monkeypatch, tmp_path)
    draw(app)
    click(app, text_rect(draw(app), "kappa2.csv"), fx=0.3)  # the file name field
    assert app.io.want_capture_keyboard
    app.key(0x41, "a", 0x04000000)
    for ch in "my_k2":
        app.key(ord(ch), ch)
        draw(app, frames=1)
    click(app, text_rect(draw(app), "Save"))  # the dialog's own Save button (the last "Save" drawn)
    written = tmp_path / "my_k2.csv"
    assert written.is_file(), [p.name for p in tmp_path.iterdir()]
    lines = written.read_text().splitlines()
    qt_lines = (REPO / "okf/plugins/emtk-ports/kappa2_dist/qt_saved.csv").read_text().splitlines()
    assert (
        lines[0] == "# Kappa2 Distribution"
        and lines[-1].count(",") == 1
        and len(lines) == len(qt_lines) == 141
    )
    assert app.tool.status == f"Saved to my_k2.csv ({tmp_path})"
    shown = " ".join(draw(app).strings)
    assert "Saved to my_k2.csv" in shown and "Cancel" not in shown  # the dialog closed


def test_the_save_button_is_greyed_without_a_distribution_and_a_click_then_opens_nothing(
    app, monkeypatch, tmp_path
):
    app.tool._model._k2hist = None
    monkeypatch.chdir(tmp_path)
    draw(app)
    click(app, app.item_rects["save"])
    assert "Cancel" not in draw(app).strings


def test_guide_button_starts_the_tour_and_the_tour_card_buttons_work(app):
    press_text(app, "Guide")
    tour = app.kappa2_gui.tour
    assert tour.active
    tour.next()  # step 1 (introduction) -> 2: the model choice (the Next button's callback; its click is test_the_tour_next_button_can_be_clicked)
    draw(app)
    assert tour.awaiting
    pick_model(app, "Isotropic")  # the user operates the highlighted control
    assert not tour.awaiting
    click(app, text_rect(draw(app), "Close Tour"))
    assert not tour.active


def test_the_tour_next_button_can_be_clicked(app):
    tour = app.kappa2_gui.tour
    press_text(app, "Guide")
    draw(app)
    assert not tour.awaiting  # the first step is an introduction
    click(app, text_rect(draw(app), "Next ►"))
    assert tour.step_idx == 1


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(app):
    tour = app.kappa2_gui.tour
    press_text(app, "Guide")
    guard = 0
    while tour.active and guard < 30:
        guard += 1
        draw(app)
        step = tour.steps[tour.step_idx]
        key = (step.get("target") or {}).get("attr") or (step.get("target") or {}).get("key")
        if tour.awaiting:
            if key == "model_type":
                pick_model(app, "Isotropic" if tour.step_idx == 1 else "WIC (Cone)")
            elif key == "compute":
                np.random.seed(7)
                press_text(app, "Compute")
                settle(app)
            elif key == "r_Dinf":
                type_into(app, "r_Dinf", "0.2")
            assert not tour.awaiting, f"{step['title']}: operating {key} did not release the step"
        tour.next()
    assert (
        not tour.active and app.tool._model.model_type == "cone" and app.tool._model.r_Dinf == 0.2
    )


def test_help_button_opens_the_help_window_whose_buttons_work(app):
    press_text(app, "Help")
    window = app.kappa2_gui.help_window
    assert window.open
    painter = draw(app)
    assert {"Start Guided Tour", "Close", "Close Help"} <= set(painter.strings)
    click(app, text_rect(painter, "Start Guided Tour"))
    assert not window.open and app.kappa2_gui.tour.active
    app.kappa2_gui.tour.stop()
    for closer in ("Close Help", "Close"):
        press_text(app, "Help")
        click(app, text_rect(draw(app), closer, last=False if closer == "Close" else True))
        assert not window.open, closer
    press_text(app, "Help")
    app.key(keys.KEY_ESCAPE, "")
    draw(app)
    assert not window.open


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the help window's section buttons are all '...##filter' (one id), so a click on any but "
    "the first never fires; see REPORT.md section 10",
)
def test_a_help_section_button_shows_only_that_section(app):
    press_text(app, "Help")
    click(app, text_rect(draw(app), "The three models"))
    shown = " ".join(draw(app).strings)
    assert "wobbling" in shown.lower() and "What you need to measure first" not in shown


# ── the statistics table and the plot --------------------------------------------------------------------------- #


def test_a_click_on_a_statistics_row_selects_it_and_changes_no_value(app):
    draw(app)
    before = {r["quantity"]: r["value"] for r in app.kappa2_gui.result_rows()}
    inputs = app.export_settings()
    click(app, text_rect(draw(app), "SD κ²"))
    click(app, text_rect(draw(app), "Quantity"))  # the header
    assert {r["quantity"]: r["value"] for r in app.kappa2_gui.result_rows()} == before
    assert app.export_settings() == inputs and not app.tool.busy
    assert {"Mean κ²", "SD κ²", "δ (deg)"} <= set(draw(app).strings)


def tick_labels(painter):
    return [s for s in painter.strings if s.replace(".", "").replace("-", "").isdigit()]


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the wheel never reaches an implot inside a DockManager window, so no docked plot can be "
    "zoomed with it (works in a plain im.begin window); see REPORT.md section 10",
)
def test_the_wheel_zooms_the_distribution_plot(app):
    draw(app)
    before = tick_labels(draw(app))
    x, y, w, h = app.item_rects["plot"]
    app.pointer_move(x + w / 2, y + h / 2)
    draw(app, frames=2)
    app.wheel(x + w / 2, y + h / 2, 3.0)
    assert tick_labels(draw(app, frames=2)) != before


def test_a_drag_pans_the_distribution_plot(app):
    draw(app)
    before = tick_labels(draw(app))
    x, y, w, h = app.item_rects["plot"]
    cx, cy = x + w / 2, y + h / 2
    app.pointer_move(cx, cy)
    draw(app, frames=2)
    app.press(cx, cy)
    draw(app, frames=1)
    for step in range(1, 8):
        app.drag(cx - 30 * step, cy)
        draw(app, frames=1)
    app.release()
    assert tick_labels(draw(app, frames=2)) != before


# ── the host: no file drop (the Qt widget accepted none either) ------------------------------------------------- #


def test_the_qt_host_refuses_a_dropped_file_as_the_qt_widget_did(app):
    QtWidgets = pytest.importorskip("qtpy.QtWidgets")
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication(
        []
    )  # kept alive for the host
    host = ControlHost(app)
    host.resize(*SIZE)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile("/tmp/run.ptu")])
    enter = QtGui.QDragEnterEvent(
        QtCore.QPoint(10, 10),
        QtCore.Qt.CopyAction,
        mime,
        QtCore.Qt.LeftButton,
        QtCore.Qt.NoModifier,
    )
    host.dragEnterEvent(enter)
    assert not enter.isAccepted() and qapp is not None
    host.close()


# ── the same flow in the small window --------------------------------------------------------------------------- #


def test_the_flow_works_in_the_small_window_too(app):
    m = app.tool._model
    draw(app, SMALL)
    type_into(app, "r_Dinf", "0.2", size=SMALL)
    assert m.r_Dinf == 0.2
    pick_model(app, "Isotropic", size=SMALL)
    assert m.model_type == "isotropic"
    draw(app, SMALL)
    click(app, app.item_rects["save"], SMALL)
    assert "Cancel" in draw(app, SMALL).strings
    click(app, text_rect(draw(app, SMALL), "Cancel"), SMALL)
    assert "Cancel" not in draw(app, SMALL).strings
