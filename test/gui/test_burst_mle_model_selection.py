"""The actual embedded Burst MLE panel selects canonical registered fit models."""

import pytest


def test_real_wizard_choice_is_writable_validated_and_model_aware(qapp):
    """Existing real Qt parameter rows use facade inputs rather than supplied slots."""
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    wizard = MLELifetimeAnalysisWizard()
    try:
        assert wizard.fit_model_options() == ["fit23", "fit24", "fit25", "tail"]
        wizard.fit_model = "fit25"
        assert wizard.fit_model == "fit25"
        assert wizard._fit_param_names("fit25") == ["tau1", "tau2", "tau3", "tau4", "gamma"]
        assert len(wizard.fit_parameters[0]) == 5
        wizard._dyn_params.values[0] = 0.75
        wizard.fit_model = "fit24"
        wizard.fit_model = "fit25"
        assert wizard.fit_parameters[0][0] == 0.75
        payload = {
            "model": "fit25",
            "model_parameter_states": wizard._model_parameter_payload(),
            "detector_settings": wizard.channel_definer.get_settings(),
            "channel_settings": wizard.channel_settings,
        }
        wizard.fit_model = "fit24"
        wizard.apply_settings_payload(payload)
        assert wizard.fit_model == "fit25"
        assert wizard.fit_parameters[0][0] == 0.75
        wizard.apply_settings_payload({"detector_settings": wizard.channel_definer.get_settings()})
        assert wizard.fit_model == "fit23"
        wizard.fit_model = "fit25"
        with pytest.raises(ValueError):
            wizard.fit_model = "fit_nexp"
        assert wizard.fit_model == "fit25"
    finally:
        wizard.channel_definer.close()
        wizard.close()


def test_actual_embedded_choice_has_reachable_guide_target(qapp):
    """The shipped Qt-hosted emtk panel delivers a real change to the guide await seam."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_mle_analysis.gui.app import BurstMleApp
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    wizard = MLELifetimeAnalysisWizard()
    app = BurstMleApp(wizard)
    tour = app.mle_gui.tour
    tour.steps = [
        {
            "title": "Fit model",
            "text": "Choose a different model.",
            "target": {"name": "fit_model"},
            "await": {"hint": "Choose Fit24."},
        }
    ]
    driver = Driver(app, (1280, 900))
    try:
        driver.frame(3)
        assert "Fit parameters.fold" in driver.ids()
        driver.click("Fit parameters.fold")
        assert "parameter_records" not in driver.ids()
        driver.click("Fit parameters.fold")
        assert "parameter_records" in driver.ids()
        assert tour.get_target_rect("fit_model") is not None
        tour.start()
        assert tour.awaiting
        driver.click("fit_model")
        driver.click(dict(wizard.fit_model_choices())["fit24"])
        assert wizard.fit_model == "fit24"
        assert not tour.awaiting
    finally:
        tour.stop()
        wizard.channel_definer.close()
        wizard.close()


@pytest.mark.parametrize("name", ["fit23", "fit24", "fit25"])
def test_actual_embedded_parameter_cell_is_editable(qapp, name):
    """A typed edit in the visible pane must reach the selected model's actual starts."""
    from emtk.events import CONTROL_MODIFIER, LEFT_BUTTON
    from emtk.keys import KEY_ENTER
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_mle_analysis.gui.app import BurstMleApp
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    wizard = MLELifetimeAnalysisWizard()
    wizard.fit_model = name
    app = BurstMleApp(wizard)
    driver = Driver(app, (1280, 900))
    try:
        driver.frame(3)
        param = "tau" if name == "fit23" else "tau1"
        header = driver.rect("Start")
        row = next(text[:4] for text in driver.painter.texts if text[5] == param)
        point = (header[0] + header[2] / 2, row[1] + row[3] / 2)
        control = app.form.tables["parameter_records"].control
        assert control.column_at(point[0]).key == "start"
        driver.click(point)
        driver.surface.on_pointer_press(*point, LEFT_BUTTON, 0, double=True)
        driver.frame()
        driver.surface.on_pointer_release(*point, LEFT_BUTTON, 0)
        driver.frame()
        assert control.editing == (0, "start"), (point, control._body_box, control.selected_key)
        driver.press(ord("A"), CONTROL_MODIFIER)
        driver.type("0.875")
        driver.press(KEY_ENTER)
        assert wizard.fit_parameters[0][0] == 0.875
        fixed_header = driver.rect("Fixed")
        fixed_point = (fixed_header[0] + fixed_header[2] / 2, row[1] + row[3] / 2)
        driver.click(fixed_point)
        assert bool(wizard.fit_parameters[1][0]) is True
        if name == "fit25":
            driver.click(fixed_point)
            assert bool(wizard.fit_parameters[1][0]) is True
        before = wizard.fit_parameters[0].copy()
        with pytest.raises(ValueError):
            wizard.edit_parameter({"name": param}, "start", -1.0)
        assert list(wizard.fit_parameters[0]) == list(before)
    finally:
        wizard.channel_definer.close()
        wizard.close()


def test_embedded_reader_honors_explicit_correction_and_clock(qapp, tmp_path):
    """Saved calibration reaches real photons and effective fit timing, without changing their header."""
    import copy
    import shutil

    import numpy as np

    from chisurf.core.data_io.detector_setups import setup_lut_open_kwargs
    from chisurf.core.fio.staging import open_tttr
    from chisurf.plugins.burst.burst_mle_analysis.tests.conftest import REPO_DATA, build_wizard

    sample = tmp_path / "data"
    shutil.copytree(REPO_DATA, sample)
    wizard = build_wizard(sample)
    try:
        raw = wizard._current_tttr()
        definition = copy.deepcopy(wizard.channel_definer.get_settings())
        definition.update(
            channel_luts={"0": 4095.0 * (np.arange(4096) / 4095.0) ** 1.2},
            channel_shifts={"0": 2},
            apply_lut=True,
        )
        definition["tttr_reading"].update(
            override_timing=True, micro_time_resolution=25.0, macro_time_resolution=102.4
        )
        wizard.channel_definer.set_settings(definition)
        actual = wizard._current_tttr()
        path = next(path for path in wizard._tttr_paths.values() if path.stem == "m000")
        expected = open_tttr(path, "SPC-130", cache=False, **setup_lut_open_kwargs(definition))
        assert not np.array_equal(raw.micro_times, expected.micro_times)
        np.testing.assert_array_equal(actual.micro_times, expected.micro_times)
        assert wizard.dt_effective == 0.025 * wizard.micro_time_binning
        assert wizard.excitation_period == 102.4
        assert actual.header.micro_time_resolution == expected.header.micro_time_resolution
    finally:
        wizard.channel_definer.close()
        wizard.close()


def test_shipped_embedded_demo_and_model_guide_actions(qapp, tmp_path, monkeypatch):
    """Real declared controls load photons and satisfy the shipped manual guide awaits."""
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_mle_analysis.gui.app import BurstMleApp
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    wizard = MLELifetimeAnalysisWizard()
    app = BurstMleApp(wizard)
    driver = Driver(app, (1280, 900))
    tour = app.mle_gui.tour
    try:
        driver.frame(3)
        demo_step = next(
            step for step in tour.steps if step.get("target", {}).get("name") == "load_demo"
        )
        assert "await" in demo_step
        assert tour.get_target_rect("load_demo") is not None
        tour.start(tour.steps.index(demo_step))
        assert tour.awaiting
        driver.click("load_demo")
        driver.frame(3)
        assert not tour.awaiting
        tour.stop()
        assert wizard.n_bursts == 16
        assert wizard.current_detector == "synthetic"
        assert wizard._fit is None
        assert wizard.gamma == 0.0
        assert wizard.r0 == 0.0
        model_step = next(
            step for step in tour.steps if step.get("target", {}).get("name") == "fit_model"
        )
        assert "await" in model_step
        tour.start(tour.steps.index(model_step))
        assert tour.awaiting
        driver.click("fit_model")
        driver.click(dict(wizard.fit_model_choices())["fit25"])
        assert wizard.fit_model == "fit25"
        assert not tour.awaiting
    finally:
        tour.stop()
        wizard.channel_definer.close()
        wizard.close()


def test_demo_clears_previous_measured_curves_and_parameter_state(qapp, tmp_path, monkeypatch):
    """Replacing inputs must not display an earlier file's fit as a synthetic result."""
    from chisurf.plugins.burst.burst_mle_analysis.wizard import MLELifetimeAnalysisWizard

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    wizard = MLELifetimeAnalysisWizard()
    try:
        wizard.fit_curves = object()
        wizard.burst_results = [{"old": 1.0}]
        wizard.fit_model = "fit25"
        wizard.load_demo()
        assert wizard.fit_curves is None
        assert wizard.burst_results == []
        assert wizard.tau == 4.0
        assert not wizard.fix_tau
        assert wizard.fix_gamma and wizard.fix_r0 and wizard.fix_rho
    finally:
        wizard.channel_definer.close()
        wizard.close()
