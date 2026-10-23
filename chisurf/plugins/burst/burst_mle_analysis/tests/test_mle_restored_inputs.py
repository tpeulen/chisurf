"""Measured IRF/background files, tail fit, IRF model, hyperparameter Opt and save-to-setup (engine and click tests).

Every number is checked against an input known by construction: ``demo.make_demo`` draws burst photons with a 2 ns
lifetime behind a Gaussian prompt (mean 20, sigma 2 channels); the measured IRF file is another draw of exactly that
prompt, the measured background a uniform draw. The click tests press the real controls of the native app through
``emtk``'s pointer events.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.burst.burst_mle_analysis import demo, engine, hpo
from chisurf.plugins.burst.burst_mle_analysis.gui.native import create_app
from chisurf.plugins.emtk_test_input import SMALL, Driver

from .test_emtk_mle_native import wait
from .test_emtk_mle_no_invented_data import texts

TRUE_TAU = demo.SIGNAL_LIFETIME_NS


def write_ptu(path: Path, micro: np.ndarray, seed_ticks: int = 100) -> Path:
    """A PTU of *micro* times on alternating routing channels with the demo's clock."""
    import tttrlib

    micro = np.asarray(micro, dtype=np.uint16)
    routing = (np.arange(len(micro)) % 2).astype(np.int8)
    macro = np.arange(len(micro), dtype=np.uint64) * np.uint64(seed_ticks)
    stream = tttrlib.TTTR(macro, micro, routing, np.zeros(len(micro), dtype=np.int8))
    stream.header.set_macro_time_resolution(demo.MACRO_RESOLUTION_S)
    stream.header.set_micro_time_resolution(demo.MICRO_RESOLUTION_S)
    stream.header.set_number_of_micro_time_channels(demo.CHANNELS)
    assert stream.write(str(path), "PTU")
    return path


@pytest.fixture(scope="module")
def inputs(tmp_path_factory, hermetic_env):
    """The demo burst table plus a measured IRF file and a measured background file beside its raw data."""
    folder = tmp_path_factory.mktemp("mle_inputs")
    bur = Path(demo.make_demo(folder / "demo"))
    # pto-first: pack the demo's photons and its burst table as one container --
    # the .bur stays on disk for parity checks, the app gets the container.
    from chisurf.core.fio.fluorescence.burst import read_bur_file
    from chisurf.plugins.burst.burst_selection.api.io import write_container

    bur = Path(write_container(
        bur.parents[2] / "synthetic_mle.ptu", read_bur_file(bur), run="demo"
    ))
    rng = np.random.default_rng(7)
    irf = np.clip(np.rint(rng.normal(20.0, 2.0, 40000)), 0, demo.CHANNELS - 1)
    bg = rng.integers(0, demo.CHANNELS, 20000)
    raw = bur.parent  # beside the container: the dialog folder stays small
    return {
        "bur": bur,
        "irf": write_ptu(raw / "measured_irf.ptu", irf),
        "bg": write_ptu(raw / "measured_bg.ptu", bg),
    }


def fresh_session(bur: Path) -> engine.MleSession:
    session = engine.MleSession(template=engine.MleSettings(gamma=0.0, r0=0.0))
    session.set_definition(demo.SETUP)
    session.add_burst_files([bur])
    session.build_decay()
    return session


def set_window(session: engine.MleSession) -> None:
    session.build_decay()
    window = engine.select_fit_range(session.decay)
    assert window is not None, "no fit range found in the restored decay"
    session.settings.micro_time_start, session.settings.micro_time_stop = window
    session.build_decay()


# -- measured IRF and background ------------------------------------------------------------------------------- #
def test_measured_irf_and_background_recover_the_planted_lifetime(inputs):
    session = fresh_session(inputs["bur"])
    session.set_binning(1)
    session.set_pattern_files("irf", "synthetic", [inputs["irf"]])
    session.set_pattern_files("bg", "synthetic", [inputs["bg"]])
    irf = session.irf_np["synthetic"]
    half = irf.size // 2
    assert irf.size == 2 * demo.CHANNELS
    assert irf[:half].sum() == pytest.approx(1.0) and irf[half:].sum() == pytest.approx(1.0)
    assert int(np.argmax(irf[:half])) in range(18, 23), "the prompt is where it was planted"
    set_window(session)
    outcome = session.fit()
    assert outcome is not None, session.status
    assert outcome.x[0] == pytest.approx(TRUE_TAU, rel=0.05)
    assert 0.0 < outcome.two_istar < 1.5


def test_one_for_all_sets_every_detector_and_per_detector_sets_one(inputs):
    session = fresh_session(inputs["bur"])
    session.set_detectors(
        {
            "synthetic": {"chs": [0, 1], "micro_time_ranges": []},
            "second": {"chs": [0, 1], "micro_time_ranges": []},
        }
    )
    session.set_binning(1)
    assert sorted(session.set_pattern_files("irf", "synthetic", [inputs["irf"]])) == [
        "second",
        "synthetic",
    ]
    np.testing.assert_array_equal(session.irf_np["second"], session.irf_np["synthetic"])
    session.clear_pattern_files("irf", "synthetic")
    assert not session.irf_files and not session.irf_np
    session.irf_one_for_all = False
    assert session.set_pattern_files("irf", "second", [inputs["irf"]]) == ["second"]
    assert "synthetic" not in session.irf_np and session.irf_files["second"] == [inputs["irf"]]


def test_a_measured_file_is_kept_by_auto_irf_background_and_re_read_at_a_new_binning(inputs):
    session = fresh_session(inputs["bur"])
    session.set_binning(1)
    session.set_pattern_files("irf", "synthetic", [inputs["irf"]])
    measured = session.irf_np["synthetic"].copy()
    session.extract_irf_background()
    np.testing.assert_array_equal(session.irf_np["synthetic"], measured)
    assert session.bg_np["synthetic"].size, "the background is still estimated"
    session.set_binning(4)
    session.refresh_pattern_files()
    assert session.irf_np["synthetic"].size == 2 * demo.CHANNELS // 4


def test_save_vv_vhs_writes_the_histogram_of_each_file(inputs, tmp_path):
    import shutil

    from chisurf.core.fio import read_vv_vh

    copy = shutil.copy(inputs["irf"], tmp_path / "irf_copy.ptu")
    session = fresh_session(inputs["bur"])
    session.set_binning(1)
    session.save_vv_vhs = True
    session.set_pattern_files("irf", "synthetic", [Path(copy)])
    written = sorted(tmp_path.glob("irf_copy_*.dat"))
    assert len(written) == 1, [p.name for p in tmp_path.iterdir()]
    np.testing.assert_allclose(read_vv_vh(written[0]), session.irf_np["synthetic"], atol=1e-5)


# -- tail fit --------------------------------------------------------------------------------------------------- #
def test_the_tail_fit_is_offered_and_recovers_the_planted_lifetime(inputs):
    assert engine.TAIL_MODEL in engine.fit_model_specs()
    session = fresh_session(inputs["bur"])
    session.set_binning(1)
    session.set_pattern_files("bg", "synthetic", [inputs["bg"]])  # the tail fit needs no IRF at all
    set_window(session)
    session.set_model(engine.TAIL_MODEL)
    session.settings.edit_parameter("tail_start", 40, fixed=False)
    session.settings.edit_parameter("tau2", 2.0, fixed=False)
    session.settings.edit_parameter("tau2", True, fixed=True)
    session.settings.edit_parameter("tau1", 1.0, fixed=False)
    assert session.blocked_reason() is None
    outcome = session.fit()
    assert outcome is not None, session.status
    assert outcome.names == ["tail_start", "tau1", "tau2"]
    assert outcome.x[1] == pytest.approx(TRUE_TAU, rel=0.05)
    assert outcome.curves.irf is None, "the tail fit deconvolves no IRF"
    with pytest.raises(ValueError, match="tail fit previews"):
        session.run_batch()


# -- IRF model --------------------------------------------------------------------------------------------------- #
def test_the_irf_model_changes_the_estimated_irf(inputs):
    patterns = {}
    for model in ("gaussian", "skewed", "experimental"):
        session = fresh_session(inputs["bur"])
        session.template.irf_model = model
        session.settings.irf_model = model
        session.set_binning(1)
        session.extract_irf_background()
        patterns[model] = session.irf_np["synthetic"].copy()
    assert not np.array_equal(patterns["gaussian"], patterns["experimental"])
    assert not np.array_equal(patterns["gaussian"], patterns["skewed"])
    for irf in patterns.values():
        assert int(np.argmax(irf[: irf.size // 2])) in range(17, 24), (
            "every model finds the planted prompt"
        )


# -- hyperparameter optimisation -------------------------------------------------------------------------------- #
def displaced_session(inputs, bins: int = 3) -> tuple[engine.MleSession, float]:
    """Auto IRF with the VH half displaced by *bins*; returns the session and the tau of the undisplaced fit."""
    session = fresh_session(inputs["bur"])
    session.auto_extract()
    assert session.outcome is not None, "auto_extract produced no fit"
    reference = session.outcome.x[0]
    irf = session.irf_np["synthetic"].copy()
    half = irf.size // 2
    irf[half:] = np.roll(irf[half:], bins)
    session.irf_np["synthetic"] = irf
    session.fit()
    return session, reference


def test_opt_recovers_a_planted_shift(inputs):
    session, reference = displaced_session(inputs)
    before = session.outcome.two_istar
    assert before > 2.5, "the planted displacement must hurt the fit"
    result = hpo.optimize_hyperparameters(session, 60, seed=1)
    assert not result["stopped"] and result["start_loss"] == pytest.approx(before)
    assert result["loss"] < 1.0 < before
    assert session.outcome.x[0] == pytest.approx(reference, rel=0.02)
    assert session.settings.shift_ss == pytest.approx(-3.0, abs=0.75), (
        "the VH IRF was displaced by +3 bins"
    )


def test_opt_that_is_stopped_restores_the_settings(inputs):
    session, _ = displaced_session(inputs)
    before = (session.settings.shift, session.settings.shift_ss, session.settings.irf_start)
    result = hpo.optimize_hyperparameters(session, 30, should_stop=lambda: True)
    assert result["stopped"]
    assert (session.settings.shift, session.settings.shift_ss, session.settings.irf_start) == before


class _SurrogateSession:
    """The part of a session the search touches, with a loss that is a known function of the settings."""

    def __init__(self):
        self.settings = engine.MleSettings()
        self.irf_np = {}
        self.current_detector = "d"
        self.det_settings = {}

    def blocked_reason(self):
        return None

    def build_decay(self):
        pass

    def fit(self):
        return None


def test_the_search_budget_the_caller_asks_for_is_the_budget_it_gets(monkeypatch):
    """``max(8, ...)`` on the exploration stage once silently inflated small budgets.

    Every extra evaluation is a full refit of the decay, and the bar sits at 100 % while they run.
    """
    for budget in (1, 5, 11):
        session = _SurrogateSession()
        calls = []

        def loss(sess, calls=calls):
            calls.append(1)
            return float(len(calls))

        monkeypatch.setattr(hpo, "_loss", loss)
        hpo.optimize_hyperparameters(session, budget, seed=0)
        assert len(calls) <= budget + 1, (
            f"n_iter={budget} evaluated {len(calls)}"
        )  # +1: the final refit


def test_an_improvement_is_recognised_as_one(monkeypatch):
    """A step that lowered the loss must keep its step size and be followed, not shrunk as if it had not.

    Every refinement decision once read "no improvement" (the helper had already lowered the best loss itself), so
    the step of a dimension that had just improved was shrunk anyway and the search exited on the three-quiet-rounds
    break instead of on its budget. With a loss that is a bowl in the shift, a long walk down it needs the step kept.
    """
    session = _SurrogateSession()
    session.settings.shift = 0
    monkeypatch.setattr(hpo, "_loss", lambda sess: 1.0 + abs(sess.settings.shift - 5) * 0.1)
    result = hpo.optimize_hyperparameters(session, 200, seed=0, bounds={"shift": (-5, 5, "int")})
    assert result["config"]["shift"] == 5 and result["loss"] == pytest.approx(1.0)


# -- the native app: real presses ------------------------------------------------------------------------------- #
@pytest.fixture
def app(hermetic_env):
    window = create_app()
    yield window
    window.close()


def open_demo(app, inputs) -> Driver:
    drv = Driver(app)
    app.model.session.set_definition(demo.SETUP)
    app.editor.load_definition(demo.SETUP)
    app.model.gamma = 0.0  # the demo has no scattered light and no anisotropy
    app.model.r0 = 0.0
    assert drv.drop(inputs["bur"])
    app.model.session.set_binning(1)
    return drv


def pick_file(app, drv, button: str, name: str, folder: Path) -> None:
    drv.click_text("IRF/BG files")
    drv.click_name(button)
    drv.draw(3)
    app.dialog.directory = str(folder)
    drv.click_text(name)
    drv.click_text("Open")
    drv.draw(2)


def test_pressing_add_irf_and_background_files_loads_them_and_fits(app, inputs):
    drv = open_demo(app, inputs)
    folder = inputs["irf"].parent
    pick_file(app, drv, "add_irf_files", inputs["irf"].name, folder)
    assert app.model.irf_file_rows()[0]["file"] == "measured_irf.ptu"
    assert "measured_irf.ptu" in texts(drv.draw(2))
    pick_file(app, drv, "add_bg_files", inputs["bg"].name, folder)
    assert app.model.bg_file_rows()[0]["file"] == "measured_bg.ptu"
    set_window(app.model.session)
    app.model.refit()
    assert app.model.tau_result == pytest.approx(TRUE_TAU, rel=0.05)
    drv.click_name("clear_irf_files")
    assert app.model.irf_file_rows() == [] and not app.model.session.irf_np
    drv.click_name("clear_bg_files")
    assert app.model.bg_file_rows() == []


def test_the_one_for_all_and_save_vv_vhs_toggles_are_pressed(app, inputs):
    drv = open_demo(app, inputs)
    drv.click_text("IRF/BG files")
    drv.draw(2)
    for attr in ("irf_one_for_all", "bg_one_for_all", "save_vv_vhs"):
        before = getattr(app.model, attr)
        drv.click_name(attr)
        assert getattr(app.model, attr) is (not before), attr


def test_the_irf_model_choice_is_picked_and_re_estimates_the_auto_irf(app, inputs):
    drv = open_demo(app, inputs)
    app.auto_extract()
    wait(drv)
    gaussian = app.model.session.irf_np["synthetic"].copy()
    drv.click_text("IRF/BG files")
    drv.click_name("irf_model")
    drv.draw(3)
    drv.click_text("Experimental")
    assert app.model.irf_model == "experimental"
    assert not np.array_equal(app.model.session.irf_np["synthetic"], gaussian)


def test_the_tail_model_is_picked_in_the_selector(app, inputs):
    drv = open_demo(app, inputs)
    app.auto_extract()
    wait(drv)
    drv.click_text("Burst MLE")
    drv.click_name("fit_model")
    drv.draw(3)
    drv.click_text("Tail fit (multi-exp)")
    assert app.model.fit_model == engine.TAIL_MODEL
    assert app.model.fit_curves is not None and app.model.fit_curves.irf is None
    assert "Tail lifetimes" in " ".join(texts(drv.draw(2)))
    names = [row["name"] for row in app.model.parameter_records()]
    assert names == ["tail_start", "tau1", "tau2"]


def test_pressing_opt_improves_a_displaced_irf(app, inputs):
    drv = open_demo(app, inputs)
    app.auto_extract()
    wait(drv)
    session = app.model.session
    irf = session.irf_np["synthetic"].copy()
    half = irf.size // 2
    irf[half:] = np.roll(irf[half:], 3)
    session.irf_np["synthetic"] = irf
    app.model.refit()
    before = app.model.two_istar
    drv.click_name("optimize")
    wait(drv)
    assert app.model.two_istar < 1.0 < before
    assert "Opt:" in app.model.status_text


def test_pressing_save_fit_stores_the_settings_on_the_selected_setup(app, inputs):
    drv = open_demo(app, inputs)
    drv.click_name("save_fit")
    assert "No detector setup selected" in app.model.status_text
    app.editor.model.save_setup("lab")
    app.model.shift = 2
    app.model.min_photons = 33
    app.model.fix_gamma = False
    drv.click_name("save_fit")
    saved = app.editor.model.setups["lab"]["detectors"]["synthetic"]["mle_settings"]
    assert saved["shift"] == 2 and saved["min_photons"] == 33 and saved["fix_gamma"] is False
    assert "saved to setup lab" in app.model.status_text
    app.model.shift = 0
    app.model.min_photons = 10
    app.model._apply_setup_settings("synthetic")
    assert app.model.shift == 2 and app.model.min_photons == 33


def test_the_new_controls_are_drawn_at_the_small_size(app, inputs):
    drv = open_demo(app, inputs)
    drv.resize(SMALL)
    shown = " ".join(texts(drv.draw(2)))
    assert "Opt" in shown and "Save fit" in shown
    drv.click_text("IRF/BG files")
    shown = " ".join(texts(drv.draw(2)))
    for label in ("Add IRF files", "Add background files", "IRF model", "Save VV/VHs"):
        assert label in shown, label


def test_the_tour_step_for_measured_files_shows_the_files_tab_and_points_at_its_button(app, inputs):
    drv = open_demo(app, inputs)
    steps = json.loads((Path(__file__).parents[1] / "gui" / "guide.json").read_text())["steps"]
    index = next(
        i for i, s in enumerate(steps) if (s.get("target") or {}).get("name") == "add_irf_files"
    )
    app.tour.start(index)  # the host callback shows the tab of the step's target
    drv.draw(3)
    assert "add_irf_files" in app.item_rects
    optimise = next(
        i for i, s in enumerate(steps) if (s.get("target") or {}).get("name") == "optimize"
    )
    app.tour.start(optimise)
    drv.draw(3)
    assert "optimize" in app.item_rects
