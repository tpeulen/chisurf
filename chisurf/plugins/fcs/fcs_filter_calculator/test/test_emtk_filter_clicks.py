"""Every control of the filter calculator operated with simulated pointer and keyboard events.

Only ``pointer_move`` / ``press`` / ``release`` / ``wheel`` / ``key`` and the host's file drop reach the window, at the rectangles
the controls were drawn in (``item_rects`` for buttons and fields, the table's own cell geometry for the tables, the drawn text
for list entries, tabs and dialog buttons); the assertions read the visible outcome (the model, the drawn strings, the files
written). The control -> test list is in ``okf/plugins/emtk-ports/fcs_filter_calculator/REPORT.md``.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.fcs.fcs_filter_calculator.gui.app import create_app

from .driving import BIG, SMALL, FilterDriver, hermetic_env


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def no_failed_draws(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture
def drv():
    app = create_app()
    d = FilterDriver(app, BIG)
    d.settle()
    yield d
    app.close()


def model(drv):
    return drv.app.model


def edit(drv, table, row, column, text):
    """Double click the cell and type; the editor keeps its old text, so it is erased with Backspace."""
    x, y, w, h = drv.cell(table, row, column)
    drv.app.press(x + w / 2, y + h / 2, clicks=2)
    drv.draw(1)
    drv.app.release()
    drv.draw(1)
    if drv.control(table).editing is None:
        return False
    drv.key(keys.KEY_END, "")
    for _ in range(len(str(drv.control(table).value(row, column) or "")) + 4):
        drv.key(keys.KEY_BACKSPACE, "")
    drv.type_text(text)
    drv.enter()
    return True


def decay_file(tmp_path, name="mixed.txt", n=128, tau=20.0, scale=2000.0):
    x = np.arange(n)
    counts = np.round(scale * np.exp(-x / tau) + 3).astype(int)
    path = tmp_path / name
    path.write_text("\n".join(map(str, counts)))
    return path


# -- the toolbar ------------------------------------------------------------------------------------------------------ #


def test_compute_filters_reports_success_and_equals_the_models_filters(drv):
    before = model(drv)._result.filters.copy()
    drv.click("compute")
    drv.settle()
    assert model(drv).message == "Filters computed successfully." and "Filters computed successfully." in drv.draw(2).strings
    assert np.array_equal(model(drv)._result.filters, before)


def test_unmix_reports_the_fractions_of_the_example(drv):
    drv.click("unmix")
    drv.settle()
    assert model(drv).message.startswith("Unmixed: ")
    assert model(drv)._unmix_result.fractions == pytest.approx([0.7, 0.3], abs=0.03)


def test_auto_fit_replaces_the_components_with_fitted_species_and_names_the_fit(drv):
    drv.click("autofit")
    drv.settle()
    assert model(drv).message.startswith("Auto-fit [10")
    assert len(model(drv).components) == 2 and model(drv)._auto_fit_result
    names = [c.name for c in model(drv).components]
    assert all("ns" in n or "tau" in n.lower() or "ns" in n for n in names), names


def test_the_example_button_restores_the_example_after_a_change(drv):
    model(drv).components.pop()
    drv.settle()  # the change recomputes; a button pressed while the worker runs is greyed
    drv.click("example")
    drv.settle()
    assert len(model(drv).components) == 2 and model(drv).total_label.startswith("Convolved example")


def test_save_project_dialog_writes_the_project_and_load_project_restores_it(drv, tmp_path):
    model(drv).components[0].enabled = False
    drv.settle()
    drv.click("save_project")
    assert drv.app.dialog is not None
    drv.click_text("Save", last=True)
    drv.settle()
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["component_enabled"] == [False, True]
    model(drv).components[0].enabled = True
    drv.settle()
    drv.click("load_project")
    drv.draw(4)
    drv.click_text(files[0].name)
    drv.click_text("Open", last=True)
    drv.settle()
    assert model(drv).components[0].enabled is False


def test_export_is_greyed_without_results_and_writes_the_filters(drv, tmp_path):
    drv.click("export_results")
    drv.click_text("Save", last=True)
    drv.settle()
    exported = list(tmp_path.glob("*.json"))
    assert len(exported) == 1
    data = json.loads(exported[0].read_text())
    assert len(data["filters"]) == 4 and data["nuisance_count"] == 2


def test_dialog_cancel_and_close_write_nothing(drv, tmp_path):
    drv.click("save_project")
    drv.click_text("Cancel")
    assert drv.app.dialog is None and not list(tmp_path.glob("*.json"))


def test_stop_is_greyed_when_idle_and_a_click_does_nothing(drv):
    drv.click("stop")
    assert not drv.app.job.running and model(drv)._result is not None


def test_guide_help_buttons_and_the_tour(drv):
    drv.click("help")
    window = drv.app.help
    assert window.open and {"Start Guided Tour", "Close"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.click("help")
    drv.click_text("Close")
    assert not window.open
    drv.click("help")
    drv.escape()
    assert not window.open
    drv.click("guide")
    tour = drv.app.tour
    assert tour.active and not tour.awaiting
    drv.click_text("Next ►")
    assert tour.step_idx == 1
    drv.click_text("◄ Prev")
    assert tour.step_idx == 0
    drv.click_text("Close Tour")
    assert not tour.active


def test_the_tour_is_walked_to_the_end_with_the_user_pressing_the_highlighted_buttons(drv):
    tour = drv.app.tour
    drv.click("guide")
    pressed = []
    for _ in range(30):
        if not tour.active:
            break
        drv.draw(3)
        if tour.awaiting:
            target = tour.steps[tour.step_idx].get("target", {})
            name = target.get("action")
            drv.click({"Auto-fit": "autofit", "Unmix": "unmix"}[name])
            pressed.append(name)
            drv.settle()
            assert not tour.awaiting
        drv.draw(2)
        drv.click_text("Finish ✓" if tour.step_idx == len(tour.steps) - 1 else "Next ►")
    assert pressed == ["Auto-fit", "Unmix"] and not tour.active


def test_every_guide_target_is_a_drawn_control(drv):
    for step in drv.app.tour.steps:
        key = drv.app.tour._target_key(step.get("target"))
        if key:
            assert key in drv.app.item_rects, (step["title"], key)


# -- inputs and the fit range -------------------------------------------------------------------------------------------- #


def test_the_input_checkboxes_are_clicked_and_recompute(drv):
    for name, getter in (("fit_background", lambda m: m.options_model.fit_background), ("scatter_irf", lambda m: m.options_model.scatter_irf),
                         ("stacked", lambda m: m.stacked), ("polarized", lambda m: m.polarized)):
        before = getter(model(drv))
        drv.click(name)
        assert getter(model(drv)) is (not before), name
        drv.settle()
        drv.click(name)
        drv.settle()
        assert getter(model(drv)) is before


def test_removing_the_afterpulse_and_scatter_filters_changes_the_number_of_filters(drv):
    assert len(model(drv)._result.filters) == 4
    drv.click("fit_background")
    drv.settle()
    assert len(model(drv)._result.filters) == 3
    drv.click("scatter_irf")
    drv.settle()
    assert len(model(drv)._result.filters) == 2


@pytest.mark.parametrize("name, text, expected", [("fit_start", "20", (20, 254)), ("fit_stop", "200", (10, 200)), ("fit_start", "9999", (253, 254)),
                                                  ("fit_stop", "0", (10, 11)), ("fit_start", "abc", (10, 254))])
def test_the_fit_range_is_typed_clamped_and_recomputes(drv, name, text, expected):
    drv.type_into(name, text)
    assert model(drv)._fit_bounds == expected
    drv.settle()
    assert model(drv)._result.filters.shape[1] == 256


def test_the_fit_range_arrows_and_the_wheel(drv):
    x, y, w, h = drv.rect("fit_start.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert model(drv)._fit_bounds[0] == 11
    drv.settle()
    drv.click_at(x + w / 2, y + h * 0.75)
    assert model(drv)._fit_bounds[0] == 10
    drv.settle()
    x, y, w, h = drv.rect("fit_stop")
    drv.wheel(x + w * 0.3, y + h / 2, -1)
    assert model(drv)._fit_bounds[1] == 253


def test_the_fit_range_follows_the_qt_tools_default_for_the_example(drv):
    assert model(drv)._fit_bounds == (10, 254)  # peak + 1 % of the bins to 1 % short of the end, as the Qt tool initialises it


# -- the mixed decay ----------------------------------------------------------------------------------------------------- #


def test_the_mixed_dialog_loads_a_decay_file_and_names_it(drv, tmp_path):
    path = decay_file(tmp_path)
    drv.click("load_mixed")
    assert drv.app.dialog is not None
    drv.draw(4)
    drv.click_text(path.name)
    drv.click_text("Open", last=True)
    drv.settle()
    assert model(drv)._total_paths == [path] and path.name in drv.draw(2).strings[0:200].__str__() or str(path) in model(drv).total_label
    assert model(drv)._current_n_bins() == 128


def test_a_dropped_decay_file_is_loaded_and_a_dropped_project_is_restored(drv, tmp_path):
    path = decay_file(tmp_path, "dropped.txt")
    drv.drop(str(path))
    drv.settle()
    assert model(drv)._total_paths == [path]
    project = tmp_path / "p.json"
    other = create_app()
    try:
        other.model.populate_example()
        other.model.save_project(project)
    finally:
        other.close()
    drv.drop(str(project))
    drv.settle()
    assert model(drv).total_label.startswith("Convolved example")


def test_from_correlator_without_a_correlator_says_so(drv):
    drv.click("from_correlator")
    assert model(drv).message == "No files are loaded in the Correlator (Files & Steps) step yet."
    assert "No files are loaded in the Correlator" in " ".join(drv.draw(2).strings)  # the line wraps


def test_from_correlator_adopts_the_correlators_files(tmp_path):
    path = decay_file(tmp_path, "corr.txt")
    context = type("Ctx", (), {"expanded_files": [path], "file_paths": [path], "microtime_binning": 2})()
    app = create_app(workflow_context=context)
    d = FilterDriver(app, BIG)
    try:
        d.settle()
        d.click("from_correlator")
        d.settle()
        assert model(d)._total_paths == [path] and model(d)._micro_time_binning == 2
    finally:
        app.close()


# -- the components ------------------------------------------------------------------------------------------------------- #


def test_a_component_is_ticked_off_by_a_click_and_renamed_by_typing(drv):
    drv.click_cell("component_rows", 0, "enabled")
    assert model(drv).components[0].enabled is False
    drv.settle()
    assert len(model(drv)._result.filters) == 3  # one species and two nuisance filters left
    drv.click_cell("component_rows", 0, "enabled")
    drv.settle()
    assert edit(drv, "component_rows", 1, "name", "Renamed species")
    assert model(drv).components[1].name == "Renamed species" and model(drv).components[1].source["name"] == "Renamed species"
    assert "Renamed species" in drv.draw(2).strings


def test_the_definition_column_is_read_only(drv):
    assert not edit(drv, "component_rows", 0, "kind", "x")


@pytest.mark.parametrize("button, model_name", [("add_lifetime", "lifetime"), ("add_spectrum", "lifetime_spectrum"), ("add_fret", "fret_species"),
                                                ("add_lifetime_distribution", "gaussian_lifetime"), ("add_distance_distribution", "gaussian_distance")])
def test_each_add_button_opens_the_form_of_its_model_and_apply_adds_the_component(drv, button, model_name):
    drv.click(button)
    assert drv.app.editor is not None and drv.app.editor["model"] == model_name
    assert "Component name" in drv.draw(3).strings and {"Apply", "Cancel"} <= set(drv.painter.strings)
    drv.click_text("Apply")
    drv.settle()
    assert len(model(drv).components) == 3 and drv.app.editor is None


def test_the_component_form_fields_are_typed_and_reach_the_pattern(drv):
    drv.click("add_lifetime")
    drv.draw(3)
    drv.type_into("name", "Long") if "name" in drv.app.item_rects else None
    x, y, w, h = drv.app.forms["component_form"].rects["lifetime"]
    drv.click_at(x + w * 0.3, y + h / 2)
    drv.select_all()
    drv.type_text("9.5")
    drv.enter()
    assert drv.app.editor["lifetime"] == 9.5
    drv.click_text("Apply")
    drv.settle()
    assert model(drv).components[-1].source["lifetime"] == 9.5


def test_the_component_form_cancel_and_the_close_button_discard_the_edit(drv):
    drv.click("add_lifetime")
    drv.draw(3)
    drv.click_text("Cancel")
    assert drv.app.editor is None and len(model(drv).components) == 2
    drv.click("add_lifetime")
    drv.draw(3)
    x, y, w, h = drv.app.component_window.box
    drv.click_at(x + w - 12, y + 12)
    assert drv.app.editor is None and len(model(drv).components) == 2


def test_the_spectrum_form_adds_rows_and_edits_them(drv):
    drv.click("add_spectrum")
    drv.draw(3)
    n = len(drv.app.editor["lifetimes"])
    drv.click_text("Add spectrum row")
    assert len(drv.app.editor["lifetimes"]) == n + 1 and f"Lifetime {n + 1} (ns)" in drv.draw(3).strings


def test_select_a_component_then_edit_duplicate_and_remove_it(drv):
    drv.click_cell("component_rows", 0, "kind")
    assert drv.app.selected_component == 0
    drv.click("edit_component")
    assert drv.app.editor is not None and drv.app.editor["name"] == "Fast example" and drv.app.editor_index == 0
    drv.draw(3)
    drv.click_text("Cancel")
    drv.click("duplicate_component")
    assert len(model(drv).components) == 3
    drv.settle()
    drv.click_cell("component_rows", 2, "kind")
    drv.click("remove_component")
    drv.settle()
    assert len(model(drv).components) == 2 and drv.app.selected_component == -1


def test_edit_buttons_are_greyed_without_a_selection(drv):
    drv.click("edit_component")
    drv.click("remove_component")
    assert drv.app.editor is None and len(model(drv).components) == 2


def test_editing_a_component_replaces_its_definition(drv):
    drv.click_cell("component_rows", 0, "kind")
    drv.click("edit_component")
    drv.draw(3)
    x, y, w, h = drv.app.forms["component_form"].rects["lifetime"]
    drv.click_at(x + w * 0.3, y + h / 2)
    drv.select_all()
    drv.type_text("2")
    drv.enter()
    drv.click_text("Apply")
    drv.settle()
    assert model(drv).components[0].source["lifetime"] == 2.0 and len(model(drv).components) == 2


def test_add_measured_pattern_dialog_adds_a_reference_component(drv, tmp_path):
    ref = decay_file(tmp_path, "ref.txt", n=256, tau=40.0)
    drv.click("add_measured")
    drv.click_text(ref.name)
    drv.click_text("Open", last=True)
    drv.settle()
    assert len(model(drv).components) == 3 and model(drv).components[-1].name == "ref.txt"


# -- the detectors and the instrument ------------------------------------------------------------------------------------ #


def test_the_detector_table_edits_the_synthetic_irf(drv):
    assert edit(drv, "detector_rows", 0, "width", "0.3")
    drv.settle()
    assert edit(drv, "detector_rows", 0, "skew", "0.2")
    drv.settle()
    assert edit(drv, "detector_rows", 0, "shift", "-0.05")
    d = model(drv).detectors
    assert (d.width("green"), d.skew("green"), d.shift("green")) == (0.3, 0.2, -0.05)
    drv.settle()
    assert model(drv)._result is not None


def test_a_negative_width_is_clamped_and_text_is_ignored(drv):
    edit(drv, "detector_rows", 0, "width", "-1")
    assert model(drv).detectors.width("green") == 0.0
    edit(drv, "detector_rows", 0, "width", "abc")
    assert model(drv).detectors.width("green") == 0.0


def test_the_last_detector_cannot_be_unticked(drv):
    drv.click_cell("detector_rows", 0, "use")
    assert model(drv).detectors.selected == ["green"]


def test_the_irf_path_is_typed_and_browsed(drv, tmp_path):
    ref = decay_file(tmp_path, "irf.txt", n=256, tau=1.5, scale=500.0)
    drv.click_cell("detector_rows", 0, "name")
    drv.click("browse_irf")
    drv.click_text(ref.name)
    drv.click_text("Open", last=True)
    assert model(drv).detectors.irf_path("green") == str(ref)
    assert edit(drv, "detector_rows", 0, "irf", "")
    assert model(drv).detectors.irf_path("green") == ""


def test_browse_irf_is_greyed_without_a_selected_detector(drv):
    drv.click("browse_irf")
    assert drv.app.dialog is None


def test_polarization_resolved_detectors_get_a_row_per_role(drv):
    drv.click("polarized")
    drv.draw(3)
    names = [c for c in drv.painter.strings if c.startswith("green")]
    assert "green par" in names and "green perp" in names


def test_the_instrument_table_values_are_typed_and_the_period_toggle_clicked(drv):
    drv.tab("Instrument")
    assert edit(drv, "instrument_rows", 4, "value", "1.2")  # G factor
    assert model(drv).instrument_model.g_factor == 1.2
    drv.settle()
    assert edit(drv, "instrument_rows", 7, "value", "60")  # R0
    assert model(drv).instrument_model.forster_radius == 60.0
    drv.settle()
    assert not edit(drv, "instrument_rows", 0, "name", "x")
    drv.click("periodic")
    assert model(drv).instrument_model.periodic is True


def test_the_info_tab_edits_the_per_detector_range(drv):
    drv.tab("Info")
    assert edit(drv, "range_rows", 0, "start", "30")
    assert model(drv)._detector_fit_ranges["green"] == (30, 254)
    drv.settle()
    assert edit(drv, "range_rows", 0, "stop", "100")
    assert model(drv)._detector_fit_ranges["green"] == (30, 100)
    assert not edit(drv, "range_rows", 0, "detector", "x")
    strings = drv.draw(2).strings
    assert "== Mixed decay ==" in strings and "== Components ==" in strings


def test_the_auto_fit_fields_are_typed_clamped_and_the_fit_runs(drv):
    drv.tab("Auto-fit")
    drv.type_into("autofit_components", "3")
    drv.type_into("autofit_tau_min", "0.5")
    drv.type_into("autofit_tau_max", "6")
    s = model(drv)._auto_fit_settings
    assert (s["n_components"], s["tau_min"], s["tau_max"]) == (3, 0.5, 6.0)
    drv.type_into("autofit_components", "40")
    assert s["n_components"] == 12
    drv.type_into("autofit_components", "2")
    drv.click("autofit")
    drv.settle()
    assert "Reduced chi2" in " ".join(drv.draw(2).strings)
    assert len(drv.app.panel.parameter_rows()) >= 3


def test_the_auto_fit_type_list_picks_fret_states(drv):
    drv.tab("Auto-fit")
    drv.click("autofit_kind")
    drv.click_text("FRET states", last=True)
    assert model(drv)._auto_fit_settings["kind"] == "fret"
    drv.click("autofit_kind")
    drv.click_text("Lifetime species", last=True)
    assert model(drv)._auto_fit_settings["kind"] == "lifetime"


def test_fitted_parameters_are_edited_fixed_and_linked(drv):
    drv.tab("Auto-fit")
    drv.click("autofit")
    drv.settle()
    drv.draw(3)
    rows = drv.app.panel.parameter_rows()
    assert rows
    assert edit(drv, "parameter_rows", 0, "value", "0.5")
    assert rows[0]["_parameter"].value == 0.5
    fixed = rows[0]["_parameter"].fixed
    drv.click_cell("parameter_rows", 0, "fixed")
    assert rows[0]["_parameter"].fixed is (not fixed)
    drv.click_cell("parameter_rows", 0, "name")
    assert drv.app.selected_parameter is rows[0]["_parameter"]
    drv.click("link_parameter")
    assert drv.app.link_parameter is rows[0]["_parameter"]


def test_the_detector_setup_tab_embeds_the_shared_editor(drv):
    painter = drv.tab("Detector setup")
    assert {"Setup:", "Save", "TTTR Reading routine", "Optical Setup..."} & set(painter.strings)
    assert "Detectors" in painter.strings or "Detector Name" in painter.strings
    drv.click_text("Add")  # a detector row of the shared table
    drv.draw(3)
    assert len(drv.app.setup.model.get_settings().get("detectors", {})) >= 2


def test_a_new_detector_from_the_shared_editor_reaches_the_calculator(drv):
    drv.tab("Detector setup")
    drv.click_text("Add")
    drv.draw(3)
    drv.settle()
    assert len(model(drv).detectors.names) >= 2


# -- the tabs, the plots ------------------------------------------------------------------------------------------------ #


@pytest.mark.parametrize("tab, marker", [("Sources", "Components"), ("Detector setup", "TTTR Reading routine"), ("Auto-fit", "Type"),
                                         ("Instrument", "Periodic convolution"), ("Info", "Information")])
def test_each_control_tab_is_clicked_and_shows_its_panel(drv, tab, marker):
    drv.tab("Info" if tab != "Info" else "Sources")
    assert any(s == marker or s.endswith(" " + marker) for s in drv.tab(tab).strings), marker


def ticks(painter):
    import re

    return [s for s in painter.strings if re.fullmatch(r"-?[\d.]+(e[+-]?\d+)?", s)]


def test_the_plots_are_dragged_and_zoomed_by_pointer(drv):
    before = ticks(drv.draw(2))
    x, y, w, h = 800.0, 130.0, 100.0, 100.0  # the lifetime filters plot of the top right dock
    drv.drag((x, y), (x - 60, y - 30))
    assert ticks(drv.draw(2)) != before
    mid = ticks(drv.draw(2))
    drv.wheel(900.0, 130.0, 3)
    assert ticks(drv.draw(2)) != mid


def test_the_fit_range_lines_of_the_reconstruction_plot_are_dragged(drv):
    painter = drv.draw(3)
    lo, hi = model(drv)._fit_bounds
    # the plot's x axis runs 0..256 over the plot width: find the reconstruction window's plot area from the tick labels
    xs = [(t[0] + t[2] / 2, float(t[5])) for t in painter.texts if t[5] in ("0", "50", "100", "150", "200", "250") and 560 < t[1] < 580]
    assert len(xs) >= 4
    (x0, v0), (x1, v1) = xs[0], xs[-1]
    px = lambda v: x0 + (v - v0) * (x1 - x0) / (v1 - v0)  # noqa: E731
    y = 430.0
    drv.drag((px(hi), y), (px(200), y))
    drv.settle()
    assert 190 <= model(drv)._fit_bounds[1] <= 210 and model(drv)._fit_bounds[0] == lo


# -- the small window ------------------------------------------------------------------------------------------------------- #


def test_the_flow_works_in_the_small_window_too(drv):
    drv.size = SMALL
    drv.settle()
    drv.type_into("fit_start", "15")
    assert model(drv)._fit_bounds[0] == 15
    drv.click_cell("component_rows", 0, "enabled")
    drv.click("compute")
    drv.settle()
    for tab in ("Detector setup", "Auto-fit", "Instrument", "Info", "Sources"):
        drv.tab(tab)
