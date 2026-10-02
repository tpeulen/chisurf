"""The native PSF determination tool against the Qt tool it replaces, every control operated with real input events.

Hermetic through ``conftest.py`` (HOME, chisurf/MMFDB folders, QSettings in a temp folder); the last test proves the
user's real ``~/.chisurf`` is untouched. The Qt tool and the native app share the Qt-free ``PsfViewModel``: the beads,
the fits and the CSV of a run started from the native window must equal those of the Qt tool's model for the same stack.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.emtk_test_input import CTRL, SIZE, SMALL, Driver
from chisurf.plugins.microscopy.psf_determination.gui.app import PsfDeterminationApp, make_app
from chisurf.plugins.microscopy.psf_determination.gui.view_model import PsfViewModel

PLUGIN = Path(__file__).parent.parent
REAL_CHISURF = Path(pwd.getpwuid(os.getuid()).pw_dir) / ".chisurf"
BEADS = [(10, 20, 20), (10, 22, 60), (10, 50, 30), (11, 55, 80), (9, 90, 50)]      # z, y, x


def snapshot_real():
    if not REAL_CHISURF.is_dir():
        return {}
    return {str(p): p.stat().st_mtime_ns for p in REAL_CHISURF.rglob("*")
            if p.is_file() and not {"cache", "logs"} & set(p.parts)}


REAL_BEFORE = snapshot_real()


def make_stack(shape=(21, 110, 100), seed=4):
    """Five Gaussian beads (sigma 1.8 / 1.8 / 3.0), flat background 5, Poisson noise."""
    rng = np.random.default_rng(seed)
    z, y, x = np.indices(shape)
    img = np.full(shape, 5.0)
    for bz, by, bx in BEADS:
        img += 800 * np.exp(-0.5 * (((x - bx) / 1.8) ** 2 + ((y - by) / 1.8) ** 2 + ((z - bz) / 3.0) ** 2))
    return rng.poisson(img).astype(np.float32)


@pytest.fixture
def tiff(tmp_path):
    from chisurf.core.fio.image import imwrite

    path = tmp_path / "data" / "beads.tif"
    path.parent.mkdir()
    imwrite(path, make_stack(), axes="ZYX")
    return str(path)


class UI(Driver):
    def settle(self, timeout=120.0):
        end = time.monotonic() + timeout
        self.draw(1)
        while self.app.job.busy and time.monotonic() < end:
            time.sleep(0.01)
            self.draw(1)
        self.draw(3)
        assert not self.app.job.busy
        assert not self.app.job.error, self.app.job.error
        return self.app.model


@pytest.fixture
def ui():
    app = make_app()
    driver = UI(app)
    driver.draw(3)
    yield driver
    app.job.thread and app.job.thread.join(timeout=20)


@pytest.fixture
def demo(ui):
    ui.click_name("demo")
    ui.draw(3)
    return ui


@pytest.fixture
def detected(demo):
    demo.click_name("detect_beads")
    demo.settle()
    return demo


def field(ui, name):
    ui.draw(2)
    for form in ui.app.forms.values():
        if name in form.rects:
            return form.rects[name]
    raise AssertionError(name)


def type_value(ui, name, text):
    ui.type_into(field(ui, name), text)
    return ui.app.model


def pick(ui, x, y):
    px, py = ui.app.canvas.pick_pixels(x, y)
    ui.click((px - 2, py - 2, 4, 4))


# ───────────────────────────── numbers equal the Qt tool ───────────────────────────── #


@pytest.fixture
def qt_model():
    pytest.importorskip("qtpy")
    from qtpy import QtWidgets

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    from chisurf.plugins.microscopy.psf_determination.gui.tool import PsfDeterminationTool

    tool = PsfDeterminationTool()
    tool._qapp = qapp
    tool.model.set_stack(make_stack())
    tool.model.pixel_size_nm, tool.model.z_step_nm = 100.0, 300.0
    return tool.model


def test_detection_fits_and_the_batch_csv_started_in_the_native_window_equal_the_qt_tools(qt_model, demo, tmp_path):
    qt = qt_model
    qt.detect_beads()
    qt.fit_all()
    qt.export_csv(str(tmp_path / "qt.csv"))
    ui = demo
    ui.click_name("detect_beads")
    m = ui.settle()
    assert m.detected_beads == qt.detected_beads and len(m.detected_beads) == 4
    ui.click_name("fit_all")
    m = ui.settle()
    assert m.results_text == qt.results_text
    ui.app.last_dir = str(tmp_path)
    ui.click_name("export_csv")
    ui.click_text("psf_batch_results.csv", last=False, fx=0.3)
    ui.app.key(0x41, "a", CTRL)
    ui.type("native.csv")
    ui.click_text("Save")
    ui.settle()
    assert (tmp_path / "native.csv").read_text() == (tmp_path / "qt.csv").read_text()


def test_a_picked_bead_fit_equals_the_qt_tools_single_fit(qt_model, demo):
    qt = qt_model
    qt.selected_bead = (10, 20, 20)
    fit = qt.fit_selected()
    demo.app.canvas.z = 10
    demo.draw(3)
    pick(demo, 20, 20)
    m = demo.settle()
    assert m.selected_bead == (10, 20, 20) and m.results_text == qt.results_text
    np.testing.assert_allclose(m._fit_params, qt._fit_params)
    assert m.fit_circle()["r"] == pytest.approx(qt.fit_circle()["r"])
    assert fit["success"]


def test_the_physical_widths_of_the_known_stack_are_recovered(demo):
    demo.click_name("detect_beads")
    demo.settle()
    demo.click_name("fit_all")
    m = demo.settle()
    fwhm_xy = [float(v) for v in re.findall(r"FWHMxy≈([\d.]+) nm", m.results_text)]
    fwhm_z = [float(v) for v in re.findall(r"FWHMz=([\d.]+) nm", m.results_text)]
    assert len(fwhm_xy) == 4 == len(fwhm_z)
    assert np.mean(fwhm_xy) == pytest.approx(424.0, rel=0.02) and np.mean(fwhm_z) == pytest.approx(2120.0, rel=0.03)


def test_the_native_forms_carry_every_field_range_and_decimal_of_the_qt_spec():
    qt_spec = json.loads((PLUGIN / "gui" / "psf.view.json").read_text())

    def leaves(sections, out):
        for s in sections:
            if s.get("attr") and s.get("type") == "value" and "target" not in s:
                out[s["attr"]] = s
            leaves(s.get("sections", []), out)
        return out

    qt = {a: s for a, s in leaves(qt_spec["sections"], {}).items() if a != "results_text"}
    app = make_app()
    nat = {}
    for spec in app.panels.values():
        leaves(spec["sections"], nat)
    assert set(qt) <= set(nat)
    for attr, section in qt.items():
        for key in ("minimum", "maximum", "decimals", "kind", "step"):
            if key in section:
                assert nat[attr].get(key) == section[key], (attr, key)


# ───────────────────────────────────── loading ───────────────────────────────────── #


def test_the_empty_window_asks_for_a_stack_and_greys_the_actions(ui):
    assert "Load an image or run Preview to inspect pixels." in [t[5] for t in ui.draw().texts]
    for name in ("detect_beads", "fit_selected", "fit_all", "export_csv"):
        ui.click_name(name)
        assert ui.app.dialog is None and not ui.app.job.busy
    assert ui.app.model.stack is None


def test_load_stack_through_the_dialog_reads_the_tiff_on_a_job(ui, tiff):
    ui.app.model.pixel_size_nm = 100.0
    ui.click_name("load_stack")
    assert ui.app.dialog is not None
    # the dialog opens in the plugin's start folder: go to the file's folder through the app (as the Qt dialog did)
    ui.app.dialog.directory = str(Path(tiff).parent)
    ui.app.dialog.refresh()
    ui.click_text("beads.tif")
    ui.click_text("Open")
    m = ui.settle()
    assert m.stack.shape == (21, 110, 100) and m.filename == tiff
    assert any("beads.tif" in t[5] for t in ui.draw().texts)


def test_the_dialog_cancel_and_close_load_nothing(ui):
    for closer in ("Cancel", "×"):
        ui.click_name("load_stack")
        assert ui.app.dialog is not None
        ui.click_text(closer)
        assert ui.app.dialog is None
    assert ui.app.model.stack is None


def test_a_dropped_tiff_is_loaded_and_a_dropped_junk_file_is_reported(ui, tiff, tmp_path):
    assert ui.drop(tiff) is True
    m = ui.settle()
    assert m.filename == tiff
    junk = tmp_path / "junk.tif"
    junk.write_text("not a tiff")
    ui.drop(junk)
    ui.draw(1)
    end = time.monotonic() + 30
    while ui.app.job.busy and time.monotonic() < end:
        ui.draw(1)
        time.sleep(0.01)
    ui.draw(3)
    assert ui.app.job.error and any("Error:" in t[5] for t in ui.draw().texts)
    assert ui.drop() is False


def test_the_demo_button_loads_a_generated_stack_labelled_as_a_demo(demo):
    m = demo.app.model
    assert m.stack.shape == (21, 110, 100) and m.filename == ""
    assert "Demo stack" in [t[5] for t in demo.draw().texts]
    assert "Demo stack loaded" in m.results_text and (m.pixel_size_nm, m.z_step_nm) == (100.0, 300.0)


def test_the_mmfdb_button_opens_the_dataset_picker_and_cancel_closes_it(ui):
    ui.click_name("mmfdb")
    assert ui.app.picker.is_open
    assert "Select MMFDB dataset" in [t[5] for t in ui.draw(3).texts]
    ui.click_name("load_stack")                        # greyed while the picker is open
    assert ui.app.dialog is None
    ui.click_text("Cancel")
    assert not ui.app.picker.is_open


# ───────────────────────────────────── detection, picking, fitting ───────────────────────────────────── #


def test_detect_runs_on_a_job_and_marks_the_beads_then_fit_selected_fits_the_first(detected):
    m = detected.app.model
    assert len(m.detected_beads) == 4 and m.selected_bead == m.detected_beads[0]
    assert "4 detected beads" in [t[5] for t in detected.draw().texts]
    detected.click_name("fit_selected")
    m = detected.settle()
    assert m._fit_params is not None and "PSF Fit Results" in m.results_text


def test_clicking_a_bead_in_the_image_selects_and_fits_it_and_a_click_outside_does_nothing(demo):
    demo.app.canvas.z = 10
    demo.draw(3)
    pick(demo, 60, 22)
    m = demo.settle()
    assert m.selected_bead == (10, 22, 60) and m._fit_params is not None
    before = m.selected_bead
    px, py = demo.app.canvas.pick_pixels(-30, 5)
    demo.click((px - 2, py - 2, 4, 4))
    assert demo.app.model.selected_bead == before and not demo.app.job.busy


def test_the_bead_index_field_selects_and_fits_the_typed_bead_and_clamps(detected):
    m = detected.app.model
    type_value(detected, "bead_index", "2")
    m = detected.settle()
    assert detected.app.bead_index == 2 and m.selected_bead == m.detected_beads[2] and m._fit_params is not None
    type_value(detected, "bead_index", "99")
    detected.settle()
    assert detected.app.bead_index == 3
    detected.click(field(detected, "bead_index.stepper"), fy=0.75)
    detected.settle()
    assert detected.app.bead_index == 2


def test_the_bead_index_is_greyed_without_beads(demo):
    assert not demo.app.beads.enabled("bead_index")
    assert demo.app.beads.bounds("bead_index") == (0, 0)


def test_fit_all_lists_every_bead_and_the_profile_tabs_show_the_fit(detected):
    detected.click_name("fit_all")
    m = detected.settle()
    assert m.results_text.count("ok=True") == 4
    detected.click_name("fit_selected")
    detected.settle()
    for axis, label in (("x", "x [pixels]"), ("y", "y [pixels]"), ("z", "z [slices]")):
        detected.click_text(f"{axis} profile")
        strings = [t[5] for t in detected.draw(3).texts]
        assert label in strings and "Intensity" in strings and "data" in strings and "fit" in strings, axis
    assert detected.app.profile_axis == "z"


def test_buttons_are_greyed_while_a_job_runs(demo):
    demo.click_name("detect_beads")
    demo.draw(1)
    assert demo.app.job.busy
    demo.click_name("fit_all")                         # greyed: nothing queued twice
    demo.settle()
    assert "Batch PSF fits" not in demo.app.model.results_text


# ───────────────────────────────────── settings forms and display ───────────────────────────────────── #


@pytest.mark.parametrize("name,typed,expected", [
    ("pixel_size_nm", "65", 65.0), ("pixel_size_nm", "5000", 1000.0), ("z_step_nm", "150", 150.0), ("z_step_nm", "0", 1.0),
    ("roi_xy", "21", 21), ("roi_xy", "1", 3), ("roi_z", "9", 9), ("roi_z", "999", 200),
    ("pixels_per_frame", "40", 40), ("min_distance", "8", 8.0), ("min_area", "3", 3),
])
def test_each_field_takes_typed_values_clamped_to_the_qt_range(ui, name, typed, expected):
    m = type_value(ui, name, typed)
    assert getattr(m, name) == pytest.approx(expected)


@pytest.mark.parametrize("name,step", [("pixel_size_nm", 1.0), ("z_step_nm", 10.0), ("roi_xy", 1), ("pixels_per_frame", 1), ("min_distance", 1.0)])
def test_the_arrows_step_each_field(ui, name, step):
    m = ui.app.model
    ui.click(field(ui, f"{name}.stepper"), fy=0.25)
    after_up = getattr(m, name)
    ui.click(field(ui, f"{name}.stepper"), fy=0.75)
    ui.click(field(ui, f"{name}.stepper"), fy=0.75)
    assert after_up - getattr(m, name) == pytest.approx(2 * step)


def test_the_calibration_scales_the_physical_widths_when_the_bead_is_refit(demo):
    demo.app.canvas.z = 10
    demo.draw(3)
    pick(demo, 20, 20)
    m = demo.settle()
    first = float(re.search(r"FWHMx: ([\d.]+)", m.results_text).group(1))
    type_value(demo, "pixel_size_nm", "200")
    demo.click_name("fit_selected")
    m = demo.settle()
    second = float(re.search(r"FWHMx: ([\d.]+)", m.results_text).group(1))
    assert second == pytest.approx(2 * first, rel=1e-6)


def test_the_colormap_gamma_levels_and_reset_controls_work(demo):
    c = demo.app.canvas
    demo.click_text("magma")
    demo.click_text("gray")
    assert c.colormap == "gray" and demo.app.model.colormap == "gray"
    assert c.auto_levels is True
    demo.click_text("Automatic levels")
    assert c.auto_levels is False and demo.drawn("Display minimum")
    demo.click_text("Automatic levels")
    assert c.auto_levels is True
    demo.click_text("Reset view")


def test_the_z_slider_browses_slices_by_dragging(demo):
    c = demo.app.canvas
    label = [t[:4] for t in demo.draw().texts if t[5] == "Z slice"][-1]
    left = [t for t in demo.draw().texts if t[5] == "Detect"]                 # the controls window ends before the stack window
    x0 = demo.app.item_rects["stack"][0]
    y = label[1] + label[3] / 2
    before = c.z
    demo.drag((x0 + 10, y), (x0 + 400, y), steps=4)
    assert c.z != before


def test_the_wheel_zooms_the_image_and_a_drag_pans_it(demo):
    demo.draw(3)
    x, y, w, h = demo.app.item_rects["stack"]
    before = [t[5] for t in demo.draw().texts]
    demo.wheel(x + w * 0.5, y + h * 0.5, -3.0)
    zoomed = [t[5] for t in demo.draw().texts]
    assert zoomed != before
    demo.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.4))
    assert [t[5] for t in demo.draw().texts] != zoomed


# ───────────────────────────────────── settings files, help, guide ───────────────────────────────────── #


def test_save_and_load_settings_round_trip_through_the_dialogs_and_reopen_the_stack(ui, tiff, tmp_path):
    ui.drop(tiff)
    ui.settle()
    m = ui.app.model
    type_value(ui, "pixel_size_nm", "65")
    type_value(ui, "roi_xy", "17")
    ui.app.canvas.z = 7
    ui.app.last_dir = str(tmp_path)
    ui.click_name("save_settings")
    ui.app.dialog.directory = str(tmp_path)
    ui.click_text("psf_settings.json", last=False, fx=0.3)
    ui.app.key(0x41, "a", CTRL)
    ui.type("mine.json")
    ui.click_text("Save")
    saved = json.loads((tmp_path / "mine.json").read_text())
    assert saved["pixel_size_nm"] == 65.0 and saved["roi_xy"] == 17 and saved["filename"] == tiff and saved["display"]["z"] == 7
    other = UI(make_app())
    other.draw(3)
    other.app.dialog = None
    other.click_name("load_settings")
    other.app.dialog.directory = str(tmp_path)
    other.app.dialog.refresh()
    other.click_text("mine.json")
    other.click_text("Open")
    om = other.settle()
    assert om.pixel_size_nm == 65.0 and om.roi_xy == 17 and om.filename == tiff and om.stack is not None
    assert other.app.canvas.z == 7


def test_a_damaged_settings_file_is_reported(ui, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    ui.click_name("load_settings")
    ui.app.dialog.directory = str(tmp_path)
    ui.app.dialog.refresh()
    ui.click_text("bad.json")
    ui.click_text("Open")
    assert ui.app.error and ui.app.dialog is not None


def test_the_host_settings_seam_round_trips(demo):
    m = demo.app.model
    m.pixel_size_nm, m.min_area = 80.0, 4
    saved = json.loads(json.dumps(demo.app.export_settings()))
    other = make_app()
    other.restore_settings(saved)
    assert other.model.pixel_size_nm == 80.0 and other.model.min_area == 4
    other.restore_settings(None)


def test_help_opens_with_live_links_and_closes(ui):
    ui.click_name("help")
    assert ui.app.help_window.open
    ui.click_text("Close")
    assert not ui.app.help_window.open
    repo = next(p for p in PLUGIN.parents if (p / "pyproject.toml").exists())
    links = re.findall(r"\]\((docs/[^)#]+)", (PLUGIN / "gui" / "help.md").read_text())
    assert links and all((repo / link).is_file() for link in links)


def test_the_tour_waits_for_the_demo_detect_and_fit_all(ui):
    ui.click_name("guide")
    tour = ui.app.tour
    assert tour.active
    ui.click_text("Next ►")
    assert tour.step_idx == 1 and tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 1
    ui.click_name("demo")
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 2
    ui.click_text("Next ►")
    assert tour.step_idx == 3 and tour.awaiting
    ui.click_name("detect_beads")
    ui.settle()
    assert not tour.awaiting
    ui.click_text("Next ►")
    assert tour.step_idx == 4 and tour.awaiting
    ui.click_name("fit_all")
    ui.settle()
    assert not tour.awaiting
    ui.click_text("Close Tour")
    assert not tour.active


def test_every_tour_target_is_drawn(ui):
    for index, step in enumerate(ui.app.tour.steps):
        key = ui.app.tour._target_key(step.get("target"))
        if not key:
            continue
        ui.app.tour.start(index)
        ui.draw(3)
        assert ui.app.tour.get_target_rect(key), key
        ui.app.tour.stop()


# ───────────────────────────────────── layout, tooltips, hygiene ───────────────────────────────────── #


@pytest.mark.parametrize("size", [SIZE, SMALL, (500, 500)])
def test_the_window_draws_empty_and_populated_at_every_size(ui, size):
    ui.resize(size)
    ui.draw(3)
    ui.click_name("demo")
    ui.click_name("detect_beads")
    ui.settle()
    ui.click_name("fit_all")
    ui.settle()
    ui.resize(size)


def test_no_text_runs_past_the_window_edge_in_the_small_window(detected):
    detected.resize(SMALL)
    detected.click_name("fit_all")
    detected.settle()
    for x, y, w, h, align, string, *_ in detected.draw(3).texts:
        assert x + w <= SMALL[0] + 1, (x, w, string)


def test_every_control_has_a_tooltip(detected):
    from test.gui.emtk_port_parity import emtk_inventory

    detected.click_name("fit_all")
    detected.settle()
    missing = set(emtk_inventory(detected.app, SIZE)["controls_without_tooltip"])
    assert not missing, sorted(missing)


def test_the_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("psf_determination")
    assert result["ok"], result["output"]


def test_zzz_the_real_chisurf_folder_was_not_touched():
    assert snapshot_real() == REAL_BEFORE
