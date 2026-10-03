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
from chisurf.plugins.burst.burst_h2mm.gui.model import H2mmViewModel, parse_channels
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


def configure(drv, sample, min_states="2", max_states="2"):
    drv.type_into_name("data_folder", str(sample))
    drv.type_into_name("donor_channels", "0, 1")
    drv.type_into_name("acceptor_channels", "8, 9")
    drv.type_into_name("min_states", min_states)
    drv.type_into_name("max_states", max_states)
    drv.type_into_name("restarts", "1")


def test_empty_state_draws_no_data_at_both_sizes(monkeypatch, app):
    spy = PlotSpy(monkeypatch)
    for size in ((1200, 800), SMALL):
        drv = Driver(app, size)
        painter = drv.draw()
    assert spy.calls == []
    shown = " ".join(texts(painter))
    assert "No H2MM fit yet" in shown and "No transition density yet" in shown and "No dwell times yet" in shown


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
    drv.type_into_name("donor_channels", "2, 3")
    assert parse_channels(app.model.donor_channels) == [2, 3]


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
    points = result_view.transition_points(ana)
    np.testing.assert_array_equal(spy.named("Transitions")[2][0], points[0])
    assert "Selected 2 states" in " ".join(shown)


def test_stop_ends_a_running_fit_with_the_stopped_message(app, sample):
    drv = Driver(app)
    configure(drv, sample, min_states="1", max_states="8")
    app.model.restarts = 20
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
    model.restarts, model.criterion, model.donor_channels, model.decoder = 9, "icl", "4, 5", "ffbs"
    path = tmp_path / "h2mm.json"
    model.save_settings(path)
    other = H2mmViewModel()
    other.load_settings(path)
    assert (other.restarts, other.criterion, other.donor_channels, other.decoder) == (9, "icl", "4, 5", "ffbs")


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
