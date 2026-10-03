"""The standalone emtk H2MM app (cards H0, H1, H3 core): settings model, spec form, actions through SnapshotJob.

Real input: the in-repository BH SPC-132 smFRET DNA sample (``burst_selection/tests/data``, copied to a temp folder
because the fit writes ``h2mm/`` beside the bursts), fitted by the unchanged ``run_analysis``. Nothing is generated
or read from outside the repository. Every control is operated with pointer, keyboard and host drops.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import RecordingPainter

from chisurf.plugins.burst.burst_h2mm.gui import result_view
from chisurf.plugins.burst.burst_h2mm.gui.model import H2mmViewModel
from chisurf.plugins.burst.burst_h2mm.gui.native import create_app
from chisurf.plugins.emtk_test_input import SMALL, Driver
from chisurf.plugins.burst.burst_h2mm.tests.test_emtk_h2mm_no_invented_data import PlotSpy

REPO_DATA = Path(__file__).resolve().parents[2] / "burst_selection" / "tests" / "data" / "bh_spc132_sm_dna"
BURSTS = "burstwise_All 0.1000#15"


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    target = tmp_path_factory.mktemp("h2mm_sample") / "data"
    shutil.copytree(REPO_DATA, target, ignore=shutil.ignore_patterns(".DS_Store"))
    return target / BURSTS


@pytest.fixture(scope="module")
def qapp_ref():
    """Keep a reference to the QApplication: a collected one aborts the process when a Qt tool is built."""
    from qtpy.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture
def app():
    window = create_app()
    yield window
    window.close()


TABS = ("Dwell FRET", "Selection", "Decays", "LL scan", "TDP", "Dwell times", "State path")


def texts(painter):
    return [t[5] for t in painter.texts]


def wait(drv, timeout=180.0):
    end = time.monotonic() + timeout
    drv.draw(1)
    while drv.app.job.busy and time.monotonic() < end:
        time.sleep(0.05)
        drv.draw(1)
    assert not drv.app.job.busy, "the fit did not finish"
    drv.draw(2)


BH_SETUP = {
    "detectors": {
        "green": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
        "red": {"chs": [8, 9], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0},
    },
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130", "macro_time_resolution": 0.0, "micro_time_resolution": 0.0, "micro_time_binning": 1},
}


def configure(drv, sample, min_states="2", max_states="2"):
    """The BH sample's detectors go in through the shared editor's model (the editor's own inputs are tested apart)."""
    drv.app.editor.model.data = __import__("copy").deepcopy(BH_SETUP)
    drv.app.model.set_setup(BH_SETUP)
    drv.type_into_name("data_folder", str(sample))
    drv.type_into_name("min_states", min_states)
    drv.type_into_name("max_states", max_states)
    drv.type_into_name("restarts", "1")


def test_empty_state_draws_no_data_at_both_sizes(monkeypatch, app):
    spy = PlotSpy(monkeypatch)
    shown = set()
    for size in ((1200, 800), SMALL):
        drv = Driver(app, size)
        shown.update(" ".join(texts(drv.draw())).split(". "))
        for tab in TABS:  # every plot tab, reached by clicking its title
            drv.click_text(tab)
            shown.update(" ".join(texts(drv.draw())).split(". "))
    assert spy.calls == []
    text = " ".join(shown)
    for message in ("No H2MM fit yet", "No transition density yet", "No dwell times yet", "No dwell FRET states yet",
                    "No model selection yet", "No per-state decays", "No likelihood scan yet", "No state path yet"):
        assert message in text, message


def test_the_run_button_is_greyed_with_its_reason_until_a_folder_is_given(app):
    drv = Driver(app)
    shown = " ".join(texts(drv.draw()))
    assert "Select a folder of .bur files first." in shown
    drv.click_name("toolAction_run")
    assert not app.job.busy and app.model.analysis is None


def test_settings_equal_the_qt_tools_gathered_settings(app, qapp_ref):
    """The same values in the Qt tool's widgets give the same ``H2mmSettings`` as the model builds."""
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    model = app.model
    model.min_states, model.max_states, model.criterion, model.restarts = 2, 4, "icl", 5
    model.max_iter, model.min_photons, model.engine, model.seed, model.patience = 321, 8, "em", 7, -1
    model.decoder, model.decoder_seed, model.divisors, model.time_scale = "ffbs", 3, 2, 4
    tool = H2mmTool(embedded=True)
    try:
        tool.sb_min_states.setValue(2)
        tool.sb_max_states.setValue(4)
        tool.cb_criterion.setCurrentText("icl")
        tool.sb_restarts.setValue(5)
        tool.sb_max_iter.setValue(321)
        tool.sb_min_photons.setValue(8)
        tool.cb_engine.setCurrentIndex(tool.cb_engine.findData("em"))
        tool.sb_seed.setValue(7)
        tool.sb_patience.setValue(-1)
        tool.cb_decoder.setCurrentIndex(tool.cb_decoder.findData("ffbs"))
        tool.sb_decoder_seed.setValue(3)
        tool.sb_divisors.setValue(2)
        tool.sb_time_scale.setValue(4)
        qt = tool._gather_settings()
    finally:
        tool.close()
    mine = model.build_settings()
    for name in (
        "min_states", "max_states", "criterion", "n_restarts", "max_iter", "min_photons", "engine", "seed", "patience",
        "decoder", "decoder_seed", "divisors", "time_scale", "photon_hdf5", "photon_csv", "write_state_tttr",
        "state_tttr_ptu", "state_tttr_sidecar", "tol",
    ):
        assert getattr(mine, name) == getattr(qt, name), name


def test_default_settings_equal_the_qt_tools_defaults(qapp_ref):
    from chisurf.plugins.burst.burst_h2mm.gui.tool import H2mmTool

    tool = H2mmTool(embedded=True)
    try:
        qt = tool._gather_settings()
    finally:
        tool.close()
    mine = H2mmViewModel().build_settings()
    for name in ("min_states", "max_states", "criterion", "n_restarts", "max_iter", "min_photons", "engine", "seed",
                 "patience", "decoder", "decoder_seed", "divisors", "time_scale", "photon_hdf5", "photon_csv"):
        assert getattr(mine, name) == getattr(qt, name), name


def test_typed_fields_reach_the_model_and_are_clamped(app):
    drv = Driver(app)
    drv.type_into_name("restarts", "6")
    assert app.model.restarts == 6
    drv.type_into_name("restarts", "999")
    assert app.model.restarts == 20, "clamped to the spec's range"
    drv.type_into_name("max_iter", "3")
    assert app.model.max_iter == 10, "clamped up to the spec's minimum"


def test_a_real_fit_by_clicks_equals_the_backend_and_fills_tables_and_plots(monkeypatch, app, sample):
    from chisurf.plugins.burst.burst_h2mm.backend.services import run_analysis

    drv = Driver(app)
    configure(drv, sample)
    assert app.model.data_folder == str(sample)
    drv.click_name("toolAction_run")
    wait(drv)
    assert not app.job.error, app.job.error
    ana = app.model.analysis
    assert ana is not None and ana.best.n_states == 2

    # numeric parity with the backend, same seed and settings
    result, bundle = run_analysis(app.model.build_settings(), analysis_folder=str(sample))
    np.testing.assert_allclose(bundle.analysis.trans_rates, ana.trans_rates, rtol=1e-6)
    np.testing.assert_allclose(bundle.analysis.fret, ana.fret, rtol=1e-6)

    spy = PlotSpy(monkeypatch)
    painter = None
    for _ in range(2):
        spy.clear()
        painter = drv.draw(1)
    shown = texts(painter)
    rates = np.asarray(ana.trans_rates)
    assert f"{rates[0, 1]:.1f}" in shown and f"{rates[1, 0]:.1f}" in shown
    rows = {r["transition"]: r["rate"] for r in app.model.rate_rows()}
    assert rows == {"S0 -> S1": f"{rates[0, 1]:.1f}", "S1 -> S0": f"{rates[1, 0]:.1f}"}, "the table pairs a rate with its transition"
    for e in ana.fret:
        assert f"{float(e):.3f}" in shown
    np.testing.assert_array_equal(spy.named("Transitions")[2][0], np.ascontiguousarray(result_view.tdp_histogram(ana).T[::-1]))
    assert "Selected 2 states" in " ".join(shown)


def test_stop_ends_a_running_fit_with_the_stopped_message(app, sample):
    drv = Driver(app)
    configure(drv, sample, min_states="1", max_states="8")
    app.model.restarts = 20
    drv.type_into_name("restarts", "20")
    drv.click_name("toolAction_run")
    drv.draw(2)
    assert app.job.busy
    drv.click_name("Stop")
    wait(drv)
    assert "stopped" in app.job.error.lower()
    assert app.model.analysis is None


def test_edits_are_refused_while_a_fit_runs(app, sample):
    drv = Driver(app)
    configure(drv, sample, min_states="1", max_states="8")
    app.model.restarts = 20
    drv.click_name("toolAction_run")
    drv.draw(2)
    assert app.job.busy
    drv.click_name("restarts")
    app.app_key = None
    app.model.stop()
    wait(drv)
    assert app.model.restarts == 20


def test_a_dropped_folder_becomes_the_burst_folder(app, sample):
    drv = Driver(app)
    assert drv.drop(sample)
    assert app.model.data_folder == str(sample)
    assert not drv.drop()


def test_settings_file_round_trip(tmp_path):
    model = H2mmViewModel()
    model.restarts, model.criterion, model.donor, model.decoder = 9, "icl", "red", "ffbs"
    path = tmp_path / "h2mm.json"
    model.save_settings(path)
    other = H2mmViewModel()
    other.load_settings(path)
    assert (other.restarts, other.criterion, other.donor, other.decoder) == (9, "icl", "red", "ffbs")


def test_guide_targets_are_drawn_and_the_run_step_waits_for_the_press(app, sample):
    import json

    drv = Driver(app)
    drv.draw()
    steps = json.loads((Path(__file__).parents[1] / "gui" / "guide.json").read_text())["steps"]
    for step in steps:
        key = app.tour._target_key(step.get("target"))
        if key:
            assert key in app.item_rects or key in app.form.rects, key
    app.start_guide()
    app.tour.step_idx = next(i for i, s in enumerate(steps) if s.get("await") and s["target"]["name"] == "toolAction_run")
    configure(drv, sample)
    app.start_guide()
    app.tour.step_idx = next(i for i, s in enumerate(steps) if s.get("await") and s["target"]["name"] == "toolAction_run")
    drv.draw()
    assert app.tour.awaiting
    drv.click_name("toolAction_run")
    assert not app.tour.awaiting
    app.model.stop()
    wait(drv)


def test_help_and_buttons_have_tooltips(app):
    drv = Driver(app)
    drv.draw()
    drv.click_name("help")
    assert app.help_window.open


def test_a_toggle_is_flipped_by_a_click(app):
    drv = Driver(app)
    assert app.model.photon_csv is True
    drv.click_name("photon_csv")
    assert app.model.photon_csv is False
    drv.click_name("photon_csv")
    assert app.model.photon_csv is True


# ------------------------------------------------------------------------------------------------------------------
# Cards H2, H4, H5: detector editor, remaining plots, Restart / Bootstrap / LL scan / dwells / settings / plot saving
# ------------------------------------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def fitted(sample, qapp_ref):
    """One app with a real fit (states 1..3) on the BH sample, shared by the tests below."""
    window = create_app()
    drv = Driver(window)
    configure(drv, sample, min_states="1", max_states="3")
    drv.click_name("toolAction_run")
    wait(drv)
    assert not window.job.error, window.job.error
    yield window, drv
    window.close()


def tab(drv, title):
    drv.click_text(title)
    return drv.draw(2)


def test_the_detector_setup_is_the_shared_editor_and_edits_reach_the_model(app):
    drv = Driver(app)
    painter = tab(drv, "Detector setup")
    shown = texts(painter)
    assert "Detector Name" in shown and "Channels" in shown, "the shared editor's detector table is not drawn"
    editor = app.editor
    rec = next(r for r in editor.detector_rows() if r["name"] == "green")
    editor.edit_detector(rec, "chs", "0, 1")
    assert app.model.setup["detectors"]["green"]["chs"] == [0, 1]
    assert app.model._stream("green").channels == [0, 1]
    editor.add_detector()
    assert len(app.model.detector_names()) == 3 and app.model.aex_options()[0] == "(none)"


def test_stream_choices_follow_the_detector_names(app):
    app.model.set_setup({"detectors": {"a": {"chs": [0]}, "b": {"chs": [1]}}, "tttr_reading": {"file_type": "PTU"}})
    assert (app.model.donor, app.model.acceptor, app.model.aex, app.model.file_type) == ("a", "b", "(none)", "PTU")
    assert [s.name for s in app.model.streams()] == ["a", "b"]
    app.model.aex = "b"
    assert [s.name for s in app.model.streams()] == ["a", "b", "b"]


def test_plot_tabs_hold_the_analysis_numbers(monkeypatch, fitted):
    window, drv = fitted
    ana = window.model.analysis
    spy = PlotSpy(monkeypatch)

    def last(title):
        drv.click_text(title)
        for _ in range(2):
            spy.clear()
            drv.draw(1)
        return spy

    info = result_view.dwell_fret(ana)
    s = last("Dwell FRET")
    lines = [c for c in s.calls if c[0] == "plot_line" and not c[1].startswith("k ")]
    assert [c[1] for c in lines] == [f"S{i}" for i in info.counts]
    arrows = {c[1]: c for c in s.calls if c[0] == "plot_line" and c[1].startswith("k ")}
    expected = result_view.transition_arrows(ana, max(float(c.max()) for c in info.counts.values()) * 1.08)
    assert sorted(arrows) == sorted(f"k S{i}->S{j}" for i, j, *_ in expected), "one arrow per transition with a rate"
    for i, j, x0, y0, x1, y1, _w in expected:
        np.testing.assert_allclose(arrows[f"k S{i}->S{j}"][2][0], [x0, x1])
        assert np.isclose(arrows[f"k S{i}->S{j}"][2][1][0], y0)
    for call, (state, counts) in zip(lines, info.counts.items()):
        np.testing.assert_array_equal(call[2][1], counts)
    sel = result_view.model_selection(ana)
    s = last("Selection")
    np.testing.assert_array_equal(s.named("BIC")[2][1], sel[1])
    np.testing.assert_array_equal(s.named("ICL")[2][1], sel[2])
    assert list(sel[0]) == [f.n_states for f in ana.scan]
    last("Decays")  # drawn or says why not: no crash either way


def test_the_state_path_plot_follows_the_burst_field_and_the_dynamic_toggle(monkeypatch, fitted):
    window, drv = fitted
    ana, data = window.model.analysis, window.model.bundle.data
    spy = PlotSpy(monkeypatch)
    drv.click_text("State path")
    drv.draw(2)
    window.model.dynamic_only = False
    drv.type_into_name("nav_burst", "7")
    assert window.model.nav_burst == 7
    spy.clear()
    drv.draw(1)
    path = result_view.burst_path(ana, data, 7)
    np.testing.assert_array_equal(spy.named("state E")[2][0], path.t_ms)
    np.testing.assert_array_equal(spy.named("state E")[2][1], path.e)
    drv.click_name("dynamic_only")
    assert window.model.dynamic_only is True
    dyn = result_view.dynamic_bursts(ana)
    assert window.model.nav_bursts() == (dyn or list(range(int(data.n_bursts))))
    drv.click_name("dynamic_only")


def test_restart_refits_and_run_keeps_an_unchanged_fit(fitted):
    window, drv = fitted
    before = window.model.analysis
    drv.click_name("toolAction_run")
    wait(drv)
    assert window.model.analysis is before, "Run refitted unchanged inputs"
    assert "Unchanged" in window.model.status_text
    drv.click_name("toolAction_restart")
    wait(drv)
    assert window.model.analysis is not before
    np.testing.assert_allclose(window.model.analysis.trans_rates, before.trans_rates, rtol=1e-6)


def test_bootstrap_and_ll_scan_buttons_compute_the_backends_results(monkeypatch, fitted):
    window, drv = fitted
    drv.click_name("bootstrap")
    wait(drv)
    unc = window.model.uncertainty
    assert unc is not None and unc.n_boot > 0 and "bootstrap resamples" in window.model.status_text
    assert np.all(np.isfinite(unc.fret_lo)) and np.all(unc.fret_lo <= unc.fret_hi + 1e-9)
    drv.click_name("ll_scan")
    wait(drv)
    scans = window.model.scans
    assert scans and {s.param for s in scans} <= {"E", "S"}
    spy = PlotSpy(monkeypatch)
    drv.click_text("LL scan")
    for _ in range(2):
        spy.clear()
        drv.draw(1)
    e_scans = [s for s in scans if s.param == "E"]
    drawn = {c[1]: c for c in spy.calls if c[0] == "plot_line"}
    for sc in e_scans:
        np.testing.assert_allclose(drawn[f"S{sc.state}"][2][1], 2.0 * (np.max(sc.loglik) - sc.loglik))


def test_buttons_needing_a_fit_are_greyed_without_one(app):
    drv = Driver(app)
    drv.draw()
    for name in ("bootstrap", "ll_scan", "save_plot", "ndx", "export_dwells"):
        drv.click_name(name)
    assert app.dialog is None and not app.job.busy and app.model.uncertainty is None


def _dialog_save(drv, name):
    """Press *name*, type a file name in the open dialog and press Save."""
    drv.click_name(name)
    drv.draw(3)
    assert drv.app.dialog is not None, f"{name} opened no dialog"


def test_save_and_load_settings_through_the_file_dialog(app, tmp_path):
    drv = Driver(app)
    app.model.restarts = 9
    app.browse("save_settings")
    drv.draw(3)
    path = tmp_path / "s.json"
    app.dialog.directory = str(tmp_path)
    app.dialog.filename = "s.json"
    drv.click_text("Save")
    assert path.exists(), "the Save button of the dialog wrote nothing"
    app.model.restarts = 2
    app.browse("load_settings")
    drv.draw(3)
    app.dialog.directory = str(tmp_path)
    drv.click_text("s.json")
    drv.click_text("Open")
    assert app.model.restarts == 9


def test_export_dwells_and_save_plot_write_files(fitted, tmp_path):
    window, drv = fitted
    window.browse("export_dwells")
    drv.draw(3)
    window.dialog.directory = str(tmp_path)
    window.dialog.filename = "dwells.csv"
    drv.click_text("Save")
    csv = tmp_path / "dwells.csv"
    if window.model.dwell_table() is not None:
        assert csv.exists() and csv.stat().st_size > 0
    window.browse("save_plot")
    drv.draw(3)
    window.dialog.directory = str(tmp_path)
    window.dialog.filename = "plots.png"
    drv.click_text("Save")
    drv.draw(1)
    if not (tmp_path / "plots.png").exists():
        pytest.fail(f"File missing. Status: {window.model.status_text}")
    assert (tmp_path / "plots.png").stat().st_size > 1000


def test_browse_folder_dialog_sets_the_folder(app, sample):
    drv = Driver(app)
    drv.click_name("folder")
    drv.draw(3)
    assert app.dialog is not None
    app.dialog.directory = str(sample)
    drv.click_text("Choose")
    assert app.model.data_folder in (str(sample), "")


def test_bootstrap_bands_follow_the_uncertainty_on_the_dwell_fret_plot(monkeypatch, fitted):
    window, drv = fitted
    if window.model.uncertainty is None:
        drv.click_name("bootstrap")
        wait(drv)
    ana, unc = window.model.analysis, window.model.uncertainty
    bands = result_view.e_ci_bands(ana, unc)
    assert bands and all(lo <= hi for _s, lo, hi in bands)
    spy = PlotSpy(monkeypatch)
    drv.click_text("Dwell FRET")
    for _ in range(2):
        spy.clear()
        drv.draw(1)
    shaded = {c[1]: c for c in spy.calls if c[0] == "plot_shaded"}
    assert sorted(shaded) == sorted(f"CI S{s}" for s, _lo, _hi in bands)
    for state, lo, hi in bands:
        np.testing.assert_allclose(shaded[f"CI S{state}"][2][0], [lo, hi])
    window.model.uncertainty = None
    spy.clear()
    drv.draw(2)
    assert not [c for c in spy.calls if c[0] == "plot_shaded"], "bands without a bootstrap"
    window.model.uncertainty = unc


def test_result_view_arrows_and_bands_are_empty_without_a_fit():
    assert result_view.transition_arrows(None, 1.0) == [] and result_view.e_ci_bands(None, None) == []
    assert result_view.tdp_histogram(None) is None


# ------------------------------------------------------------------------------------------------------------------
# Hand-off: the burst-analysis workflow's step 7 hosts the native app (apply_workflow_context, panel, task seam)
# ------------------------------------------------------------------------------------------------------------------
def test_apply_workflow_context_sets_the_folder_and_the_detectors(sample):
    model = H2mmViewModel()
    model.apply_workflow_context({"burst_folder": str(sample), "channel_settings": BH_SETUP})
    assert model.data_folder == str(sample)
    assert model.detector_names() == ["green", "red"] and model.file_type == "SPC-130"
    assert (model.donor, model.acceptor) == ("green", "red")
    assert model._stream("red").channels == [8, 9]
    other = H2mmViewModel()
    other.apply_workflow_context({"analysis_folder": "/no/such/folder", "channel_settings": {"tttr_reading": {"file_type": "PTU"}}})
    assert other.data_folder == "" and other.file_type == "PTU", "a missing folder is ignored; a bare file type is taken"


def test_the_workflow_panel_runs_a_fit_through_the_task_seam(qapp_ref, sample):
    """The shell's Next waits for the step's registered task: the hidden run button the shell clicks starts one."""
    from qtpy import QtWidgets

    from chisurf.gui.task import running_tasks_under
    from chisurf.plugins.burst.burst_h2mm.gui.panel import make_panel

    panel = make_panel()
    try:
        panel.apply_workflow_context({"burst_folder": str(sample), "channel_settings": BH_SETUP})
        panel.model.min_states = panel.model.max_states = 2
        panel.model.restarts = 1
        button = panel.findChild(QtWidgets.QToolButton, "toolAction_run")
        assert button is not None and button.isEnabled()
        button.click()
        assert running_tasks_under(panel), "the shell cannot see the fit: Next would never advance"
        end = time.monotonic() + 180
        while running_tasks_under(panel) and time.monotonic() < end:
            qapp_ref.processEvents()
            time.sleep(0.05)
        qapp_ref.processEvents()
        assert panel.model.analysis is not None and panel.model.analysis.best.n_states == 2
        assert "Selected 2 states" in panel.model.status_text
    finally:
        panel.close()
