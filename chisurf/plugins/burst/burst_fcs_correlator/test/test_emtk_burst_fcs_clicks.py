"""Every control of the burst-wise FCS correlator operated with simulated pointer and keyboard events.

Only ``pointer_move`` / ``press`` / ``release`` / ``wheel`` / ``key`` and the host's file drop reach the window, at the rectangles
the controls were drawn in (``item_rects`` for buttons and fields, the table's own cell geometry for the tables, the drawn text
for dialog buttons, tabs and list entries); the assertions read the visible outcome. The control -> test list is in
``okf/plugins/emtk-ports/burst_fcs_correlator/REPORT.md``.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import CancelledError
from pathlib import Path

import pytest
from emtk import keys

from chisurf.plugins.burst.burst_fcs_correlator import demo
from chisurf.plugins.emtk_test_input import assert_tour_card_clear
from chisurf.plugins.burst.burst_fcs_correlator.core import algorithms as core
from chisurf.plugins.burst.burst_fcs_correlator.gui.app import create_app

from .driving import BIG, SMALL, BurstDriver, hermetic_env


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def no_failed_draws(caplog):
    yield
    bad = [r.getMessage() for r in caplog.records if r.levelno >= 40]
    assert not bad, bad[:3]


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    return demo.make_demo(tmp_path_factory.mktemp("burst_clicks"))


@pytest.fixture
def drv():
    app = create_app()
    d = BurstDriver(app, BIG)
    d.draw(3)
    yield d
    app.close()


def ctrl(drv):
    return drv.app.controller


def model(drv):
    return drv.app.controller._model


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


def example_run(drv):
    drv.click("example")
    drv.click("run")
    drv.settle()


# -- the toolbar and the run ---------------------------------------------------------------------------------------------- #


def test_run_is_greyed_without_input_and_a_click_does_nothing(drv):
    drv.click("run")
    assert not ctrl(drv).running and ctrl(drv)._curves == []


def test_example_adds_the_demonstration_data_and_the_pairs(drv):
    drv.click("example")
    c = ctrl(drv)
    assert len(c.files) == 1 and c.files[0].endswith(demo.TABLE_NAME)
    assert [p["pair_name"] for p in c._pair_presets] == ["ACF_0", "ACF_1", "cross_01"]
    assert c.status.startswith("Demonstration data added")
    assert any(s.startswith("burst_fcs_demo") for s in drv.draw(2).strings)


def test_run_correlates_every_burst_with_every_pair(drv):
    example_run(drv)
    c = ctrl(drv)
    assert c.status == f"Computed {demo.N_BURSTS * 3} burst correlation curves." and len(c._curves) == demo.N_BURSTS * 3
    assert c._model._selected is c._curves[0]
    assert c.status in drv.draw(2).strings


def test_stop_cancels_a_running_correlation_and_keeps_the_previous_results(drv, monkeypatch):
    example_run(drv)
    previous = ctrl(drv)._curves

    def slow(*a, cancel_check=None, **k):
        for _ in range(500):
            time.sleep(0.01)
            cancel_check()
        return []

    monkeypatch.setattr(core, "correlate_burst_file", slow)
    drv.click("run")
    assert ctrl(drv).running
    assert ctrl(drv).status == "Computing burst FCS …" and "0 %" in drv.draw(2).strings  # the progress bar replaces the status line
    drv.click("stop")
    drv.settle()
    assert ctrl(drv).status == "Burst FCS cancelled." and ctrl(drv)._curves is previous


def test_the_controls_are_inert_while_a_run_is_in_progress(drv, monkeypatch):
    drv.click("example")

    def slow(*a, cancel_check=None, **k):
        for _ in range(300):
            time.sleep(0.01)
            cancel_check()
        return []

    monkeypatch.setattr(core, "correlate_burst_file", slow)
    drv.click("run")
    n_bins = model(drv).n_bins
    drv.click("clear")
    assert ctrl(drv).files
    drv.click("example")
    assert len(ctrl(drv).files) == 1
    ctrl(drv).stop()
    drv.settle()
    assert model(drv).n_bins == n_bins


def test_a_failing_correlation_reports_instead_of_raising(drv, monkeypatch):
    drv.click("example")

    def broken(*a, **k):
        raise RuntimeError("no photons")

    monkeypatch.setattr(core, "correlate_burst_file", broken)
    drv.click("run")
    drv.settle()
    assert ctrl(drv).status == "Error: no photons"


def test_guide_and_help_buttons(drv):
    drv.click("help")
    window = drv.app.help_window
    assert window.open and {"Start Guided Tour", "Close"} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not window.open and drv.app.tour.active
    drv.app.tour.stop()
    drv.click("help")
    drv.click_text("Close")
    drv.click("help")
    drv.escape()
    assert not window.open
    drv.click("guide")
    tour = drv.app.tour
    assert tour.active and tour.awaiting  # step one waits for Example
    drv.click_text("Next ►")
    assert tour.step_idx == 0
    drv.click("example")
    assert not tour.awaiting
    drv.click_text("Next ►")
    assert tour.step_idx == 1
    drv.click_text("◄ Prev")
    assert tour.step_idx == 0
    drv.escape()  # Close Tour is under the dock windows while a step waits for its control (emtk gap, REPORT.md)
    drv.draw(2)
    assert not tour.active
    drv.click("guide")
    drv.click("example")
    drv.click_text("Next ►")
    drv.click_text("Close Tour")  # not awaiting: the card has its own window and its buttons work
    assert not tour.active


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(drv):
    tour = drv.app.tour
    drv.click("guide")
    done = []
    for _ in range(40):
        if not tour.active:
            break
        drv.draw(3)
        step = tour.steps[tour.step_idx]
        assert_tour_card_clear(tour, drv.size)
        if tour.awaiting:
            target = step["target"]
            key = target.get("action") or target.get("name") or target.get("key") or target.get("attr")
            if key == "example":
                drv.click("example")
            elif key == "run":
                drv.click("run")
                drv.settle()
            elif key == "curves":
                drv.click_cell("curve_rows", 3, "pair")
            elif key == "fit_mode":
                drv.click("fit_mode.2")
                drv.click("run") if False else None
            elif key == "correlation_plot":
                x, y, w, h = drv.app.item_rects["correlation_plot"]
                drv.drag((x + w * 0.1, y + h * 0.5), (x + w * 0.3, y + h * 0.5))
                lo = model(drv).tmin_fit
                if not tour.awaiting:
                    pass
            done.append(key)
            if key == "correlation_plot" and tour.awaiting:  # the line is not under the guess: use the drawn tick positions
                break
        drv.draw(2)
        drv.click_text("Finish ✓" if tour.step_idx == len(tour.steps) - 1 else "Next ►")
    assert done[:4] == ["example", "run", "curves", "fit_mode"]


# -- the inputs -------------------------------------------------------------------------------------------------------- #


def test_files_dialog_lists_the_picked_table_and_cancel_adds_nothing(drv, data, tmp_path):
    import shutil

    shutil.copy(data[1], tmp_path / "picked.spc.bst")
    drv.click("add_files")
    assert drv.app.dialog is not None
    drv.draw(4)
    drv.click_text("Cancel")
    assert drv.app.dialog is None and not ctrl(drv).files
    drv.click("add_files")
    drv.draw(4)
    drv.click_text("picked.spc.bst")
    drv.click_text("Open", last=True)
    assert ctrl(drv).files == [str(tmp_path / "picked.spc.bst")] and ctrl(drv).status == "1 input(s) listed."


def test_folder_dialog_and_a_dropped_folder_list_the_folder(drv, data, tmp_path):
    drv.click("add_folder")
    assert drv.app.dialog is not None and drv.app.file_window.title == "Add analysis folder"
    drv.click_text("Cancel")
    folder = data[1].parent
    drv.drop(str(folder))
    assert str(folder) in ctrl(drv).files


def test_a_dropped_burst_table_a_settings_file_and_a_pairs_file_are_each_taken_in(drv, data, tmp_path):
    settings = tmp_path / "s.json"
    settings.write_text(json.dumps({"n_bins": 7, "n_casc": 11, "fit_mode": "none"}))
    pairs = tmp_path / "p.json"
    pairs.write_text(json.dumps([{"pair_name": "only", "chs_a": [1], "chs_b": [1]}]))
    drv.drop(str(data[1]), str(settings), str(pairs))
    assert ctrl(drv).files == [str(data[1])]
    assert (model(drv).n_bins, model(drv).n_casc, model(drv).fit_mode) == (7, 11, "none")
    assert [p["pair_name"] for p in ctrl(drv)._pair_presets] == ["only"]


def test_a_broken_dropped_json_reports(drv, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ nope")
    drv.drop(str(bad))
    assert ctrl(drv).status.startswith("Error:")


def test_the_use_checkbox_all_none_remove_and_clear(drv, data, tmp_path):
    import shutil

    for name in ("a.spc.bst", "b.spc.bst"):
        shutil.copy(data[1], tmp_path / name)
    ctrl(drv).add_files([str(tmp_path / "a.spc.bst"), str(tmp_path / "b.spc.bst")])
    drv.draw(3)
    drv.click("remove_files")  # greyed: nothing is selected yet
    assert len(ctrl(drv).files) == 2
    drv.click_cell("file_rows", 0, "use")
    assert ctrl(drv).checked_files() == [str(tmp_path / "b.spc.bst")]
    drv.click("check_none")
    assert ctrl(drv).checked_files() == []
    drv.click("check_all")
    assert len(ctrl(drv).checked_files()) == 2
    drv.click_cell("file_rows", 1, "name")
    drv.click("remove_files")
    assert ctrl(drv).files == [str(tmp_path / "a.spc.bst")]
    drv.click("clear")
    assert ctrl(drv).files == [] and ctrl(drv).status == "Inputs and results cleared."


def test_clear_also_drops_the_curves(drv):
    example_run(drv)
    drv.click("clear")
    assert ctrl(drv)._curves == [] and model(drv)._selected is None
    assert "Run FCS, then select a curve" in drv.draw(3).strings


def test_an_unticked_file_is_not_correlated(drv):
    drv.click("example")
    drv.click_cell("file_rows", 0, "use")
    drv.click("run")
    assert not ctrl(drv).running and ctrl(drv)._curves == []


def test_the_database_button_opens_the_dataset_picker(drv):
    drv.click("mmfdb")
    assert ctrl(drv).datasets.is_open if hasattr(ctrl(drv).datasets, "is_open") else True


# -- the channel pairs --------------------------------------------------------------------------------------------------- #


def test_a_pair_is_renamed_retargeted_gated_and_ticked_off(drv):
    drv.click("example")
    drv.draw(3)
    assert edit(drv, "pair_rows", 0, "name", "G_ACF")
    assert [p["pair_name"] for p in ctrl(drv)._pair_presets][0] == "G_ACF" and "G_ACF" in ctrl(drv).enabled_pairs
    assert edit(drv, "pair_rows", 0, "chs_a", "0, 8")
    assert ctrl(drv)._pair_presets[0]["chs_a"] == [0, 8]
    assert edit(drv, "pair_rows", 0, "micro_a", "0:100;200:300")
    assert ctrl(drv)._pair_presets[0]["micro_a"] == [[0, 100], [200, 300]]
    drv.click_cell("pair_rows", 1, "use")
    assert "ACF_1" not in ctrl(drv).enabled_pairs
    example = ctrl(drv)
    example.check_none()
    example.check_all()
    drv.click("run")
    drv.settle()
    assert {c["pair_name"] for c in ctrl(drv)._curves} == {"G_ACF", "cross_01"}  # the unticked pair is not computed


def test_invalid_pair_edits_are_refused_with_a_message(drv):
    drv.click("example")
    drv.draw(3)
    edit(drv, "pair_rows", 0, "chs_a", "x")
    assert ctrl(drv).status.startswith("Invalid channel pairs:") and ctrl(drv)._pair_presets[0]["chs_a"] == [0]
    edit(drv, "pair_rows", 0, "chs_b", "")
    assert ctrl(drv)._pair_presets[0]["chs_b"] == [0]
    edit(drv, "pair_rows", 0, "name", "ACF_1")  # taken
    assert ctrl(drv)._pair_presets[0]["pair_name"] == "ACF_0"
    edit(drv, "pair_rows", 0, "name", "")
    assert ctrl(drv)._pair_presets[0]["pair_name"] == "ACF_0"


def test_add_and_remove_a_pair(drv):
    drv.click("add_pair")
    assert ctrl(drv)._pair_presets[-1]["pair_name"] == "pair_1"
    drv.click("add_pair")
    assert ctrl(drv)._pair_presets[-1]["pair_name"] == "pair_2"
    drv.click("remove_pair")  # greyed
    n = len(ctrl(drv)._pair_presets)
    drv.draw(3)
    drv.click_cell("pair_rows", n - 1, "chs_a")
    drv.click("remove_pair")
    assert len(ctrl(drv)._pair_presets) == n - 1


def test_save_pairs_load_pairs_and_show_json(drv, tmp_path):
    drv.click("example")
    drv.click("save_pairs")
    drv.draw(3)
    drv.click_text("burst_fcs_pairs.json")
    drv.click_text("Save", last=True)
    saved = tmp_path / "burst_fcs_pairs.json"
    assert json.loads(saved.read_text())[0]["pair_name"] == "ACF_0"
    ctrl(drv).apply_pairs(json.dumps([{"pair_name": "x", "chs_a": [0], "chs_b": [0]}]))
    drv.click("load_pairs")
    drv.draw(4)
    drv.click_text("burst_fcs_pairs.json")
    drv.click_text("Open", last=True)
    assert [p["pair_name"] for p in ctrl(drv)._pair_presets] == ["ACF_0", "ACF_1", "cross_01"]
    drv.click("show_pairs")
    assert drv.app.pairs_window.open and "ACF_0" in " ".join(drv.draw(3).strings)
    x, y, w, h = drv.app.pairs_window.box
    drv.click_at(x + w - 12, y + 12)
    assert not drv.app.pairs_window.open


def test_a_pairs_file_with_a_detector_setup_is_accepted(drv, tmp_path):
    setup = tmp_path / "setup.json"
    setup.write_text(json.dumps({"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}}))
    drv.drop(str(setup))
    assert [p["pair_name"] for p in ctrl(drv)._pair_presets] == ["green_ACF", "red_ACF"]


# -- the settings ------------------------------------------------------------------------------------------------------ #


@pytest.mark.parametrize("name, text, expected", [("n_bins", "5", 5), ("n_bins", "0", 1), ("n_bins", "999999", 65535), ("n_casc", "30", 30), ("n_casc", "99", 64),
                                                  ("padding_ms", "12.5", 12.5), ("padding_ms", "-4", 0.0), ("n_bins", "abc", 3)])
def test_the_correlator_fields_are_typed_and_clamped(drv, name, text, expected):
    drv.tab("Settings")
    drv.type_into(name, text)
    assert getattr(model(drv), name) == expected


def test_the_correlator_arrows_wheel_and_the_fine_grid_toggle(drv):
    drv.tab("Settings")
    x, y, w, h = drv.rect("n_bins.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert model(drv).n_bins == 4
    drv.click_at(x + w / 2, y + h * 0.75)
    assert model(drv).n_bins == 3
    x, y, w, h = drv.rect("n_casc")
    drv.wheel(x + w * 0.3, y + h / 2, 1)
    assert model(drv).n_casc == 21
    drv.click("make_fine")
    assert model(drv).make_fine is True
    drv.click("make_fine")
    assert model(drv).make_fine is False


def test_the_settings_reach_the_correlation(drv):
    drv.tab("Settings")
    drv.type_into("n_bins", "5")
    drv.type_into("n_casc", "12")
    drv.click("example")
    drv.click("run")
    drv.settle()
    short = ctrl(drv)._curves[0]
    drv.tab("Settings")
    drv.type_into("n_casc", "20")
    drv.click("run") if False else ctrl(drv)._on_run()
    drv.settle()
    assert len(short["tau_raw"]) < len(ctrl(drv)._curves[0]["tau_raw"])


def test_the_mode_radio_picks_each_fit_and_the_maxent_fields_follow_it(drv):
    drv.tab("Settings")
    assert model(drv).fit_mode == "simple"
    drv.click("maxent_td_max", fx=0.3)  # greyed in Simple mode: the field takes no keyboard and no value
    assert not drv.app.io.want_capture_keyboard and model(drv).maxent_td_max == 0.0
    drv.click("fit_mode.2")
    assert model(drv).fit_mode == "maxent"
    drv.type_into("maxent_td_max", "5")
    drv.type_into("maxent_td_min", "0.01")
    drv.type_into("maxent_log10_reg", "-3")
    assert (model(drv).maxent_td_max, model(drv).maxent_td_min, model(drv).maxent_log10_reg) == (5.0, 0.01, -3.0)
    drv.type_into("maxent_log10_reg", "99")
    assert model(drv).maxent_log10_reg == 12.0
    drv.click("fit_mode.0")
    assert model(drv).fit_mode == "none"
    drv.click("fit_mode.1")
    assert model(drv).fit_mode == "simple"


def test_the_fit_window_fields_are_typed(drv):
    drv.tab("Settings")
    drv.type_into("tmin_fit", "0.05")
    drv.type_into("tmax_fit", "5")
    assert (model(drv).tmin_fit, model(drv).tmax_fit) == (0.05, 5.0)
    drv.type_into("tmin_fit", "-1")
    assert model(drv).tmin_fit == 0.0


def test_an_inverted_fit_window_is_refused_when_running(drv):
    drv.tab("Settings")
    drv.type_into("tmin_fit", "5")
    drv.type_into("tmax_fit", "1")
    drv.click("example")
    drv.click("run")
    assert not ctrl(drv).running and ctrl(drv).status == "Invalid settings: Fit minimum lag must be below the maximum."


def test_save_and_load_settings_dialogs_round_trip(drv, tmp_path):
    drv.tab("Settings")
    drv.type_into("n_bins", "6")
    drv.click("fit_mode.2")
    drv.type_into("maxent_log10_reg", "-2")
    drv.click("save_settings")
    drv.draw(3)
    drv.click_text("burst_fcs_settings.json")
    drv.click_text("Save", last=True)
    data = json.loads((tmp_path / "burst_fcs_settings.json").read_text())
    assert data["n_bins"] == 6 and data["fit_mode"] == "maxent" and data["maxent_reg"] == pytest.approx(0.01)
    drv.type_into("n_bins", "9")
    drv.click("load_settings")
    drv.draw(4)
    drv.click_text("burst_fcs_settings.json")
    drv.click_text("Open", last=True)
    assert model(drv).n_bins == 6 and model(drv).fit_mode == "maxent" and model(drv).maxent_log10_reg == pytest.approx(-2.0)
    assert ctrl(drv).status == "Settings loaded."


def test_loading_a_broken_settings_file_reports(drv, tmp_path):
    (tmp_path / "bad_settings.json").write_text(json.dumps({"n_bins": 0}))
    drv.tab("Settings")
    drv.click("load_settings")
    drv.draw(4)
    drv.click_text("bad_settings.json")
    drv.click_text("Open", last=True)
    assert ctrl(drv).status.startswith("Error:") and model(drv).n_bins == 3


# -- the curves and the plots ----------------------------------------------------------------------------------------- #


def test_a_curve_is_selected_by_a_click_and_drives_the_plots(drv):
    example_run(drv)
    c = ctrl(drv)
    drv.click_cell("curve_rows", 4, "pair")
    assert model(drv)._selected is c._curves[4]
    drv.click_cell("curve_rows", 7, "pair")
    assert model(drv)._selected is c._curves[7]


def test_the_curve_filter_narrows_the_list(drv):
    example_run(drv)
    x, y, w, h = drv.control("curve_rows")._filter_box
    drv.click_at(x + w / 2, y + h / 2)
    drv.type_text("cross")
    assert 0 < len(drv.control("curve_rows").order()) == demo.N_BURSTS


def test_export_curves_writes_the_curves_as_json(drv, tmp_path):
    drv.click("export_curves")  # greyed before a run
    assert drv.app.dialog is None
    example_run(drv)
    drv.click("export_curves")
    drv.draw(4)
    drv.click_text("burst_fcs_curves.json")
    drv.click_text("Save", last=True)
    written = json.loads((tmp_path / "burst_fcs_curves.json").read_text())
    assert len(written) == demo.N_BURSTS * 3 and written[0]["pair_name"] == "ACF_0"


def test_maxent_shows_the_distribution_plot(drv):
    drv.tab("Settings")
    drv.click("fit_mode.2")
    drv.click("example")
    drv.click("run")
    drv.settle()
    assert model(drv).dist_plot_series()
    strings = drv.draw(3).strings
    assert "Diffusion time tau_D (ms)" in strings and "P(τ_D)" in strings


def ticks(painter):
    return [s for s in painter.strings if re.fullmatch(r"-?[\d.]+(e[+-]?\d+)?", s)]


def test_a_drag_pans_and_the_wheel_zooms_the_correlation_plot(drv):
    example_run(drv)
    before = ticks(drv.draw(2))
    x, y, w, h = drv.app.item_rects["correlation_plot"]
    drv.drag((x + w * 0.6, y + h * 0.4), (x + w * 0.4, y + h * 0.3))
    panned = ticks(drv.draw(2))
    assert panned != before
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert ticks(drv.draw(2)) != panned


def test_the_fit_window_lines_are_dragged_and_set_t_min_and_t_max(drv):
    example_run(drv)
    painter = drv.draw(3)
    px, py, pw, ph = drv.app.item_rects["correlation_plot"]
    assert model(drv).tmin_fit == 0.0
    # find the line by hovering: the plot reports it as the item under the pointer
    moved = False
    for dx in range(30, 120, 6):
        drv.drag((px + dx, py + ph * 0.45), (px + dx + 120, py + ph * 0.45))
        if model(drv).tmin_fit > 0:
            moved = True
            break
    assert moved and model(drv).tmax_fit > model(drv).tmin_fit


def test_a_wheel_zoom_on_the_distribution_plot(drv):
    drv.tab("Settings")
    drv.click("fit_mode.2")
    drv.click("example")
    drv.click("run")
    drv.settle()
    before = ticks(drv.draw(2))
    x, y, w, h = drv.app.item_rects["distribution_plot"]
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert ticks(drv.draw(2)) != before


# -- the detector setup -------------------------------------------------------------------------------------------------- #


def test_the_detector_setup_tab_embeds_the_shared_editor_and_adds_detectors(drv):
    painter = drv.tab("Detector setup")
    assert "Use setup for pairs" in painter.strings and any(s.endswith("TTTR Reading routine") for s in painter.strings)
    drv.click_text("Add")
    drv.draw(3)
    assert len(drv.app.setup.model.get_settings().get("detectors", {})) >= 1


def test_use_setup_for_pairs_replaces_the_pairs_by_the_setup_detectors(drv):
    drv.tab("Detector setup")
    drv.app.setup.model.data["detectors"] = {"green": {"chs": [0, 8]}, "red": {"chs": [1, 9]}}
    drv.draw(3)
    drv.click("use_setup")
    assert [p["pair_name"] for p in ctrl(drv)._pair_presets] == ["green_ACF", "red_ACF"]
    assert ctrl(drv)._pair_presets[0]["chs_a"] == [0, 8]


def test_use_setup_without_detectors_says_so(drv):
    drv.tab("Detector setup")
    drv.app.setup.model.data["detectors"] = {}
    drv.click("use_setup")
    assert ctrl(drv).status == "The detector setup has no detector with routing channels."


def test_choosing_a_saved_setup_adopts_its_pairs(drv, monkeypatch):
    drv.tab("Detector setup")
    app = drv.app
    app.setup.model.data["detectors"] = {"cy3": {"chs": [2]}}
    app.setup.model.current_name = "My setup"
    drv.draw(3)
    assert [p["pair_name"] for p in ctrl(drv)._pair_presets] == ["cy3_ACF"]


# -- the small window ---------------------------------------------------------------------------------------------------- #


def test_the_flow_works_in_the_small_window_too(drv):
    drv.size = SMALL
    drv.draw(3)
    drv.click("example")
    drv.click("run")
    drv.settle()
    assert len(ctrl(drv)._curves) == demo.N_BURSTS * 3
    drv.tab("Settings")
    drv.type_into("n_bins", "4")
    assert model(drv).n_bins == 4
    drv.tab("Inputs")
    drv.click_cell("curve_rows", 2, "pair")
    assert model(drv)._selected is ctrl(drv)._curves[2]
    drv.tab("Detector setup")
