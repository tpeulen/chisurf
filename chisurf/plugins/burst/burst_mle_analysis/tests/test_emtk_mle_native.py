"""The standalone emtk burst-MLE app (cards ML0-ML5): real input on the in-repository BH SPC-132 sample.

The sample (``burst_selection/tests/data``, copied to a temp folder by ``conftest``) is added by a host file drop, the
IRF and background are estimated by a click on Auto IRF/background, bursts are fitted by a click on Fit bursts. Every
number drawn is compared with the engine's session (itself compared with the Qt wizard in ``test_mle_engine.py``).
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import implot, keys

from chisurf.plugins.burst.burst_mle_analysis import engine
from chisurf.plugins.burst.burst_mle_analysis.gui import fit_view
from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app
from chisurf.plugins.emtk_test_input import SMALL, Driver

from .conftest import BURST_TABLE, CHANNEL_SETTINGS
from .test_emtk_mle_no_invented_data import PlotSpy, texts

GUI = Path(__file__).parents[1] / "gui"
TABS = ("Decay and fit", "Inspected burst", "Burst lifetimes", "Lifetime table")


def wait(drv, timeout=240.0):
    end = time.monotonic() + timeout
    drv.draw(1)
    while drv.app.job.busy and time.monotonic() < end:
        time.sleep(0.05)
        drv.draw(1)
    assert not drv.app.job.busy, "the job did not finish"
    drv.draw(2)


@pytest.fixture(scope="module")
def burst_table(sample_copy):
    return sample_copy / BURST_TABLE


@pytest.fixture
def app(hermetic_env):
    window = create_app()
    yield window
    window.close()


@pytest.fixture(scope="module")
def fitted(hermetic_env, burst_table):
    """One app with the sample dropped in and Auto IRF/background clicked (module-wide: the fit is the slow part)."""
    window = create_app()
    drv = Driver(window)
    window.editor.model.data["detectors"] = json.loads(json.dumps(CHANNEL_SETTINGS["detectors"]))
    window.model.set_setup(CHANNEL_SETTINGS)
    assert drv.drop(burst_table)
    drv.draw()
    drv.click_name("auto")
    wait(drv)
    assert window.model.fit_curves is not None, window.model.status_text
    yield window, drv
    window.close()


def test_empty_state_draws_no_data_at_both_sizes(monkeypatch, app):
    spy = PlotSpy(monkeypatch)
    shown = set()
    for size in ((1200, 800), SMALL):
        drv = Driver(app, size)
        shown.update(" ".join(texts(drv.draw())).split(". "))
        for tab in TABS:
            drv.click_text(tab)
            shown.update(" ".join(texts(drv.draw())).split(". "))
    assert spy.calls == []
    text = " ".join(shown)
    for message in ("No fit yet", "No burst lifetimes yet", "No bursts loaded", "No lifetime table yet", "Add burst (.bur) files to begin"):
        assert message in text, message


def test_a_dropped_burst_table_loads_the_analysis_and_lists_the_file(app, burst_table):
    drv = Driver(app)
    assert drv.drop(burst_table)
    assert app.model.n_bursts == 2980 and [p.name for p in app.model.session.bur_files] == ["m000.bur"]
    shown = texts(drv.draw(2))
    assert "m000.bur" in shown
    assert not drv.drop(burst_table), "a table already listed is not added twice"
    assert not drv.drop("/no/such/file.txt")


def test_auto_irf_background_click_equals_the_engine_and_draws_its_curves(monkeypatch, fitted):
    window, drv = fitted
    session = window.model.session
    reference = engine.MleSession()
    reference.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    reference.add_burst_files(list(session.bur_files))
    reference.current_detector = "green"
    reference.auto_extract()
    assert window.model.tau_result == pytest.approx(reference.outcome.x[0], rel=1e-9)
    np.testing.assert_array_equal(session.decay, reference.decay)
    assert 0.5 < window.model.tau_result < 5.0
    spy = PlotSpy(monkeypatch)
    drv.click_text("Decay and fit")
    for _ in range(2):
        spy.clear()
        drv.draw(1)
    curves = window.model.fit_curves
    np.testing.assert_array_equal(spy.named("Data (VV|VH)")[2][1], curves.data)
    np.testing.assert_allclose(spy.named("Model (fit)")[2][1], curves.model)
    assert sorted(c[1] for c in spy.calls) == ["Background", "Data (VV|VH)", "IRF", "Model (fit)"]


def test_typing_the_window_refits_and_changes_the_curves(fitted):
    window, drv = fitted
    start, stop = window.model.micro_time_start, window.model.micro_time_stop
    n = window.model.fit_curves.data.size
    drv.type_into_name("micro_time_stop", str(stop - 20))
    assert window.model.micro_time_stop == stop - 20 and window.model.fit_curves.data.size < n
    drv.type_into_name("micro_time_stop", str(stop))
    assert window.model.fit_curves.data.size == n


def window_table(window):
    return window.form.tables["parameter_records"].control


def test_the_parameter_table_edits_a_start_value_and_a_fixed_flag(fitted):
    window, drv = fitted
    shown = texts(drv.draw(2))
    assert "tau" in shown and "gamma" in shown
    # double click the Start cell of tau (the first '4' under the Start column), type, Enter
    rec = {r["name"]: r for r in window.model.parameter_records()}
    assert rec["tau"]["start"] == 4.0 and rec["gamma"]["fixed"] is True
    cell = drv.text_rect(drv.draw(2), "4")
    drv.click((cell[0], cell[1], cell[2], cell[3]), clicks=2)
    assert window_table(window).editing is not None, "a double click on the Start cell did not open it"
    for _ in range(8):  # empty the open cell with the keyboard: End, then Backspace
        drv.app.key(keys.KEY_END, "")
        drv.app.key(keys.KEY_BACKSPACE, "")
        drv.draw(1)
    drv.type("3")
    drv.enter()
    assert window.model.tau == 3.0, "typing into the Start cell did not reach the model"
    before = window.model.session.outcome
    assert before is not None and before.x[0] != 4.0
    window.model.tau = 4.0
    # the Fixed check box of gamma: a click on its cell flips the flag (real pointer press at the drawn cell)
    painter = drv.draw(2)
    header = drv.text_rect(painter, "Fixed")
    row = drv.text_rect(painter, "gamma")
    assert window.model.fix_gamma is True
    drv.click((header[0] + 4, row[1], 20.0, row[3]))
    assert window.model.fix_gamma is False and window.model.parameter_records()[1]["fixed"] is False
    drv.click((header[0] + 4, row[1], 20.0, row[3]))
    assert window.model.fix_gamma is True


def test_the_binning_choice_re_estimates_the_patterns_and_refits(fitted):
    window, drv = fitted
    old = window.model.binning
    window.model.binning = old * 2
    assert window.model.session.irf_np["green"].size == window.model.session.decay.size
    assert window.model.fit_curves is not None
    window.model.binning = old
    assert window.model.session.irf_np["green"].size == window.model.session.decay.size


@pytest.fixture(scope="module")
def batch(fitted):
    window, drv = fitted
    for det in ("green", "red"):
        window.model.current_detector = det
        window.model.auto_extract()
    window.model.current_detector = "green"
    drv.draw(2)
    drv.click_name("toolAction_run")
    wait(drv)
    assert window.model.burst_results, window.model.status_text
    return window, drv


def test_fit_bursts_click_gives_the_engines_rows_histogram_and_table(monkeypatch, batch, fitted):
    window, drv = batch
    rows = window.model.burst_results
    lifetimes = fit_view.burst_lifetimes(rows)
    assert {"green", "red"} <= set(lifetimes) and lifetimes["green"].size > 100
    spy = PlotSpy(monkeypatch)
    drv.click_text("Burst lifetimes")
    for _ in range(2):
        spy.clear()
        drv.draw(1)
    bars = [c for c in spy.calls if c[0] == "plot_bars"]
    assert [c[1] for c in bars] == sorted(lifetimes)
    everything = np.concatenate(list(lifetimes.values()))
    edges = np.linspace(everything.min(), everything.max(), fit_view.LIFETIME_BINS + 1)
    for call in bars:
        np.testing.assert_array_equal(call[2][1], np.histogram(lifetimes[call[1]], bins=edges)[0])
    table = {r["series"]: r for r in window.model.lifetime_rows()}
    assert table["green"]["median"] == f"{np.median(lifetimes['green']):.3f}"
    drv.click_text("Lifetime table")
    shown = texts(drv.draw(2))
    assert table["green"]["median"] in shown and table["red"]["n"] in shown


def test_the_batch_rows_equal_the_engines_batch(batch):
    window, _drv = batch
    session = window.model.session
    again = session.run_batch()
    mine = np.sort(np.array([r["Tau (green)"] for r in again if "Tau (green)" in r and np.isfinite(r["Tau (green)"])]))
    theirs = np.sort(np.array([r["Tau (green)"] for r in window.model.burst_results if "Tau (green)" in r and np.isfinite(r["Tau (green)"])]))
    np.testing.assert_allclose(mine, theirs, rtol=1e-12)


def test_save_results_click_writes_the_b4_tables(batch, burst_table):
    window, drv = batch
    drv.click_name("save_results")
    drv.draw(2)
    assert "file(s) written" in window.model.status_text, window.model.status_text
    folder = burst_table.parent.parent
    assert (folder / "bg4" / "m000.bg4").is_file() and (folder / "br4" / "m000.br4").is_file()
    text = (folder / "bg4" / "m000.bg4").read_text().splitlines()
    assert text[0].startswith("Ng-p-all") and "Tau (green)" in text[0]


def test_the_inspected_burst_follows_the_burst_field(monkeypatch, batch):
    window, drv = batch
    spy = PlotSpy(monkeypatch)
    drv.click_text("Inspected burst")
    drv.draw(2)
    drv.type_into_name("nav_burst", "12")
    assert window.model.nav_burst == 12
    spy.clear()
    drv.draw(1)
    expected = window.model.session.inspect_burst(12)
    lines = {c[1]: c for c in spy.calls if c[0] == "plot_line"}
    assert sorted(lines) == sorted(expected)
    for det, hist in expected.items():
        np.testing.assert_array_equal(lines[det][2][1], hist)


def test_the_detector_setup_is_the_shared_editor_and_its_edits_reach_the_session(app):
    drv = Driver(app)
    shown = texts(drv.draw(2)) + texts(drv.draw(1))
    drv.click_text("Detector setup")
    assert "Detector Name" in texts(drv.draw(2))
    rec = next(r for r in app.editor.detector_rows() if r["name"] == "red")
    app.editor.edit_detector(rec, "chs", "8, 9, 10")
    assert app.model.session.detectors["red"]["chs"] == [8, 9, 10]


def test_settings_round_trip_through_the_file_dialog(app, tmp_path):
    drv = Driver(app)
    app.model.tau = 2.5
    app.model.micro_time_stop = 99
    app.browse("save_settings")
    drv.draw(3)
    app.dialog.directory = str(tmp_path)
    app.dialog.filename = "s.json"
    drv.click_text("Save")
    assert (tmp_path / "s.json").exists()
    app.model.tau = 1.0
    app.browse("load_settings")
    drv.draw(3)
    app.dialog.directory = str(tmp_path)
    drv.click_text("s.json")
    drv.click_text("Open")
    assert app.model.tau == 2.5 and app.model.micro_time_stop == 99


def test_add_files_dialog_adds_a_table(app, burst_table):
    drv = Driver(app)
    drv.click_name("add_files")
    drv.draw(3)
    assert app.dialog is not None
    app.dialog.directory = str(burst_table.parent)
    drv.click_text("m000.bur")
    drv.click_text("Open")
    assert app.model.n_bursts == 2980


def test_guide_targets_are_drawn_and_the_awaited_steps_are_released_by_presses(app, burst_table):
    drv = Driver(app)
    assert drv.drop(burst_table)
    drv.draw(2)
    steps = json.loads((GUI / "guide.json").read_text())["steps"]
    for step in steps:
        key = app.tour._target_key(step.get("target"))
        if key and key not in ("decay", "distribution"):  # those two are in the plot tabs
            assert key in app.item_rects or key in app.form.rects, key
    awaited = [i for i, s in enumerate(steps) if s.get("await")]
    app.start_guide()
    app.tour.step_idx = awaited[0]
    drv.draw(2)
    assert app.tour.awaiting
    drv.click_name("auto")
    wait(drv)
    assert not app.tour.awaiting


def test_the_engine_session_not_the_wizard_is_behind_the_app():
    import subprocess
    import sys

    code = (
        "import sys; import chisurf.plugins.burst.burst_mle_analysis.gui.native as n; "
        "bad=[m for m in sys.modules if m.startswith('chisurf.plugins.burst.burst_mle_analysis.wizard') or m.split('.')[0] in ('PyQt5','qtpy')]; "
        "print(bad); raise SystemExit(1 if bad else 0)"
    )
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
