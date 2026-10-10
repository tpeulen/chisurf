"""Fit-model selection, the model's parameter editor, the timing calibration and the demo in the Qt-free burst-MLE tool.

These are the behaviours the retired Qt wizard's ``test/gui`` tests pinned (the registered fit models, a per-model
parameter editor that remembers its edits, a saved LUT / clock reaching the photons and the fit timing, the demo
starting from a clean slate), now stated against the view model, the engine session and the native app.
"""

from __future__ import annotations

import copy
import json
import shutil
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.burst.burst_mle_analysis import engine
from chisurf.plugins.burst.burst_mle_analysis.gui.model import MleViewModel
from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app
from chisurf.plugins.emtk_test_input import Driver

from .conftest import BURST_TABLE, CHANNEL_SETTINGS, REPO_DATA
from .test_emtk_mle_no_invented_data import texts

GUI = Path(__file__).parents[1] / "gui"


@pytest.fixture
def model(hermetic_env):
    """A view model once the compiled model registry has been read (it is read on a worker thread)."""
    from chisurf.core.registry import catalog

    deadline = time.monotonic() + 60
    while not catalog.prefetch() and time.monotonic() < deadline:
        time.sleep(0.05)
    return MleViewModel()


def test_the_choice_is_writable_validated_and_model_aware(model):
    """The parameter rows follow the selected registered model and remember another model's edits."""
    assert model.fit_model_options() == ["fit23", "fit24", "fit25", "tail"]
    model.fit_model = "fit25"
    assert model.fit_model == "fit25"
    names = [r["name"] for r in model.parameter_records()]
    assert names == ["tau1", "tau2", "tau3", "tau4", "gamma"]
    model.edit_parameter({"name": "tau1"}, "start", 0.75)
    model.fit_model = "fit24"
    model.fit_model = "fit25"
    assert model.parameter_records()[0]["start"] == 0.75
    with pytest.raises(ValueError):
        model.fit_model = "fit_nexp"
    assert model.fit_model == "fit25"


def test_the_model_choice_round_trips_through_the_settings_payload(model):
    model.fit_model = "fit25"
    model.edit_parameter({"name": "tau1"}, "start", 0.75)
    det = model.session.current_detector
    payload = json.loads(json.dumps(model.session.settings_payload(), cls=engine.NumpyEncoder))
    assert payload["detector_settings"][det]["model"] == "fit25"
    model.fit_model = "fit24"
    model.session.apply_settings_payload(payload)
    assert model.fit_model == "fit25"
    assert model.parameter_records()[0]["start"] == 0.75
    # a detector whose stored settings name no model is the default one
    model.session.apply_settings_payload({"detector_settings": {det: {"tau": 3.0}}})
    assert model.fit_model == "fit23"
    # and a stored model nobody registered is refused rather than half applied
    with pytest.raises(ValueError):
        model.session.apply_settings_payload({"detector_settings": {det: {"model": "fit_nexp"}}})


@pytest.mark.parametrize("name", ["fit23", "fit24", "fit25"])
def test_the_visible_parameter_cell_is_editable(hermetic_env, model, name):
    """A typed edit in the visible table reaches the selected model's starts; a bad value is refused."""
    app = create_app()
    try:
        app.model.fit_model = name
        drv = Driver(app, (1280, 900))
        painter = drv.draw(3)
        param = "tau" if name == "fit23" else "tau1"
        header = drv.text_rect(painter, "Start")
        row = drv.text_rect(painter, param)
        point = (header[0] + header[2] / 2, row[1] + row[3] / 2)
        control = app.form.tables["parameter_records"].control
        assert control.column_at(point[0]).key == "start"
        drv.click((point[0] - 4, point[1] - 4, 8, 8), clicks=2)
        assert control.editing is not None, "a double click on the Start cell did not open it"
        for _ in range(10):  # empty the open cell with the keyboard
            from emtk import keys

            app.key(keys.KEY_END, "")
            app.key(keys.KEY_BACKSPACE, "")
            drv.draw(1)
        drv.type("0.875")
        drv.enter()
        assert app.model.parameter_records()[0]["start"] == 0.875
        before = app.model.parameter_records()[0]["start"]
        if name != "fit23":  # the registry declares bounds; fit23's start values are free
            with pytest.raises(ValueError):
                app.model.edit_parameter({"name": param}, "start", -1.0)
            assert app.model.parameter_records()[0]["start"] == before
    finally:
        app.close()


def test_the_guide_awaits_a_real_fit_model_choice(hermetic_env):
    """The shipped panel delivers a real change to the guide's await seam."""
    app = create_app()
    try:
        app.tour.steps = [
            {
                "title": "Fit model",
                "text": "Choose a different model.",
                "target": {"name": "fit_model"},
                "await": {"hint": "Choose Fit24."},
            }
        ]
        drv = Driver(app, (1280, 900))
        drv.draw(3)
        assert app.tour.get_target_rect("fit_model") is not None
        app.tour.start()
        assert app.tour.awaiting
        drv.click_name("fit_model")
        drv.click_text(dict(app.model.fit_model_choices())["fit24"])
        assert app.model.fit_model == "fit24"
        assert not app.tour.awaiting
    finally:
        app.tour.stop()
        app.close()


def test_the_shipped_demo_and_model_guide_actions(hermetic_env):
    """Real declared controls load photons and satisfy the shipped manual guide's awaits."""
    app = create_app()
    try:
        drv = Driver(app, (1280, 900))
        drv.draw(3)
        tour = app.tour
        demo_step = next(s for s in tour.steps if s.get("target", {}).get("name") == "load_example")
        assert "await" in demo_step
        assert tour.get_target_rect("load_example") is not None
        tour.start(tour.steps.index(demo_step))
        assert tour.awaiting
        drv.click_name("load_example")
        drv.draw(3)
        assert not tour.awaiting
        tour.stop()
        assert app.model.n_bursts == 16
        assert app.model.current_detector == "synthetic"
        assert app.model.fit_curves is None
        assert app.model.gamma == 0.0 and app.model.r0 == 0.0
        model_step = next(s for s in tour.steps if s.get("target", {}).get("name") == "fit_model")
        assert "await" in model_step
        tour.start(tour.steps.index(model_step))
        assert tour.awaiting
        drv.click_name("fit_model")
        drv.click_text(dict(app.model.fit_model_choices())["fit25"])
        assert app.model.fit_model == "fit25"
        assert not tour.awaiting
    finally:
        app.tour.stop()
        app.close()


def test_the_demo_clears_previous_curves_and_parameter_state(model):
    """Replacing inputs must not display an earlier file's fit as a synthetic result."""
    model.burst_results = [{"old": 1.0}]
    model.fit_model = "fit25"
    model.load_example()
    assert model.fit_curves is None
    assert model.burst_results == []
    assert model.tau == 4.0
    assert not model.fix_tau
    assert model.fix_gamma and model.fix_r0 and model.fix_rho


def test_the_reader_honours_an_explicit_correction_and_clock(hermetic_env, tmp_path):
    """Saved calibration reaches real photons and the effective fit timing, without changing their header."""
    from chisurf.core.data_io.detector_setups import setup_lut_open_kwargs
    from chisurf.core.fio.staging import open_tttr

    sample = tmp_path / "data"
    shutil.copytree(REPO_DATA, sample, ignore=shutil.ignore_patterns(".DS_Store"))
    session = engine.MleSession()
    session.set_detectors(CHANNEL_SETTINGS["detectors"], CHANNEL_SETTINGS["file_type"])
    session.add_burst_files([sample / BURST_TABLE])
    raw = session.current_tttr()
    definition = copy.deepcopy(session.definition_payload())
    definition.update(
        channel_luts={"0": 4095.0 * (np.arange(4096) / 4095.0) ** 1.2},
        channel_shifts={"0": 2},
        apply_lut=True,
    )
    definition.setdefault("tttr_reading", {}).update(
        override_timing=True, micro_time_resolution=25.0, macro_time_resolution=102.4
    )
    session.set_definition(definition)
    actual = session.current_tttr()
    path = next(p for p in session.tttr_paths.values() if p.stem == "m000")
    expected = open_tttr(path, "SPC-130", cache=False, **setup_lut_open_kwargs(definition))
    assert not np.array_equal(raw.micro_times, expected.micro_times)
    np.testing.assert_array_equal(actual.micro_times, expected.micro_times)
    binning = 4
    dt, period = session.timing_ns(actual, binning)
    assert dt == 0.025 * binning and period == 102.4
    assert actual.header.micro_time_resolution == expected.header.micro_time_resolution


def test_without_header_timing_the_declared_ps_calibration_is_used_in_nanoseconds():
    """Without photon headers the declared ps channel width must still enter the ns fit API."""
    reading = {"micro_time_resolution": 3.2958984375, "macro_time_resolution": 13.5}
    for binning in (1, 4):
        dt, period = engine.effective_timing_ns(None, binning, reading)
        assert dt == pytest.approx(3.2958984375e-3 * binning) and period == 13.5
    # with a header and no override, the file's physical timing stands
    assert engine.effective_timing_ns(None, 1, {}) == (None, None)


SOURCE = Path(__file__).resolve().parents[5] / "test/data/tttr/BH/132/BH_SPC132.spc"


@pytest.mark.skipif(not SOURCE.exists(), reason="BH SPC-132 test measurement missing")
def test_auto_binning_uses_the_declared_choices_and_photon_counts():
    """The same statistical floor chooses a legal bin without inspecting any control."""
    import tttrlib

    stream = tttrlib.TTTR(str(SOURCE), "SPC-130")
    everything = np.arange(len(stream))
    choices = [1, 2, 4, 8, 16, 32, 64, 128]  # the Qt page offered these; the engine also offers 256
    assert set(choices) <= set(engine.BINNING_CHOICES)
    pick = lambda target: engine.select_binning(  # noqa: E731
        stream, [8, 0, 3], everything, choices, target_counts_per_bin=target, irf_oversample=0
    )
    assert pick(200) == 16
    assert pick(100000) == 128


def test_the_native_app_freezes_its_inputs_while_a_job_runs(hermetic_env):
    """While a batch runs, the tool must not change underneath it.

    Both long runs read their configuration once -- the batch ships it to worker processes, Opt writes it per
    trial -- so an edit landing in between would apply to part of the work and not the rest. The detector editor is
    read-only for the duration and released afterwards (a failed job must not leave it locked either).
    """
    app = create_app()
    try:
        drv = Driver(app)
        drv.draw(2)
        assert app.editor.read_only is False
        app.job.busy = True
        drv.draw(2)
        assert app.editor.read_only is True
        assert "Detector settings are locked while Burst MLE is running." in texts(
            (app.docks.focus("detectors"), drv.draw(2))[1]
        )
        app.job.busy = False
        drv.draw(2)
        assert app.editor.read_only is False
    finally:
        app.close()


def test_a_batch_with_no_data_does_not_start_a_job(hermetic_env):
    """The early return must not leave the app busy: a run that never started locks nothing."""
    app = create_app()
    try:
        app.fit_bursts()
        assert not app.job.busy and "Add burst files first" in app.model.status_text
    finally:
        app.close()


def test_settings_restore_from_a_burst_analysis_folder(model, tmp_path):
    """The tool restores from an analysis folder, not only from a settings file.

    A folder that recorded exactly what the tool needs can hand it over: passing the folder is equivalent to picking
    the file. (The manifest's ``mle_settings``, else the ``settings`` the analysis ran with.)
    """
    from chisurf.core.fio.fluorescence.burst_manifest import write_analysis_manifest

    write_analysis_manifest(
        tmp_path,
        [{"path": "m000.spc", "container_type": "SPC-130"}],
        settings={"micro_time_binning": 4},
    )
    model.load_settings(tmp_path)
    assert model.binning == 4 and str(tmp_path) in model.status_text


def test_settings_restore_reports_rather_than_raises_on_junk(model, tmp_path):
    """A corrupt source or a folder without settings must not take the tool down."""
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    model.load_settings(broken)
    assert "Could not read settings" in model.status_text
    model.load_settings(tmp_path / "no_manifest_here")
    assert "No stored settings found" in model.status_text
    assert model.binning == 1, "nothing should have been applied"


def test_a_settings_file_of_another_tool_is_refused(model, tmp_path):
    path = tmp_path / "other.json"
    path.write_text(json.dumps({"micro_time_binning": 8}), encoding="utf-8")
    with pytest.raises(ValueError, match="Not a burst-MLE settings file"):
        model.load_settings(path)
    assert model.binning == 1
