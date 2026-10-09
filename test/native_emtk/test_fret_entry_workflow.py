"""The guided FRET entry keeps scientific inputs and expert controls explicit."""

import json
from pathlib import Path

import pytest
from emtk.testing import Driver

from chisurf.plugins.fret_line.gui.app import FRETLineApp
from chisurf.plugins.fret_line.gui.model import FretLineModel


def test_fret_line_is_visible_in_the_fret_menu():
    """The existing native tool is discoverable through its declared FRET menu."""
    path = Path(__file__).resolve().parents[2] / "chisurf/plugins/fret_line/manifest.json"
    manifest = json.loads(path.read_text())
    assert manifest["menu_hidden"] is False
    assert manifest["display_name"] == "Spectroscopy:FRET:FRET Line Generator"


def test_your_dyes_is_the_first_default_view(tmp_path, monkeypatch):
    """A fresh calculator presents pair inputs and retains every expert view."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    app = FRETLineApp()
    try:
        Driver(app, (640, 480)).draw(3)
        assert app.docks.is_shown("your_dyes")
        assert {"dye_pair", "pair_tau", "pair_r0", "apply_pair", "load_example"} <= app.form.rects.keys()
        for key in ["components", "sweep", "lines", "editor"]:
            app.show_advanced(key)
            Driver(app, (640, 480)).draw(3)
            assert app.docks.is_shown(key)
    finally:
        app.close()


def test_pair_application_updates_canonical_physical_inputs():
    """An explicit pair uses consistent donor/reference lifetime and radius."""
    model = FretLineModel()
    try:
        model.pair_tau = 3.5
        model.pair_r0 = 60.0
        model.apply_dye_pair()
        values = {p.canonical_id: p.value for p in model.selected["model"].parameters_all}
        assert values["donor.tau.0"] == model.tau_d0 == values["fret.tau0"] == 3.5
        assert values["fret.forster_radius"] == 60.0
    finally:
        model.close()


def test_pair_rejects_invalid_values_before_mutating_models():
    """Invalid physical input leaves every model parameter intact."""
    model = FretLineModel()
    try:
        before = {p.canonical_id: p.value for p in model.selected["model"].parameters_all}
        model.pair_tau = -1.0
        with pytest.raises(ValueError):
            model.apply_dye_pair()
        assert {p.canonical_id: p.value for p in model.selected["model"].parameters_all} == before
    finally:
        model.close()


def test_custom_pair_matches_fixed_distance_physics():
    """A nondefault pair has the independent single-distance Förster relation."""
    import numpy as np

    from chisurf.core.fluorescence.fret.fret_line import find_parameter

    model = FretLineModel()
    try:
        model.model_label = "FRET: Fixed distance"
        model.pair_tau, model.pair_r0 = 3.0, 60.0
        model.apply_dye_pair()
        find_parameter(model.selected["model"], "fret.kappa2").value = 2 / 3
        model._select_default_sweep()
        model.minimum, model.maximum, model.n_points = 40., 80., 5
        line = model.add_line()
        assert line is not None, model.message
        result = line["result"]
        distance = np.asarray(result["parameter_values"])
        expected = 3.0 / (1 + (60.0 / distance) ** 6)
        np.testing.assert_allclose(result["tau_x"], expected, rtol=1e-10)
        np.testing.assert_allclose(result["tau_f"], expected, rtol=1e-10)
        np.testing.assert_allclose(result["e_fret"], 1 - expected / 3.0, rtol=1e-10)
    finally:
        model.close()


def test_multiexponential_donor_is_rejected_atomically():
    """The starter does not damage a spectrum edited in Advanced."""
    model = FretLineModel()
    try:
        model.apply_donor_reference({("amplitude", 0): .4, ("tau", 0): 2.,
                                     ("amplitude", 1): .6, ("tau", 1): 5.})
        before = {p.canonical_id: p.value for p in model.selected["model"].parameters_all}
        model.pair_tau, model.pair_r0 = 3., 60.
        with pytest.raises(ValueError, match="multiexponential"):
            model.apply_dye_pair()
        assert {p.canonical_id: p.value for p in model.selected["model"].parameters_all} == before
    finally:
        model.close()


def test_example_keeps_compute_as_a_user_action(tmp_path, monkeypatch):
    """The example is declared/cached, while the waiting tour leaves Compute unpressed."""
    from chisurf.plugins.fret_line import demo

    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    app = FRETLineApp()
    try:
        driver = Driver(app, (640, 480))
        driver.draw(3)
        driver.click("load_example")
        driver.draw(3)
        assert app.model.lines == []
        assert Path(app.model.example_path).is_file()
        assert demo.make_demo(Path(app.model.example_path).parent) == Path(app.model.example_path)
        driver.click("add_line")
        driver.draw(3)
        assert len(app.model.lines) == 1
    finally:
        app.close()


def test_linked_pair_input_is_rejected_before_any_component_changes():
    """A linked parameter in a later component cannot leave earlier writes applied."""
    from chisurf.core.fluorescence.fret.fret_line import find_parameter

    model = FretLineModel()
    try:
        first = model.components[0]["model"]
        model.add_component()
        second = model.components[1]["model"]
        find_parameter(second, "fret.forster_radius").link = find_parameter(first, "fret.forster_radius")
        before = [{p.canonical_id: p.value for p in c["model"].parameters_all}
                  for c in model.components]
        model.pair_tau, model.pair_r0 = 3., 60.
        with pytest.raises(ValueError, match="linked"):
            model.apply_dye_pair()
        assert [{p.canonical_id: p.value for p in c["model"].parameters_all}
                for c in model.components] == before
    finally:
        model.close()


def test_the_tour_waits_for_demo_and_advanced_buttons(tmp_path, monkeypatch):
    """Every tour target is real; collapsed Advanced opens through a user click."""
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path))
    app = FRETLineApp()
    try:
        driver = Driver(app, (640, 480))
        driver.draw(3)
        app.tour.start(step=1)
        driver.draw(3)
        assert app.tour.awaiting
        assert app.tour.get_target_rect("load_example") is not None
        driver.click("load_example")
        driver.draw(3)
        assert app.model.lines == []
        app.tour.stop()
        app.tour.start(step=3)
        driver.draw(3)
        assert app.tour.get_target_rect("Advanced.fold") is not None
        driver.click("Advanced.fold")
        driver.draw(3)
        assert app.form.folds["Advanced"] is True
    finally:
        app.close()


def test_entry_question_and_pair_label_are_drawn():
    """The entry explains the question rather than silently dropping a text section."""
    app = FRETLineApp()
    try:
        painter = Driver(app, (640, 480)).draw(3)
        text = " ".join(painter.strings)
        assert "Which lifetime-efficiency line" in text
        assert "Dye pair" in text
    finally:
        app.close()


def test_gui_validation_uses_the_existing_notice():
    """Invalid manual inputs are shown instead of becoming a swallowed draw error."""
    app = FRETLineApp()
    try:
        driver = Driver(app, (640, 480))
        driver.draw(3)
        app.model.pair_tau = -1.
        driver.click("apply_pair")
        painter = driver.draw(3)
        assert app.model.dialog_title == "Dye pair"
        assert "finite and positive" in " ".join(painter.strings)
    finally:
        app.close()
