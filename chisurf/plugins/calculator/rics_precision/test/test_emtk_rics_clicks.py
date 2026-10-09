"""The drawn RICS-precision app, driven with simulated pointer and keyboard events.

Every control of the Qt tool (Predict, Export CSV, Guide, ?, the four setting panels, every
field and the Membrane check box, the table and the plot) is used the way a person uses it, and
each test asserts what the next frame shows. The control -> test list is in REPORT.md.
"""

from __future__ import annotations

import time

import pytest
from emtk.events import CONTROL_MODIFIER

from chisurf.plugins.calculator.rics_precision.gui.app import RicsPrecisionApp
from chisurf.plugins.calculator.rics_precision.test.pointer import KEY_ESCAPE, Pointer
from chisurf.plugins.calculator.rics_precision.test.test_emtk_rics_parity import (
    QT_CSV,
    QT_FAILURE,
    QT_ROWS,
    QT_STATUS,
)


@pytest.fixture
def ui():
    app = RicsPrecisionApp()
    app.model.n_repeats, app.model.n_images = 10, 20                    # a small estimator, as in the baseline
    pointer = Pointer(app)
    yield pointer
    app.close()


def center(ui, name):
    x, y, w, h = ui.app.form.rects[name]
    return (x + w / 2.0, y + h / 2.0)


def set_field(ui, name, text):
    ui.click(center(ui, name))
    ui.key(ord("A"), "a", CONTROL_MODIFIER)
    ui.type(text)
    ui.enter()


def finish(ui, limit=120.0):
    """Frames until the sweep the click started is done (the host keeps drawing while it runs)."""
    t0 = time.time()
    while ui.app.job.busy and time.time() - t0 < limit:
        if ui.app.job.thread is not None:
            ui.app.job.thread.join(timeout=0.2)
        ui.frame()
    ui.frame(2)
    assert not ui.app.job.busy


def unfold(ui, title):
    ui.click(title)


# -- Predict -------------------------------------------------------------------------------------
def test_predict_button_runs_the_sweep_and_the_table_and_verdict_appear(ui):
    assert ui.drawn(ui.app.model.status) and not ui.drawn("314.8")
    ui.click("Predict")
    assert ui.app.job.busy or ui.app.model.sweep is not None                         # started by the click
    finish(ui)
    assert ui.app.model.sweep_rows() == QT_ROWS
    assert ui.drawn(QT_STATUS)                                                       # the verdict line
    for row in QT_ROWS:                                                              # every table cell
        for key in ("dwell", "line", "frame", "error"):
            assert ui.drawn(row[key]), (row, key)
    assert not ui.drawn("press Predict to sweep the dwell time")                     # the plot has its curve


def test_predict_is_greyed_while_the_sweep_runs_and_inputs_cannot_be_typed(ui, monkeypatch):
    import threading

    from chisurf.plugins.calculator.rics_precision import core

    gate, real = threading.Event(), core.sweep_dwell

    def slow(*args, progress=None, **kwargs):
        progress(0.25, "Sweeping")
        assert gate.wait(60)
        return real(*args, progress=progress, **kwargs)

    monkeypatch.setattr(core, "sweep_dwell", slow)
    ui.click("Predict")
    t0 = time.time()
    while "25 %" not in ui.app.status_line() and time.time() - t0 < 30:
        time.sleep(0.05)
        ui.frame()
    assert ui.drawn("Sweeping (25 %)")
    ui.click("Predict")                                                              # greyed: no second sweep
    before = ui.app.model.diffusion_coefficient
    ui.click(center(ui, "diffusion_coefficient"))
    ui.key(ord("A"), "a", CONTROL_MODIFIER)
    ui.type("77")
    ui.enter()
    assert ui.app.model.diffusion_coefficient == before                              # the inputs are greyed too
    gate.set()
    finish(ui)
    assert ui.app.model.sweep_rows() == QT_ROWS


def test_a_failing_prediction_shows_the_message_and_clears_the_curve(ui):
    ui.click("Predict")
    finish(ui)
    unfold(ui, "Estimator")
    set_field(ui, "n_lags", "15")
    set_field(ui, "nx", "8")
    set_field(ui, "ny", "8")
    ui.click("Predict")
    finish(ui)
    assert ui.app.model.status == QT_FAILURE
    assert any(QT_FAILURE.split(":")[0] in s for s in ui.strings) and ui.drawn("press Predict to sweep the dwell time")
    assert not ui.drawn("314.8")                                                     # no stale table row
    ui.click("Export CSV")                                                           # nothing to export now
    assert ui.app.dialog is None and ui.drawn("Predict something first.")


# -- Export CSV ------------------------------------------------------------------------------------
def test_export_csv_before_a_prediction_says_so_and_after_writes_the_file(ui, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ui.click("Export CSV")
    assert ui.app.dialog is None and ui.drawn("Predict something first.")
    ui.click("Predict")
    finish(ui)
    ui.click("Export CSV")
    assert ui.app.dialog is not None and ui.drawn("Save") and ui.drawn("Cancel")
    ui.click("Cancel")
    assert ui.app.dialog is None and not list(tmp_path.iterdir())
    ui.click("Export CSV")
    ui.click("Save")                                                                 # the dialog's own default name
    assert (tmp_path / "rics_precision.csv").read_text() == QT_CSV
    assert any(t.startswith("Wrote") for t in ui.strings) and ui.app.notice == f"Wrote {tmp_path / 'rics_precision.csv'}"


def test_export_csv_name_typed_without_a_suffix_gets_csv_and_the_dialog_x_closes_it(ui, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ui.click("Predict")
    finish(ui)
    ui.click("Export CSV")
    ui.click("rics_precision.csv")                                                   # the name field holds the default
    ui.key(ord("A"), "a", CONTROL_MODIFIER)
    ui.type("plan")
    ui.click("Save")
    assert (tmp_path / "plan.csv").read_text() == QT_CSV
    ui.click("Export CSV")
    x, y, w, h = ui.app.file_window.box
    ui.click((x + w - 14.0, y + 13.0))
    assert ui.app.dialog is None
    ui.click("Export CSV")
    ui.move((x + w / 2, y + h / 2))
    ui.key(KEY_ESCAPE)
    assert ui.app.dialog is None


def test_export_to_an_unwritable_place_is_reported(ui, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "blocker").write_text("x")
    ui.click("Predict")
    finish(ui)
    ui.click("Export CSV")
    ui.click("rics_precision.csv")
    ui.key(ord("A"), "a", CONTROL_MODIFIER)
    ui.type("blocker/out")
    ui.click("Save")
    assert ui.app.notice.startswith("Could not write out.csv:")
    assert any(t.startswith("Could not write out.csv:") for t in ui.strings)         # on the status line (wrapped)


# -- the fields ----------------------------------------------------------------------------------------
FIELDS = [
    # attribute, typed text, expected value, the Qt spec's bound that clamps it
    ("diffusion_coefficient", "250", 250.0, ("1e-06", 1e-06, "999999", 100000.0)),
    ("n_particles", "12.5", 12.5, ("0", 0.01, "9999999", 1000000.0)),
    ("brightness_khz", "40", 40.0, ("0", 0.001, "9999999", 100000.0)),
    ("w_r", "0.3", 0.3, ("0", 0.001, "999", 100.0)),
    ("w_z", "1.5", 1.5, ("0", 0.001, "99999", 1000.0)),
    ("pixel_size_nm", "40", 40.0, ("0", 1.0, "9999999", 100000.0)),
    ("pixel_time_us", "12", 12.0, ("0", 0.01, "9999999", 100000.0)),
    ("line_overhead", "1.5", 1.5, ("0", 1.0, "999", 100.0)),
    ("nx", "128", 128, ("1", 8, "99999", 4096)),
    ("ny", "96", 96, ("1", 8, "99999", 4096)),
    ("n_images", "250", 250, ("0", 1, "9999999", 100000)),
]
ESTIMATOR = [
    ("n_lags", "5", 5, ("0", 1, "99", 15)),
    ("n_repeats", "60", 60, ("0", 5, "99999", 2000)),
    ("seed", "7", 7, ("-5", 0, "99999999", 1000000)),
]


@pytest.mark.parametrize(("name", "text", "expected", "limits"), FIELDS + ESTIMATOR)
def test_each_field_takes_typed_text_and_clamps_to_the_qt_range(ui, name, text, expected, limits):
    if (name, text, expected, limits) in ESTIMATOR:
        unfold(ui, "Estimator")
    set_field(ui, name, text)
    assert getattr(ui.app.model, name) == pytest.approx(expected)
    set_field(ui, name, limits[0])
    assert getattr(ui.app.model, name) == pytest.approx(limits[1])
    set_field(ui, name, limits[2])
    assert getattr(ui.app.model, name) == pytest.approx(limits[3])


@pytest.mark.parametrize("name", [n for n, *_ in FIELDS + ESTIMATOR])
def test_each_field_has_working_arrows(ui, name):
    if name in ("n_lags", "n_repeats", "seed"):
        unfold(ui, "Estimator")
    ui.frame(2)
    x, y, w, h = ui.app.form.rects[f"{name}.stepper"]
    start = getattr(ui.app.model, name)
    ui.click((x + w / 2, y + h * 0.25))                                              # up
    up = getattr(ui.app.model, name)
    ui.click((x + w / 2, y + h * 0.75))                                              # down
    ui.click((x + w / 2, y + h * 0.75))
    down = getattr(ui.app.model, name)
    assert up > start and down < up, (name, start, up, down)


def test_typed_values_reach_the_next_prediction(ui):
    set_field(ui, "pixel_time_us", "15.8")                                           # the dwell the Qt run found best
    ui.click("Predict")
    finish(ui)
    assert ui.app.model.pixel_time_us == 15.8
    assert ui.drawn("At 15.8 µs: ") or any(s.startswith("At 15.8 µs") for s in ui.strings)


def test_membrane_checkbox_switches_the_2d_geometry(ui):
    assert ui.app.model.two_d is False
    ui.click(center(ui, "two_d"))
    assert ui.app.model.two_d is True
    ui.click("Predict")
    finish(ui)
    membrane_rows = ui.app.model.sweep_rows()
    assert membrane_rows != QT_ROWS                                                  # another geometry, other numbers
    ui.click(center(ui, "two_d"))
    assert ui.app.model.two_d is False
    ui.click("Predict")
    finish(ui)
    assert ui.app.model.sweep_rows() == QT_ROWS


# -- the panels --------------------------------------------------------------------------------------------
@pytest.mark.parametrize(("title", "field", "open_at_first"), [
    ("Sample", "D [µm²/s]", True), ("Optics", "w_r [µm]", True), ("Scan", "Pixel dwell [µs]", True),
    ("Estimator", "Lags fitted", False)])
def test_panel_headers_fold_and_unfold(ui, title, field, open_at_first):
    assert ui.drawn(field) is open_at_first
    ui.click(title)
    assert ui.drawn(field) is (not open_at_first)
    ui.click(title)
    assert ui.drawn(field) is open_at_first


# -- Guide and Help ------------------------------------------------------------------------------------------
def test_help_button_opens_and_closes_the_help_window(ui):
    ui.click("Help")
    assert ui.app.help_window.open and ui.drawn("Close Help")
    ui.click("Close Help")
    assert not ui.app.help_window.open


def test_guide_button_starts_the_tour_and_it_waits_for_the_controls(ui):
    ui.click("Guide")
    assert ui.app.tour.active and ui.drawn("Step 1 of 6: The one tool here you use before the measurement")
    ui.app.tour.start(1)
    ui.frame(2)
    assert ui.app.tour.awaiting and ui.drawn("Step 2 of 6: Start from the D you expect")
    set_field(ui, "diffusion_coefficient", "30")                                     # the highlighted field
    assert not ui.app.tour.awaiting
    predict_step = next(i for i, s in enumerate(ui.app.tour.steps) if s["target"] == {"action": "request_predict"})
    ui.app.tour.start(predict_step)
    ui.frame(2)
    assert ui.app.tour.awaiting
    ui.click("Predict")                                                              # the highlighted button
    assert not ui.app.tour.awaiting
    finish(ui)
    ui.click("Close Tour")
    assert not ui.app.tour.active


def test_the_tour_next_and_prev_buttons_can_be_clicked(ui):
    ui.app.tour.start(2)
    ui.frame(3)
    ui.click("Next ►")
    assert ui.app.tour.step_idx == 3
    ui.click("◄ Prev")
    assert ui.app.tour.step_idx == 2


# -- the plot and the table -----------------------------------------------------------------------------------
def test_the_plot_takes_the_wheel_and_a_drag_without_losing_the_curve(ui):
    ui.click("Predict")
    finish(ui)
    px, py, pw, ph = ui.app.item_rects["plot"]
    ui.wheel((px + pw / 2, py + ph / 2), 3)                                          # zoom in
    ui.drag((px + pw * 0.5, py + ph * 0.5), (px + pw * 0.4, py + ph * 0.5))          # pan
    assert ui.app.model.sweep_rows() == QT_ROWS and not ui.drawn("press Predict to sweep the dwell time")


def test_clicking_a_table_header_sorts_the_rows_by_that_column(ui):
    ui.click("Predict")
    finish(ui)
    first = [t for t in ui.painter.texts if t[5] in ("0.5", "500")]
    assert first, "the dwell cells are drawn"
    ui.click("Error [%]")                                                            # ascending: the smallest first
    assert ui.drawn("▴ Error [%]")
    ys = {t[5]: t[1] for t in ui.painter.texts if t[5] in ("314.8", "4.5")}
    assert ys["4.5"] < ys["314.8"]
    ui.click("▴ Error [%]")                                                          # again: descending
    ui.frame(3)
    assert ui.drawn("▾ Error [%]")
    ys = {t[5]: t[1] for t in ui.painter.texts if t[5] in ("314.8", "4.5")}
    assert ys["314.8"] < ys["4.5"]                                                   # the largest error is the first row
