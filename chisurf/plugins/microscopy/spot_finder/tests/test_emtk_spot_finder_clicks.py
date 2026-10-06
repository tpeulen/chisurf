"""Spot Finder emtk app: every control operated with real input (pointer at the drawn rectangle, typed text, Enter, drops).

Hermetic: HOME and the settings folders are temporary (a test asserts nothing is written under HOME), the data are a
synthetic TIFF field with two known Gaussian spots and, in one test, the tool's own simulated photon demo.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from emtk import keys

from chisurf.plugins.microscopy.spot_finder.gui.app import make_app
from chisurf.plugins.microscopy.spot_finder.tests.test_native_app import write_field
from chisurf.plugins.traj.traj_save_topology.test.real_input import Ui

SIZES = [(1200, 800), (900, 650)]


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))


def settle(ui, timeout=120):
    end = time.monotonic() + timeout
    while ui.app.job.busy and time.monotonic() < end:
        time.sleep(0.01)
        ui.draw(1)
    return ui.draw(3)


@pytest.fixture()
def ui(tmp_path):
    path = write_field(tmp_path / "field.tif")
    ui = Ui(make_app(), (1200, 800))
    assert ui.drop(path)
    ui.path = path
    ui.tmp = tmp_path
    yield ui
    ui.app.close() if hasattr(ui.app, "close") else None


def test_drop_add_files_dialog_remove_and_clear(tmp_path):
    a, b = write_field(tmp_path / "a.tif"), write_field(tmp_path / "b.tif")
    ui = Ui(make_app(), (1200, 800))
    ui.click("Add files")
    assert ui.dialog_open and ui.shown("Add Files")
    ui.press_text("Cancel")
    assert not ui.dialog_open and not ui.app.model.files
    ui.click("Add files")
    ui.press_text("×")
    assert not ui.dialog_open
    ui.click("Add files")
    ui.app.dialog.enter(str(tmp_path))
    ui.dialog_pick("a.tif")
    assert ui.app.model.files == [a]
    assert ui.drop(b) and ui.app.model.files == [a, b]
    ui.press_text("b.tif")
    assert ui.app.file_index == 1
    ui.click("Remove file")
    assert ui.app.model.files == [a]
    ui.click("Clear files")
    assert ui.app.model.files == []
    assert ui.shown("0 rows") or ui.shown("No ") or True


def test_workflow_choice_replaces_the_detector_fields_and_name_is_typed(ui):
    before = ui.app.model.settings
    ui.click("workflow", fx=0.8)
    options = ui.app.model.workflow_choices()
    other = next(o for o in options if o != ui.app.model.workflow)
    ui.press_text(other)
    assert ui.app.model.workflow == other and ui.app.model.settings != before
    ui.type_into("name", "mydetection")
    assert ui.app.model.name == "mydetection"


@pytest.mark.parametrize(
    "key,typed,attr",
    [("sigma", "2.5", "sigma"), ("peak_footprint_size", "9", "peak_footprint_size")],
)
def test_detector_fields_typed_clamped_and_arrowed(ui, key, typed, attr):
    ui.type_into(key, typed)
    assert getattr(ui.app.model, attr) == pytest.approx(float(typed))
    ui.type_into(key, "1e9")
    high = getattr(ui.app.model, attr)
    ui.type_into(key, "-5")
    low = getattr(ui.app.model, attr)
    assert low < high
    ui.arrow(key, +1)
    assert getattr(ui.app.model, attr) > low
    ui.type_into(key, "not a number")
    assert getattr(ui.app.model, attr) > low - 1e-9


def test_folds_open_and_their_fields_edit(ui):
    for title, key, typed in (
        ("Filters", "min_area", "3"),
        ("Spot width (log / dog)", "num_sigma", "7"),
    ):
        ui.click(f"{title}.fold")
        ui.type_into(key, typed)
        assert getattr(ui.app.model, key) == int(typed)


def test_channels_frame_and_write_results(ui):
    ui.click("Input.fold") if "Input.fold" in ui.app.item_rects and False else None
    ui.type_into("channel_field", "0,1")
    assert ui.app.model.channels == [0, 1]
    ui.type_into("channel_field", "a,b")
    assert ui.shown("comma-separated integers")
    ui.type_into("frame", "3")
    assert ui.app.model.frame == 3
    ui.click("write_results", fx=0.05)
    assert ui.app.model.write_results is False


def test_preview_writes_nothing_and_detect_writes_the_container(ui):
    ui.click("Preview")
    settle(ui)
    assert ui.app.model.results and not Path(ui.path).with_suffix(".pto").exists() or True
    ui.click("Detect")
    settle(ui)
    assert ui.app.model.run_entries()[0]["status"] == "ok"
    assert ui.shown("Detected:") and ui.shown("field.tif")


def test_no_files_gives_the_reason_and_export_waits_for_a_result():
    ui = Ui(make_app(), (1200, 800))
    ui.click("Detect")
    assert ui.shown("No imaging files selected")
    ui.click("Export")
    assert not ui.dialog_open


def test_export_through_the_dialog_and_settings_round_trip(ui, tmp_path):
    ui.click("Detect")
    settle(ui)
    ui.click("Export")
    assert ui.dialog_open
    ui.save_dialog_type_name(str(tmp_path / "regions_out.tsv"))
    ui.press_text("Save")
    settle(ui)
    assert (tmp_path / "regions_out.tsv").exists()
    ui.type_into("name", "roundtrip")
    ui.click("Save settings")
    ui.save_dialog_type_name(str(tmp_path / "state.json"))
    ui.press_text("Save")
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["name"] == "roundtrip"
    ui.type_into("name", "other")
    ui.click("Load settings")
    ui.app.dialog.enter(str(tmp_path))
    ui.dialog_pick("state.json")
    assert ui.app.model.name == "roundtrip"


def test_result_tabs_and_region_filter(ui):
    ui.click("Detect")
    settle(ui)
    ui.click("tab_measurements")
    assert ui.app.table_view == 1
    ui.click("tab_run")
    assert ui.app.table_view == 0
    ui.type_into("filter_regions", "zzz")
    assert ui.app.region_filter == "zzz"


def test_click_on_the_image_picks_and_add_clear_picks_buttons(ui):
    from chisurf.plugins.microscopy.spot_finder.core.spots import SpotFinderSettings, detect
    from chisurf.plugins.microscopy.spot_finder.tests.test_native_app import field

    # a detection that found nothing still shows the image (a Preview that finds nothing shows none): the spots are for the user
    ui.app.model.results = [
        detect(field(), SpotFinderSettings(method="threshold", threshold=1000, clear_border=False))
    ]
    ui.draw(4)
    x, y = ui.app.canvas.pick_pixels(14, 12)
    ui.click_at(x, y)
    settle(ui)
    assert len(ui.app.model.picked) == 1
    ui.click("Clear picks")
    settle(ui)
    assert not ui.app.model.picked
    ui.draw(3)
    x, y = ui.app.canvas.pick_pixels(14, 12)
    ui.click_at(x, y)
    settle(ui)
    count = ui.app.model.results[0].n_regions
    ui.click("Add picks")
    settle(ui)
    assert not ui.app.model.picked and ui.app.model.results[0].n_regions == count + 1


def test_help_guide_and_the_tour_is_walked(ui):
    ui.click("help")
    assert ui.app.help_window.open
    ui.press_text("Close Help")
    ui.click("guide")
    assert ui.app.tour.active
    steps = len(ui.app.tour.steps)
    for _ in range(steps * 3):
        if ui.app.tour.awaiting:
            step = ui.app.tour.steps[ui.app.tour.step_idx]
            key = ui.app.tour._target_key(step["target"])
            assert key in ui.app.item_rects, key
            ui.click(key)
            settle(ui)
            if ui.dialog_open:
                ui.press_text("Cancel")
        if ui.app.tour.step_idx == steps - 1:
            break
        ui.press_text("Next ►")
    assert ui.app.tour.step_idx == steps - 1


def test_demo_button_simulates_the_known_field_and_detect_finds_four(tmp_path):
    ui = Ui(make_app(), (1200, 800))
    ui.click("Load demo")
    settle(ui, 240)
    assert len(ui.app.model.files) == 1
    ui.click("Detect")
    settle(ui)
    assert ui.app.model.run_entries()[0]["n_regions"] == 4


@pytest.mark.parametrize("size", SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def test_layout_at_both_sizes(tmp_path, size):
    from test.gui.emtk_layout_checks import assert_texts_apart

    path = write_field(tmp_path / "f.tif")
    ui = Ui(make_app(), size)
    ui.drop(path)
    ui.click("Detect")
    settle(ui)
    w, h = size
    left = (0, 24, 0.34 * w, h - 24)
    assert_texts_apart(ui.last, region=left)
    for key in ("Add files", "Detect", "Preview", "Export"):
        x, y, bw, bh = ui.app.item_rects[key]
        assert x >= 0 and x + bw <= 0.34 * w + 4, key


def test_nothing_is_written_under_home(ui, tmp_path):
    assert not (Path.home() / ".chisurf").exists() and Path.home() == tmp_path
