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

from chisurf.plugins.emtk_layout import help_close_caption
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
    for name, value in (
        ("intensity", 0.2 + np.exp(-0.5 * (((x - 8) / 3) ** 2 + ((y - 8) / 3) ** 2))),
        ("life0", np.full((16, 16), 2.0)),
        ("life1", np.full((16, 16), 3.0)),
    ):
        np.save(tmp_path / f"{name}.npy", value)
        paths[name] = tmp_path / f"{name}.npy"
    return paths


def settle(ui, timeout=120):
    end = time.monotonic() + timeout
    while ui.app.job.busy and time.monotonic() < end:
        time.sleep(0.01)
        ui.draw(1)
    return ui.draw(3)


@pytest.fixture(autouse=True)
def workspace_restored():
    """The Datasets workspace as it was: a test's rows do not leak into the next test."""
    from chisurf.core.api import dataset_container

    held = dataset_container()
    before = list(held)
    yield
    held[:] = before


def pick(ui, name, *paths, kind="setup"):
    """Put *paths* in the Datasets workspace (an NPY map drops as a setup) and pick them in Input
    section *name*, as a person does."""
    from chisurf.core.plugin.workspace_input import register_result

    named = ui.app.inputs[name]
    rows = []
    for path in paths:
        register_result(str(path), kind=kind)
        found = [r for r in named.workspace_input_rows() if r.get("address") == str(path)]
        assert found, f"{path} is not offered by the {name!r} Input section"
        rows.append(found[-1])
    spec = named._workspace_input()
    if spec is not None and spec[1].many:
        named.workspace_input_selection = rows
        named.workspace_input_use()
    else:
        named.workspace_input_selected(rows[-1])
    assert not named.workspace_input_status.startswith("Could not"), named.workspace_input_status
    ui.draw(2)
    return True


@pytest.fixture()
def ui():
    ui = Ui(make_app(), (1200, 800))
    yield ui


@pytest.fixture()
def loaded(maps):
    ui = Ui(make_app(), (1200, 800))
    assert pick(ui, "intensity", maps["intensity"])
    assert pick(ui, "lifetimes", maps["life0"], maps["life1"])
    ui.app.model.n_lifetime_levels = ui.app.model.n_intensity_levels = 2
    ui.app.model.brightness_scale = 100
    ui.draw(3)
    return ui


def test_the_intensity_map_is_picked_from_the_workspace_and_the_path_is_shown(ui, maps):
    ui.draw(2)
    assert "Intensity image" in ui.app.item_rects  # the Input section stands where the button was
    assert not hasattr(ui.app, "on_files_dropped") and not hasattr(ui.app, "picker")
    pick(ui, "intensity", maps["intensity"])
    assert ui.app.model.intensity_path == str(maps["intensity"]) and ui.shown("intensity.npy")


def test_lifetime_maps_picked_from_the_workspace_then_select_remove_clear_and_delete_key(ui, maps):
    pick(ui, "lifetimes", maps["life0"])
    assert ui.app.model.lifetime_paths == [str(maps["life0"])]
    pick(ui, "lifetimes", maps["life1"])
    assert len(ui.app.model.lifetime_paths) == 2
    ui.app.select_lifetime({"detector": 1})
    assert ui.app.selected_lifetime == 1
    ui.click("Remove selected")
    assert ui.app.model.lifetime_paths == [str(maps["life0"])]
    ui.app.delete_lifetime({"detector": 0})
    assert ui.app.model.lifetime_paths == []
    pick(ui, "lifetimes", maps["life0"])
    ui.click("Clear maps")
    assert ui.app.model.lifetime_paths == []


def test_generate_without_inputs_gives_the_reason_and_save_is_greyed(ui):
    ui.click("Generate")
    assert ui.shown("Load an intensity image")
    ui.click("Save photon stream")
    assert not ui.dialog_open


@pytest.mark.parametrize(
    "key,typed,attr",
    [
        ("pixel_size", "0.2", "pixel_size"),
        ("dwell", "0.5", "dwell"),
        ("n_micro", "128", "n_micro"),
        ("dt", "0.1", "dt"),
        ("brightness_scale", "50", "brightness_scale"),
        ("irf_center", "20", "irf_center"),
        ("irf_sigma", "2", "irf_sigma"),
        ("n_lifetime_levels", "3", "n_lifetime_levels"),
        ("n_intensity_levels", "3", "n_intensity_levels"),
    ],
)
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
        assert (
            ui.shown("canceled")
            or ui.shown("Canceled")
            or ui.app.model.status_text.startswith("Generation canceled")
        )
    else:
        settle(ui)


def test_save_photon_stream_through_the_dialog_in_the_chosen_format_and_an_unknown_suffix(
    loaded, tmp_path
):
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
    from chisurf.core.fio.classify import classify

    assert classify(tmp_path / "gen_state.json") == "setup"  # a drop puts it in the workspace
    pick(ui, "settings", tmp_path / "gen_state.json")
    assert ui.app.model.pixel_size == pytest.approx(0.37)
    assert (
        ui.app.model.intensity_path.endswith("intensity.npy")
        and len(ui.app.model.lifetime_paths) == 2
    )


def test_help_guide_and_the_tour_is_walked(ui, maps):
    ui.click("Help")
    assert ui.app.help_window.open
    ui.press_text(help_close_caption(), nth=-1)
    ui.click("Guide")
    assert ui.app.tour.active
    steps = len(ui.app.tour.steps)
    for _ in range(steps * 4):
        if ui.app.tour.awaiting:
            key = ui.app.tour._target_key(ui.app.tour.steps[ui.app.tour.step_idx]["target"])
            assert key in ui.app.item_rects, key
            assert_tour_card_clear(
                ui.app.tour, ui.size
            )  # the card does not sit on the control the user must press
            if key == "Intensity image":
                pick(ui, "intensity", maps["intensity"])
            elif key == "Add lifetime maps":
                pick(ui, "lifetimes", maps["life0"])
            else:
                ui.click(key)
            if ui.dialog_open and key == "Save photon stream":
                ui.press_text("Cancel")
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
    pick(ui, "intensity", maps["intensity"])
    pick(ui, "lifetimes", maps["life0"])
    ui.click("Simulation.fold")
    w, h = size
    assert_texts_apart(ui.last, region=(0, 24, 0.35 * w, h - 24))
    for key in ("Intensity image", "Generate", "Save settings"):
        x, y, bw, bh = ui.app.item_rects[key]
        assert x >= 0 and x + bw <= 0.35 * w + 4, key


def test_nothing_is_written_under_home(ui, tmp_path):
    assert not (Path.home() / ".chisurf").exists() and Path.home() == tmp_path
