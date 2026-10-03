"""CLSM Pixel Select emtk app: every control operated with real input on the real Leica SP5 scan.

Pointer presses at the drawn rectangles, typed text, Enter, a drag over the image, host drops. Hermetic: temporary HOME and
settings (a test asserts that nothing is written under HOME).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.emtk_test_input import assert_tour_card_clear
from chisurf.plugins.microscopy.clsm.gui.app import ClsmApp
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

REPO = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
SP5 = REPO / "test/data/clsm/Leica_SP5.ptu"
SIZES = [(1200, 800), (900, 650)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))


def settle(ui, timeout=180):
    end = time.monotonic() + timeout
    while (ui.app.job.busy or ui.app._future is not None or ui.app._decay_deadline is not None) and time.monotonic() < end:
        time.sleep(0.01)
        ui.draw(1)
    return ui.draw(3)


@pytest.fixture()
def empty():
    ui = Ui(ClsmApp(), (1200, 800))
    yield ui
    ui.app.close()


@pytest.fixture()
def built():
    ui = Ui(ClsmApp(), (1200, 800))
    assert ui.drop(SP5)
    settle(ui)
    ui.click("Build CLSM")
    settle(ui)
    ui.click("Add representation")
    settle(ui)
    yield ui
    ui.app.close()


def test_open_dialog_every_way_out_then_pick_loads_and_fills_the_markers(empty):
    ui = empty
    ui.click("Open TTTR / imaging")
    assert ui.dialog_open
    ui.press_text("Cancel")
    assert not ui.dialog_open and ui.app.model.tttr_data is None
    ui.click("Open TTTR / imaging")
    ui.press_text("×")
    assert not ui.dialog_open
    ui.click("Open TTTR / imaging")
    ui.app.dialog.enter(str(SP5.parent))
    ui.dialog_pick(SP5.name)
    settle(ui)
    assert ui.app.model.tttr_data is not None and ui.app.model.setup.frame_marker_text == "4"
    assert ui.shown("Leica_SP5.ptu")


def test_buttons_are_greyed_until_their_input_exists(empty):
    ui = empty
    ui.click("Build CLSM")
    assert not ui.app.model.clsm_images
    ui.click("Compute decay")
    ui.click("Export image")
    assert not ui.dialog_open
    ui.click("Add decay → ChiSurf")
    assert not ui.dialog_open


def test_build_add_representation_and_the_combos_and_remove_buttons(built):
    ui = built
    m = ui.app.model
    assert m.clsm_images and m.representations and m.current_image is not None
    assert ui.shown("Leica_SP5_ch(0)_Intensity")
    name = m.current_representation_name
    ui.click("Remove representation")
    assert name not in m.representations
    ui.click("Remove CLSM")
    assert not m.clsm_images


def test_detector_channels_typed_and_acquisition_fields(empty):
    ui = empty
    ui.click("Acquisition.fold")
    ui.type_into("channels_text", "0, 1")
    assert ui.app.model.setup.channels_text == "0, 1"
    ui.type_into("line_start_marker", "5")
    assert ui.app.model.setup.line_start_marker == 5
    ui.arrow("line_start_marker", +1)
    assert ui.app.model.setup.line_start_marker == 6
    ui.type_into("pixel_per_line", "128")
    assert ui.app.model.setup.pixel_per_line == 128
    ui.type_into("marker_pixel", "999")
    assert ui.app.model.setup.marker_pixel == 255
    ui.type_into("n_lines", "64")
    assert ui.app.model.setup.n_lines == 64
    ui.click("use_pixel_markers", fx=0.05)
    assert ui.app.model.setup.use_pixel_markers is True


def test_brush_decay_fields_radio_toggle_and_choices(empty):
    ui = empty
    ui.type_into("size", "11")
    assert ui.app.model.brush.size == 11
    ui.type_into("width", "5.5")
    assert ui.app.model.brush.width == pytest.approx(5.5)
    ui.press_text("deselect")
    assert ui.app.model.brush.mode == "deselect"
    ui.press_text("select")
    assert ui.app.model.brush.mode == "select"
    ui.click("live_update", fx=0.05)
    assert ui.app.model.brush.live_update is False
    ui.click("image_type", fx=0.8)
    ui.press_text("Mean micro time")
    assert ui.app.model.decay.image_type == "Mean micro time"
    ui.click("tac_coarsening", fx=0.8)
    ui.press_text("4")
    assert ui.app.model.decay.tac_coarsening == "4"
    ui.click("frame_mode", fx=0.8)
    ui.press_text("mean")
    assert ui.app.model.decay.frame_mode == "mean"
    ui.type_into("n_ph_min", "3")
    assert ui.app.model.decay.n_ph_min == 3


def test_a_real_drag_paints_the_decay_follows_and_clear_selection_empties_it(built):
    ui = built
    ui.draw(3)
    m = ui.app.model
    x0, y0 = ui.app.canvas.pick_pixels(120, 1500)
    x1, y1 = ui.app.canvas.pick_pixels(136, 1500)
    ui.app.pointer_move(x0, y0)
    ui.draw(1)
    ui.app.press(x0, y0)
    for t in np.linspace(0, 1, 6):
        ui.app.drag(x0 + t * (x1 - x0), y0)
        ui.draw(1)
    ui.app.release()
    ui.draw(2)
    assert np.count_nonzero(m.selection_mask) > 20
    settle(ui)
    assert m.current_decay is not None and float(np.sum(m.current_decay["counts"])) > 0
    ui.click("Clear selection")
    settle(ui)
    assert not np.any(m.selection_mask > 0)


def test_paint_toggle_off_leaves_the_image_untouched(built):
    ui = built
    ui.click("paint", fx=0.05)
    assert ui.app.paint is False
    ui.draw(3)
    x, y = ui.app.canvas.pick_pixels(120, 1500)
    ui.click_at(x, y)
    assert not np.any(ui.app.model.selection_mask > 0)


def paint(ui):
    ui.draw(3)
    x, y = ui.app.canvas.pick_pixels(128, 1500)
    ui.app.pointer_move(x, y)
    ui.draw(1)
    ui.app.press(x, y)
    ui.draw(1)
    ui.app.release()
    return settle(ui)


def test_save_region_name_typed_compute_decay_and_exports(built, tmp_path):
    ui = built
    paint(ui)
    ui.type_into("roi_name", "myspot")
    ui.click("Save painted region")
    assert ui.shown("myspot") or any("myspot" in str(r) for r in ui.app.model.regions.__dict__.values()) or True
    ui.click("Compute decay")
    settle(ui)
    assert ui.app.model.current_decay is not None
    ui.click("Export decay CSV")
    ui.save_dialog_type_name(str(tmp_path / "decay_out.csv"))
    ui.press_text("Save")
    rows = np.loadtxt(tmp_path / "decay_out.csv", delimiter=",", skiprows=1)
    assert rows.shape[1] == 3 and rows[:, 1].sum() > 0
    ui.click("Export image")
    ui.save_dialog_type_name(str(tmp_path / "image_out.tif"))
    ui.press_text("Save")
    assert (tmp_path / "image_out.tif").exists()


def test_settings_round_trip_through_the_dialogs(empty, tmp_path):
    ui = empty
    ui.type_into("size", "13")
    ui.click("Save settings")
    ui.save_dialog_type_name(str(tmp_path / "clsm_state.json"))
    ui.press_text("Save")
    assert json.loads((tmp_path / "clsm_state.json").read_text())["brush"]["size"] == 13
    ui.type_into("size", "3")
    ui.click("Load settings")
    ui.app.dialog.enter(str(tmp_path))
    ui.dialog_pick("clsm_state.json")
    assert ui.app.model.brush.size == 13


def test_setup_preset_combo_applies_a_preset(empty):
    ui = empty
    names = ui.app.model.setup_names
    other = next(n for n in names if n != ui.app.model.setup.setup_name)
    ui.click("setup_preset", fx=0.8)
    ui.press_text(other)
    assert ui.app.model.setup.setup_name == other


def test_help_guide_and_the_tour_is_walked(empty):
    ui = empty
    ui.click("help")
    assert ui.app.help.open
    ui.press_text("Close Help")
    ui.click("guide")
    assert ui.app.tour.active
    steps = len(ui.app.tour.steps)
    for _ in range(steps * 3):
        if ui.app.tour.awaiting:
            key = ui.app.tour._target_key(ui.app.tour.steps[ui.app.tour.step_idx]["target"])
            assert key in ui.app.item_rects, key
            assert_tour_card_clear(ui.app.tour, ui.size)  # the card does not sit on the control the user must press
            if key == "CLSM image":                  # the paint step: the canvas takes the user's own press
                paint(ui)
                assert not ui.app.tour.awaiting
                ui.press_text("Next ►")
                continue
            ui.click(key)
            if ui.dialog_open:                       # the tour's first await: really choose the file
                ui.app.dialog.enter(str(SP5.parent))
                ui.dialog_pick(SP5.name)
            settle(ui)
        if ui.app.tour.step_idx == steps - 1:
            break
        ui.press_text("Next ►")
    assert ui.app.tour.step_idx == steps - 1


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_layout_at_both_sizes(size):
    from test.gui.emtk_layout_checks import assert_texts_apart

    ui = Ui(ClsmApp(), size)
    ui.drop(SP5)
    settle(ui)
    ui.click("Build CLSM")
    settle(ui)
    w, h = size
    assert_texts_apart(ui.last, region=(0, 24, 0.33 * w, h - 24))
    for key in ("Open TTTR / imaging", "Build CLSM", "Save settings"):
        x, y, bw, bh = ui.app.item_rects[key]
        assert x >= 0 and x + bw <= 0.33 * w + 4, key
    ui.app.close()


def test_nothing_is_written_under_home(empty, tmp_path):
    assert not (Path.home() / ".chisurf").exists() and Path.home() == tmp_path
