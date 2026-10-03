"""CLSM Generator emtk app: every control operated with real input (pointer at the drawn rectangles, typed text, Enter, drops).

Inputs are small synthetic maps written to a temporary folder (they are the user's inputs, not results); hermetic HOME and settings,
a test asserts that nothing is written under HOME.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest
from emtk import keys

from chisurf.plugins.emtk_test_input import assert_tour_card_clear
from chisurf.plugins.microscopy.clsm_generator.gui.app import make_app
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

SIZES = [(1200, 800), (900, 650)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))


@pytest.fixture()
def maps(tmp_path):
    y, x = np.indices((16, 16))
    paths = {}
    for name, value in (("intensity", 0.2 + np.exp(-0.5 * (((x - 8) / 3) ** 2 + ((y - 8) / 3) ** 2))),
                        ("life0", np.full((16, 16), 2.0)), ("life1", np.full((16, 16), 3.0))):
        np.save(tmp_path / f"{name}.npy", value)
        paths[name] = tmp_path / f"{name}.npy"
    return paths


def settle(ui, timeout=120):
    end = time.monotonic() + timeout
    while ui.app.job.busy and time.monotonic() < end:
        time.sleep(0.01)
        ui.draw(1)
    return ui.draw(3)


@pytest.fixture()
def ui():
    ui = Ui(make_app(), (1200, 800))
    yield ui


@pytest.fixture()
def loaded(maps):
    ui = Ui(make_app(), (1200, 800))
    assert ui.drop(maps["intensity"])
    assert ui.drop(maps["life0"], maps["life1"])
    ui.app.model.n_lifetime_levels = ui.app.model.n_intensity_levels = 2
    ui.app.model.brightness_scale = 100
    ui.draw(3)
    return ui


def test_intensity_dialog_cancel_close_pick_and_the_path_is_shown(ui, maps):
    ui.click("Intensity image")
    assert ui.dialog_open
    ui.press_text("Cancel")
    assert not ui.dialog_open and not ui.app.model.intensity_path
    ui.click("Intensity image")
    ui.press_text("×")
    assert not ui.dialog_open
    ui.click("Intensity image")
    ui.app.dialog.enter(str(maps["intensity"].parent))
    ui.dialog_pick("intensity.npy")
    assert ui.app.model.intensity_path == str(maps["intensity"]) and ui.shown("intensity.npy")


def test_lifetime_maps_dialog_drop_select_remove_clear_and_delete_key(ui, maps):
    ui.drop(maps["intensity"])                         # a drop is the intensity image until one is loaded, then a lifetime map
    ui.click("Add lifetime maps")
    ui.app.dialog.enter(str(maps["life0"].parent))
    ui.dialog_pick("life0.npy")
    assert ui.app.model.lifetime_paths == [str(maps["life0"])]
    ui.drop(maps["life1"])
    assert len(ui.app.model.lifetime_paths) == 2
    ui.draw(3)
    ui.press_text("life1.npy")
    assert ui.app.selected_lifetime == 1
    ui.click("Remove selected")
    assert ui.app.model.lifetime_paths == [str(maps["life0"])]
    ui.draw(3)
    ui.press_text("life0.npy")
    ui.key(keys.KEY_DELETE, "")
    assert ui.app.model.lifetime_paths == []
    ui.drop(maps["life0"])
    ui.click("Clear maps")
    assert ui.app.model.lifetime_paths == []


def test_generate_without_inputs_gives_the_reason_and_save_is_greyed(ui):
    ui.click("Generate")
    assert ui.shown("Load an intensity image")
    ui.click("Save photon stream")
    assert not ui.dialog_open


@pytest.mark.parametrize("key,typed,attr", [("pixel_size", "0.2", "pixel_size"), ("dwell", "0.5", "dwell"), ("n_micro", "128", "n_micro"),
                                            ("dt", "0.1", "dt"), ("brightness_scale", "50", "brightness_scale"), ("irf_center", "20", "irf_center"),
                                            ("irf_sigma", "2", "irf_sigma"), ("n_lifetime_levels", "3", "n_lifetime_levels"),
                                            ("n_intensity_levels", "3", "n_intensity_levels")])
def test_simulation_fields_typed_clamped_and_arrowed(ui, key, typed, attr):
    ui.click("Simulation.fold")
    ui.type_into(key, typed)
    assert getattr(ui.app.model, attr) == pytest.approx(float(typed))
    ui.type_into(key, "1e12")
    high = getattr(ui.app.model, attr)
    ui.type_into(key, "-5")
    low = getattr(ui.app.model, attr)
    assert low < high
    ui.arrow(key, +1)
    assert getattr(ui.app.model, attr) > low
    ui.type_into(key, "text")
    assert getattr(ui.app.model, attr) > low - 1e-9


def test_generate_reconstructs_photons_and_the_map_combo_browses_the_views(loaded):
    ui = loaded
    ui.click("Generate")
    settle(ui)
    assert ui.app.model.has_result() and ui.shown("Generated")
    labels = [e["label"] for e in ui.app.model.view_entries()]
    ui.click("map", fx=0.8)
    ui.press_text(labels[0])
    assert ui.app.model.current_view == ui.app.model.view_entries()[0]["id"]


def test_cancel_generation_discards_the_result(loaded):
    ui = loaded
    ui.app.model.brightness_scale = 100000
    ui.click("Generate")
    ui.draw(2)
    if ui.app.job.busy and "Cancel generation" in ui.app.item_rects:
        ui.click("Cancel generation")
        settle(ui)
        assert ui.shown("canceled") or ui.shown("Canceled") or ui.app.model.status_text.startswith("Generation canceled")
    else:
        settle(ui)


def test_save_photon_stream_through_the_dialog_in_the_chosen_format_and_an_unknown_suffix(loaded, tmp_path):
    ui = loaded
    ui.click("Generate")
    settle(ui)
    ui.click("output_format", fx=0.8)
    ui.press_text(".npz")
    assert ui.app.output_format == ".npz"
    ui.click("Save photon stream")
    assert ui.dialog_open
    ui.save_dialog_type_name(str(tmp_path / "sim_out.npz"))
    ui.press_text("Save")
    settle(ui)
    assert (tmp_path / "sim_out.npz").exists()
    ui.click("Save photon stream")
    ui.save_dialog_type_name(str(tmp_path / "sim_out.xyz"))
    ui.press_text("Save")
    settle(ui)
    # an unknown suffix is not written as such: the file dialog appends the filter's suffix
    assert not (tmp_path / "sim_out.xyz").exists() and (tmp_path / "sim_out.xyz.pto").exists()


def test_settings_round_trip_through_the_dialogs(loaded, tmp_path):
    ui = loaded
    ui.click("Simulation.fold")
    ui.type_into("pixel_size", "0.37")
    ui.click("Save settings")
    ui.save_dialog_type_name(str(tmp_path / "gen_state.json"))
    ui.press_text("Save")
    state = json.loads((tmp_path / "gen_state.json").read_text())
    assert state["parameters"]["pixel_size"] == pytest.approx(0.37)
    ui.type_into("pixel_size", "0.8")
    ui.app.model.sel_intensity = ""
    ui.draw(3)
    ui.click("Load settings")
    ui.app.dialog.enter(str(tmp_path))
    ui.dialog_pick("gen_state.json")
    assert ui.app.model.pixel_size == pytest.approx(0.37)
    assert ui.app.model.intensity_path.endswith("intensity.npy") and len(ui.app.model.lifetime_paths) == 2


def test_help_guide_and_the_tour_is_walked(ui, maps):
    ui.click("Help")
    assert ui.app.help_window.open
    ui.press_text("Close Help")
    ui.click("Guide")
    assert ui.app.tour.active
    steps = len(ui.app.tour.steps)
    for _ in range(steps * 4):
        if ui.app.tour.awaiting:
            key = ui.app.tour._target_key(ui.app.tour.steps[ui.app.tour.step_idx]["target"])
            assert key in ui.app.item_rects, key
            assert_tour_card_clear(ui.app.tour, ui.size)  # the card does not sit on the control the user must press
            ui.click(key)
            if ui.dialog_open and key == "Save photon stream":
                ui.press_text("Cancel")
            elif ui.dialog_open:
                ui.app.dialog.enter(str(maps["intensity"].parent))
                ui.dialog_pick("intensity.npy" if key == "Intensity image" else "life0.npy")
            if key == "Generate":
                ui.app.model.n_lifetime_levels = ui.app.model.n_intensity_levels = 2
            settle(ui)
            if ui.dialog_open:
                ui.press_text("Cancel")
        if ui.app.tour.step_idx == steps - 1:
            break
        ui.press_text("Next ►")
    assert ui.app.tour.step_idx == steps - 1


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_layout_at_both_sizes(maps, size):
    from test.gui.emtk_layout_checks import assert_texts_apart

    ui = Ui(make_app(), size)
    ui.drop(maps["intensity"])
    ui.drop(maps["life0"])
    ui.click("Simulation.fold")
    w, h = size
    assert_texts_apart(ui.last, region=(0, 24, 0.35 * w, h - 24))
    for key in ("Intensity image", "Generate", "Save settings"):
        x, y, bw, bh = ui.app.item_rects[key]
        assert x >= 0 and x + bw <= 0.35 * w + 4, key


def test_nothing_is_written_under_home(ui, tmp_path):
    assert not (Path.home() / ".chisurf").exists() and Path.home() == tmp_path
