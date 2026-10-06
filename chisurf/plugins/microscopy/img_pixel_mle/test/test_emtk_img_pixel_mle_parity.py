"""The native pixel-wise MLE tool against the Qt tool it replaces: numbers, every control with a real-input click test, the layout at two sizes.

Hermetic: settings, MMFDB and its database in a temporary folder, a temporary HOME, the photon streams written into a temporary folder from a
seed, no network (the database picker gets a stub client); a last test asserts the real ``~/.chisurf`` is untouched. References: the Qt tool's own view
model run on the same files (the per-pixel fit itself is the plugin's core, unchanged).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.microscopy.imaging_emtk import pixel_checks as C
from chisurf.plugins.microscopy.imaging_emtk import pixel_testing as data
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, dialog_open, hermetic_env, walk
from chisurf.plugins.microscopy.img_pixel_mle import core as mle_core
from chisurf.plugins.microscopy.img_pixel_mle.gui.app import PixelMleApp, make_app
from chisurf.plugins.microscopy.img_pixel_mle.gui.model import PixelMleModel
from chisurf.plugins.microscopy.img_pixel_mle.gui.view_model import PixelMleViewModel
from test.gui.emtk_layout_checks import (
    SIZES,
    assert_disjoint,
    assert_icons_clear,
    assert_inside,
    assert_texts_apart,
    draw,
)

HERE = Path(__file__).parent
PLUGIN = HERE.parent
EMTK_SPEC = json.loads((PLUGIN / "gui" / "pixel_mle_emtk.view.json").read_text(encoding="utf-8"))
QT_SPEC = json.loads((PLUGIN / "gui" / "pixel_mle.view.json").read_text(encoding="utf-8"))
BIG = (1200, 800)
_REAL_BEFORE = data.real_settings_state()


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(scope="module")
def scan(tmp_path_factory):
    """Two detectors (channel 0 parallel, 1 perpendicular) and an IRF measurement."""
    d = tmp_path_factory.mktemp("mle")
    return Path(data.flim_ptu(d / "scan.ptu", n_channels=2)), Path(data.irf_ptu(d / "irf.ptu"))


@pytest.fixture
def files(tmp_path, scan):
    """Copies in the test's own folder (the CSV is written beside the input)."""
    folder = tmp_path / "files"
    folder.mkdir()
    out = []
    for src in scan:
        target = folder / src.name
        target.write_bytes(src.read_bytes())
        out.append(target)
    return out


@pytest.fixture
def app():
    application = make_app()
    yield application
    application.close()


@pytest.fixture
def drv(app):
    return Driver(app, BIG)


FIT = dict(
    channels_parallel_text="0",
    channels_perpendicular_text="1",
    micro_time_start=0,
    micro_time_stop=250,
    min_photons=3,
)


def ready(app, files, **settings):
    scan, irf = files
    app.model.add_files([str(scan)])
    app.model.add_irf([str(irf)])
    for k, v in {**FIT, **settings}.items():
        setattr(app.model, k, v)
    return app.model


def fitted(app, drv, files, **settings):
    m = ready(app, files, **settings)
    drv.click("request_run")
    drv.settle(timeout=300)
    assert not app.job.error, app.job.error
    return m


def qt_run(files, **settings):
    qt = PixelMleViewModel()
    qt.files, qt.irf_files = [str(files[0])], [str(files[1])]
    for k, v in {**FIT, **settings}.items():
        setattr(qt, k, v)
    qt.run()
    return qt


# ── 1. the numbers ──────────────────────────────────────────────────────────────────────────────────────── #


def test_the_fitted_maps_and_tables_equal_the_qt_tool_on_the_same_files(app, drv, files):
    m = fitted(app, drv, files)
    qt = qt_run(files)
    assert m.result_names == qt.result_names == ["scan"] and m.status_text == qt.status_text == ""
    np.testing.assert_array_equal(m.tau_map_image(), qt.tau_map_image())
    r, q = m.results[0], qt.results[0]
    assert r.n_pixels_fit == q.n_pixels_fit and r.n_pixels_fit > 100
    np.testing.assert_array_equal(r.tau, q.tau)
    assert m.info_html() == qt.info_html() and m.summary_text.startswith("1 file(s),")


def test_the_csv_is_written_beside_the_input_and_the_fitted_lifetimes_are_physical(app, drv, files):
    m = fitted(app, drv, files)
    csv = files[0].with_name("scan_pixel_mle.csv")
    lines = csv.read_text().splitlines()
    assert (
        csv.exists()
        and "tau" in lines[0].split(",")
        and len(lines) - 1 >= m.results[0].n_pixels_fit
    )
    tau = np.asarray(m.results[0].tau)
    assert (
        np.isfinite(tau).any()
        and (tau[np.isfinite(tau) & (tau != 0)] > 0).all()
        and np.nanmax(tau) < 100
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"micro_time_binning": 2, "micro_time_stop": 120},
        {"irf_threshold": 0.1, "shift_sp": 0.5},
        {"use_bg": True, "bg_p": 1.0, "bg_s": 1.0},
        {"twoi_star": False, "bifl_scatter": True},
        {"engine": "loop", "n_workers": 1},
        {"fit_model": "fit24"},
    ],
    ids=lambda c: "+".join(sorted(c)),
)
def test_every_setting_gives_what_the_qt_tool_gives_with_the_same_setting(app, drv, files, changes):
    m = fitted(app, drv, files, **changes)
    qt = qt_run(files, **changes)
    np.testing.assert_allclose(m.tau_map_image(), qt.tau_map_image(), rtol=1e-12, equal_nan=True)


def test_a_failing_run_names_the_file_and_the_reason(app, drv, files, tmp_path):
    bad = tmp_path / "bad.ptu"
    bad.write_bytes(b"not photons")
    m = ready(app, files)
    m.files = [str(bad)]
    drv.click("request_run")
    drv.settle(timeout=60)
    assert m.status_text.startswith("bad:") and m.results == []


def test_run_is_greyed_and_says_why_until_everything_is_given(app, drv, files):
    m = app.model
    assert not m.enabled("request_run") and m.can_run() == (False, "No imaging files selected.")
    drv.click("request_run")
    assert not app.job.busy
    m.add_files([str(files[0])])
    assert m.can_run() == (False, "No IRF file selected.")
    m.add_irf([str(files[1])])
    m.micro_time_start, m.micro_time_stop = 100, 50
    assert m.can_run()[1] == "Empty micro-time fit window."
    m.micro_time_start, m.micro_time_stop = 0, 250
    m.channels_parallel_text = ""
    assert m.can_run()[1] == "Both parallel and perpendicular channels are required."
    m.channels_parallel_text, m.channels_perpendicular_text = "0 1", "1"
    assert m.can_run()[1] == "Parallel and perpendicular channels must be distinct."


# ── 2. the file lists ───────────────────────────────────────────────────────────────────────────────────── #


def test_add_files_opens_the_chooser_and_a_chosen_file_is_listed(app, drv, files):
    app.model.folder = str(files[0].parent)
    drv.click("sel_files.add")
    assert dialog_open(drv) and app.dialog.title == "Add imaging files"
    drv.click_text("scan.ptu")
    drv.click_text("Open", last=True)
    drv.draw(3)
    assert app.model.files == [str(files[0])] and not dialog_open(drv)
    assert "scan.ptu" in drv.draw(2).strings


def test_add_irf_takes_one_file_and_a_second_replaces_it(app, drv, files):
    app.model.folder = str(files[0].parent)
    drv.click("sel_irf_files.add")
    assert dialog_open(drv) and app.dialog.title == "Choose the IRF file"
    drv.click_text("irf.ptu")
    drv.click_text("Open", last=True)
    drv.draw(3)
    assert app.model.irf_files == [str(files[1])]
    app.model.add_irf([str(files[0])])
    assert app.model.irf_files == [str(files[0])]


def test_the_chooser_cancel_and_close_buttons_add_nothing(app, drv, files):
    app.model.folder = str(files[0].parent)
    drv.click("sel_files.add")
    drv.click_text("Cancel", last=True)
    assert not dialog_open(drv) and app.model.files == []
    drv.click("sel_files.add")
    drv.click_text("×")
    assert not dialog_open(drv) and app.model.files == []


def test_remove_and_clear_edit_the_list_without_deleting_files(app, drv, files, scan):
    m = app.model
    extra = files[0].with_name("second.ptu")
    extra.write_bytes(files[0].read_bytes())
    m.add_files([str(files[0]), str(extra)])
    drv.draw(3)
    drv.click("sel_files.1")
    drv.click("sel_files.remove")
    assert m.files == [str(files[0])] and extra.exists()
    drv.click("sel_files.clear")
    assert m.files == [] and files[0].exists()
    assert app.model.enabled("x") is not False


def test_the_database_buttons_pick_a_file_and_an_irf(app, drv, files):
    C.open_picker(app, drv, files[0]) if False else None
    app.picker.client = C.FakeClient(files[0])
    drv.click("sel_files.database")
    drv.draw(2)
    assert app.picker.is_open
    end = time.monotonic() + 10
    while "stored.ptu [raw_data] (ptu)" not in drv.draw(1).strings and time.monotonic() < end:
        time.sleep(0.02)
    drv.click_text("stored.ptu [raw_data] (ptu)")
    assert app.picker.accept()
    drv.draw(3)
    assert app.model.files == [str(files[0])]
    app.picker.client = C.FakeClient(files[1])
    drv.click("sel_irf_files.database")
    drv.draw(2)
    end = time.monotonic() + 10
    while "stored.ptu [raw_data] (ptu)" not in drv.draw(1).strings and time.monotonic() < end:
        time.sleep(0.02)
    drv.click_text("stored.ptu [raw_data] (ptu)")
    assert app.picker.accept()
    drv.draw(3)
    assert app.model.irf_files == [str(files[1])]


def test_a_drop_adds_the_files_and_a_drop_while_a_worker_runs_is_refused(app, drv, files):
    assert drv.drop(files[0]) is True
    assert app.model.files == [str(files[0])]
    ready(app, files)
    drv.click("request_run")
    assert app.job.busy and app.files_dropped([str(files[1])]) is False
    drv.settle(timeout=300)
    assert app.files_dropped([]) is False


def test_the_qt_host_delivers_a_dropped_file_to_the_app(app, files):
    pytest.importorskip("qtpy")
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui, QtWidgets

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    host = ControlHost(app)
    host.resize(900, 600)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(files[0]))])
    host.dropEvent(
        QtGui.QDropEvent(
            QtCore.QPointF(10, 10),
            QtCore.Qt.CopyAction,
            mime,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
        )
    )
    assert app.model.files == [str(files[0])] and qapp is not None
    host.close()


# ── 3. the settings ─────────────────────────────────────────────────────────────────────────────────────── #

FOLDS = {
    "irf_threshold": "IRF preparation.fold",
    "shift_sp": "IRF preparation.fold",
    "shift_ss": "IRF preparation.fold",
    "bg_p": "Background.fold",
    "bg_s": "Background.fold",
    "n_workers": "Performance.fold",
}


@pytest.mark.parametrize(
    "attr, text, expected",
    [
        ("channels_parallel_text", "0 4", "0 4"),
        ("channels_perpendicular_text", "1, 5", "1 5"),
        ("micro_time_start", "12", 12),
        ("micro_time_stop", "200", 200),
        ("micro_time_binning", "4", 4),
        ("min_photons", "9", 9),
        ("irf_threshold", "0.25", 0.25),
        ("shift_sp", "1.5", 1.5),
        ("shift_ss", "-2.25", -2.25),
        ("bg_p", "3.5", 3.5),
        ("bg_s", "4.5", 4.5),
        ("n_workers", "3", 3),
    ],
)
def test_every_typed_setting_is_taken_on_enter(app, drv, attr, text, expected):
    if attr in FOLDS:
        drv.click(FOLDS[attr])
    drv.type_into(attr, text)
    assert getattr(app.model, attr) == expected


def test_typed_numbers_are_clamped_to_the_qt_ranges(app, drv):
    drv.type_into("min_photons", "99999999")
    assert app.model.min_photons == 10000000
    drv.type_into("micro_time_binning", "0")
    assert app.model.micro_time_binning == 1
    drv.click("IRF preparation.fold")
    drv.type_into("irf_threshold", "7")
    assert app.model.irf_threshold == 1.0


def test_the_toggles_and_the_engine_choice_change_the_model(app, drv):
    drv.click("Fit flags.fold")
    start = app.model.twoi_star
    drv.click("twoi_star")
    assert app.model.twoi_star is (not start)
    drv.click("bifl_scatter")
    assert app.model.bifl_scatter is True
    drv.click("Background.fold")
    drv.click("use_bg")
    assert app.model.use_bg is True
    drv.click("Performance.fold")
    drv.click("engine")
    assert {"auto", "fast", "loop"} <= set(drv.draw(1).strings)
    drv.click_text("loop", last=True)
    assert app.model.engine == "loop"


def test_the_fit_model_list_shows_its_own_parameters_and_keeps_each_models_values(app, drv):
    m = app.model
    assert m.fit_model == "fit23"
    drv.click("fit_model")
    assert any("Bi-exponential" in s for s in drv.draw(1).strings)
    drv.click_text("Bi-exponential (fit24)", last=True)
    assert m.fit_model == "fit24"
    drv.type_into("p0_value", "3.25")
    assert m.p0_value == 3.25
    fixed = m.p1_fix
    drv.click("p1_fix")
    assert m.p1_fix is (not fixed)
    drv.click("fit_model")
    drv.click_text("Single lifetime + anisotropy (fit23)", last=True)
    assert m.fit_model == "fit23" and m.p0_value != 3.25
    drv.click("fit_model")
    drv.click_text("Bi-exponential (fit24)", last=True)
    assert m.p0_value == 3.25 and m.p1_fix is (not fixed)


def test_the_region_file_is_typed_or_browsed_and_a_bad_one_is_reported(app, drv, files, tmp_path):
    from chisurf.core.roi import RectangleROI, RegionCollection

    regions = RegionCollection(combine="or", name="r")
    regions.add(RectangleROI(0, 0, 16, 32, name="left"))
    path = tmp_path / "region.json"
    regions.save(str(path))
    drv.type_into("roi_path", str(path))
    assert app.model.roi is not None and app.model.status_text.startswith(
        "Region loaded: 1 region(s)"
    )
    drv.type_into("roi_path", str(tmp_path / "missing.json"))
    assert app.model.roi is None and app.model.status_text.startswith("Could not read region")
    app.model.folder = str(tmp_path)
    drv.click("open_roi")
    assert dialog_open(drv) and app.dialog.title == "Choose a region"
    drv.click_text("region.json")
    drv.click_text("Open", last=True)
    drv.draw(3)
    assert app.model.roi is not None and app.model.roi_path == str(path)


def test_a_region_confines_the_fit_to_its_pixels(app, drv, files, tmp_path):
    from chisurf.core.roi import RectangleROI, RegionCollection

    regions = RegionCollection(combine="or", name="r")
    regions.add(RectangleROI(0, 0, 16, 32, name="left"))
    path = tmp_path / "left.json"
    regions.save(str(path))
    full = fitted(app, drv, files).results[0].n_pixels_fit
    app2 = make_app()
    d2 = Driver(app2, BIG)
    m2 = ready(app2, files)
    m2.roi_path = str(path)
    d2.click("request_run")
    d2.settle(timeout=300)
    assert 0 < m2.results[0].n_pixels_fit < full
    app2.close()


# ── 4. running ──────────────────────────────────────────────────────────────────────────────────────────── #


def test_run_is_pressed_with_the_pointer_greyed_while_it_runs_and_the_status_is_empty_after(
    app, drv, files
):
    ready(app, files)
    assert app.model.enabled("request_run")
    drv.click("request_run")
    assert app.job.busy and not app.model.enabled("request_run")
    drv.settle(timeout=300)
    assert app.model.status_text == "" and app.model.results and not app.job.error


def test_cancel_stops_after_the_current_file_and_keeps_the_finished_ones(
    app, drv, files, monkeypatch
):
    real = mle_core.fit_pixel_lifetimes_from_file
    second = files[0].with_name("second.ptu")
    second.write_bytes(files[0].read_bytes())
    m = ready(app, files)
    m.add_files([str(second)])
    seen = []

    def slow(path, settings):
        seen.append(path)
        if len(seen) == 2:
            end = time.monotonic() + 30
            while not m.cancel_event.is_set() and time.monotonic() < end:
                time.sleep(0.01)
        return real(path, settings)

    monkeypatch.setattr(mle_core, "fit_pixel_lifetimes_from_file", slow)
    drv.click("request_run")
    end = time.monotonic() + 60
    while len(seen) < 2 and time.monotonic() < end:
        time.sleep(0.02)
        drv.draw(1)
    drv.click("cancel")
    drv.settle(timeout=120)
    assert m.status_text == "Cancelled; completed files are retained." and m.result_names == [
        "scan"
    ]


def test_cancel_is_idle_when_nothing_runs(app, drv):
    drv.click("cancel")
    assert not app.job.busy and app.model.status_text == ""


# ── 5. the map ──────────────────────────────────────────────────────────────────────────────────────────── #


def test_the_lifetime_map_tab_is_empty_with_a_message_then_a_picture_with_axes(app, drv, files):
    app.docks.focus("Lifetime map")
    assert any(s.startswith("No lifetime map yet") for s in drv.draw(3).strings)
    fitted(app, drv, files)
    app.docks.focus("Lifetime map")
    strings = drv.draw(3).strings
    assert "x [px]" in strings and "y [px]" in strings
    x, y, w, h = app.item_rects["Lifetime map"]
    assert w > 300 and h > 300


def test_the_result_list_switches_files_and_the_colormap_list_changes_the_picture(app, drv, files):
    second = files[0].with_name("other.ptu")
    second.write_bytes(files[0].read_bytes())
    m = ready(app, files)
    m.add_files([str(second)])
    drv.click("request_run")
    drv.settle(timeout=300)
    assert m.result_names == ["scan", "other"] and m.current_result_name == "scan"
    drv.click("current_result_name")
    assert "other" in drv.draw(1).strings
    drv.click_text("other", last=True)
    assert m.current_result_name == "other"
    start = m.colormap
    drv.click_text(start)
    assert {"magma", "inferno", "viridis", "gray"} <= set(drv.draw(1).strings)
    drv.click_text("viridis", last=True)
    assert m.colormap == "viridis"


def test_the_wheel_zooms_and_a_drag_pans_the_lifetime_map(app, drv, files):
    C.numeric_ticks  # noqa: B018
    from chisurf.plugins.microscopy.imaging_emtk.testing import numeric_ticks

    fitted(app, drv, files)
    app.docks.focus("Lifetime map")
    drv.draw(3)
    x, y, w, h = app.item_rects["Lifetime map"]
    original = numeric_ticks(drv.draw(2))
    drv.wheel(x + w / 2, y + h / 2, 3)
    zoomed = numeric_ticks(drv.draw(2))
    assert zoomed != original
    for end in ((0.3, 0.4), (0.7, 0.6)):
        drv.drag((x + w * 0.5, y + h * 0.5), (x + w * end[0], y + h * end[1]))
        if numeric_ticks(drv.draw(2)) != zoomed:
            break
    else:
        pytest.fail("a drag did not pan the map")


# ── 6. help, guide, settings, hub ───────────────────────────────────────────────────────────────────────── #


def test_help_button_opens_the_help_and_its_buttons_work(app, drv):
    C.help_button_opens_the_help_and_its_buttons_work(app, drv)


def test_guide_button_starts_the_tour_and_close_tour_ends_it(app):
    C.guide_button_starts_the_tour_and_close_tour_ends_it(app)


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(
    app, drv, files
):
    def add_files():
        app.model.folder = str(files[0].parent)
        drv.click("sel_files.add")
        drv.click_text("scan.ptu")
        drv.click_text("Open", last=True)

    def add_irf():
        app.model.folder = str(files[0].parent)
        drv.click("sel_irf_files.add")
        drv.click_text("irf.ptu")
        drv.click_text("Open", last=True)

    def run():
        for k, v in FIT.items():
            setattr(app.model, k, v)
        drv.click("request_run")

    C.tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(
        app, drv, files[0], {"files": add_files, "irf": add_irf, "run": run}
    )
    assert app.model.results


def test_every_guide_target_is_a_drawn_control_or_window(app, drv, files):
    fitted(app, drv, files)
    for index, step in enumerate(app.tour.steps):
        target = step.get("target") or {}
        if not target:
            continue
        app.tour.start(index)
        drv.draw(3)
        key = app.tour._target_key(target)
        rect = app.item_rects.get(key) or app.form.rects.get(key)
        assert rect and rect[2] > 0, f"{step['title']!r}: {key!r} is not drawn"
        app.tour.stop()


def test_settings_round_trip_and_invalid_values_are_ignored(app, drv, files):
    m = ready(app, files, min_photons=7, engine="fast", use_bg=True, bg_p=2.5)
    m.fit_model = "fit24"
    m.p0_value = 3.25
    saved = app.export_settings()
    json.dumps(saved)
    fresh = make_app()
    fresh.restore_settings(saved)
    f = fresh.model
    assert (f.min_photons, f.engine, f.use_bg, f.bg_p, f.fit_model, f.p0_value) == (
        7,
        "fast",
        True,
        2.5,
        "fit24",
        3.25,
    )
    assert f.files == [str(files[0])] and f.irf_files == [str(files[1])]
    fresh.restore_settings(
        {
            "min_photons": "many",
            "engine": "turbo",
            "use_bg": "yes",
            "fit_model": "fit99",
            "files": "x",
            "model_params": {"fit24": [[1], "x"]},
        }
    )
    assert (f.min_photons, f.engine, f.use_bg, f.fit_model) == (7, "fast", True, "fit24")
    fresh.restore_settings("garbage")
    fresh.close()


def test_the_imaging_hub_drives_the_tool(files):
    coordinator = C.FakeCoordinator()
    app = make_app(coordinator=coordinator)
    d = Driver(app, BIG)
    app.apply_setup_settings(
        {
            "detectors": {
                "green": {
                    "chs": [0, 2],
                    "ch_p": [0],
                    "ch_s": [2],
                    "micro_time_ranges": [[0, 200]],
                    "g_factor": 1.2,
                }
            }
        }
    )
    assert (
        app.model.settings.detector_chs_p == [0]
        and app.model.settings.detector_chs_s == [2]
        and app.model.settings.g_factor == 1.2
    )
    app.apply_calibration(
        {
            "green": {
                "irf": [str(files[1])],
                "bg_vv": 2.0,
                "bg_vh": 1.0,
                "conv_start": 5,
                "conv_stop": 150,
            }
        }
    )
    assert app.model.irf_files == [str(files[1])] and (
        app.model.micro_time_start,
        app.model.micro_time_stop,
    ) == (5, 150)
    app.apply_pipeline_context({"source": str(files[0]), "hdf5": ""})
    assert app.model.files == [str(files[0])]
    ready(app, files, **{k: v for k, v in FIT.items() if k not in ("micro_time_start",)})
    assert app.start("request_run")
    app.apply_setup_settings(
        {"detectors": {"late": {"chs": [1], "ch_p": [1], "ch_s": [3], "micro_time_ranges": []}}}
    )  # arrives while the worker runs
    assert app.model.settings.detector_chs_p != [1]
    d.settle(timeout=300)
    d.draw(3)
    assert app.model.settings.detector_chs_p == [1], "applied after the worker delivered"
    app.close()


# ── 7. static: spec, inventory, Qt-free, tooltips, layout ──────────────────────────────────────────────── #


def _labels(sections):
    out = set()
    for sec in walk(sections):
        if sec.get("label"):
            out.add(sec["label"])
        if sec.get("title") and sec.get("type") == "custom":
            out.add(sec["title"])
        for b in sec.get("buttons", []):
            out.add(b["label"])
    return {
        "".join(ch for ch in label if ord(ch) < 0x2300 or ch in "ρτ∥⊥γ").strip() for label in out
    }


def test_every_qt_control_has_an_emtk_equivalent():
    qt, emtk = _labels(QT_SPEC["sections"]), _labels(EMTK_SPEC["sections"])
    assert {
        "CLSM imaging files",
        "IRF file",
        "Fit start",
        "Fit stop",
        "Micro-time binning",
        "Min photons",
        "Region",
        "Threshold",
        "Run",
        "Engine",
        "Threads",
        "Subtract",
        "2I* (P+2S)",
        "BIFL scatter",
    } <= qt
    assert qt - {"Lifetime map"} <= emtk | {
        "Parallel channels",
        "Perpendicular channels",
        "Shift",
        "bg",
    }, sorted(qt - emtk)
    assert {"Parallel channels (∥)", "Perpendicular channels (⊥)"} <= {
        s.get("label") for s in walk(EMTK_SPEC["sections"])
    }


def test_every_spec_attribute_and_action_exists_on_the_model():
    model = PixelMleModel()
    for section in walk(EMTK_SPEC["sections"]):
        if section.get("attr"):
            assert hasattr(model, section["attr"]), section
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button
        for key in ("call", "options_source"):
            if section.get(key):
                assert hasattr(model, section[key]), (key, section)
        if section.get("type") == "custom" and section.get("options", {}).get("source"):
            assert callable(getattr(model, section["options"]["source"])), section
    assert not [
        s
        for s in walk(EMTK_SPEC["sections"])
        if s.get("type") not in ("custom", "panel") and not s.get("description")
    ]
    assert not [
        b
        for s in walk(EMTK_SPEC["sections"])
        for b in s.get("buttons", [])
        if not b.get("description")
    ]


def test_the_port_is_qt_free():
    C.qt_free("img_pixel_mle")


def test_every_control_has_a_tooltip(app, drv, files):
    from test.gui.emtk_port_parity import emtk_inventory

    fitted(app, drv, files)
    missing = set()
    for fold in ("IRF preparation.fold", "Fit flags.fold", "Background.fold", "Performance.fold"):
        drv.click(fold)
    for tab in ("Lifetime map", "Settings"):
        app.docks.focus(tab)
        drv.draw(3)
        missing |= set(emtk_inventory(app, BIG)["controls_without_tooltip"])
    assert not missing, sorted(missing)


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def size(request):
    return request.param


def test_layout_empty_and_populated_has_no_clipped_or_overlapping_text(app, files, size):
    drv = Driver(app, size)
    painter = draw(app, size)
    assert_texts_apart(painter)
    assert_icons_clear(painter)
    fitted(app, drv, files)
    for fold in ("IRF preparation.fold", "Fit flags.fold", "Background.fold", "Performance.fold"):
        drv.click(fold)
    for tab in ("Lifetime map", "Settings"):
        app.docks.focus(tab)
        C.texts_apart(draw(app, size), ignore=tuple(str(p) for p in files))
    rects = {
        k: app.form.rects[k]
        for k in (
            "request_run",
            "sel_files",
            "sel_irf_files",
            "channels_parallel_text",
            "min_photons",
            "fit_model",
        )
        if k in app.form.rects
    }
    assert_inside(rects, size)
    assert_icons_clear(draw(app, size))


def test_the_map_gets_the_space_and_the_settings_stay_beside_it(app, drv, files, size):
    drv = Driver(app, size)
    fitted(app, drv, files)
    app.docks.focus("Lifetime map")
    drv.draw(3)
    ix, iy, iw, ih = app.item_rects["Lifetime map"]
    assert iw * ih >= 0.25 * size[0] * size[1] * (1.0 if size[0] >= 1200 else 0.5), (iw, ih)
    sx, sy, sw, sh = app.form.rects["request_run"]
    assert sx + sw <= ix


def test_zz_the_real_user_settings_were_never_touched():
    assert data.real_settings_state() == _REAL_BEFORE
