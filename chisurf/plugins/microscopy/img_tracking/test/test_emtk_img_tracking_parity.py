"""The native particle-tracking tool against the Qt tool it replaces: numbers, every action and every error path.

Hermetic: settings in a temporary folder, files in ``tmp_path``, no network. The reference is (a) the numbers the
Qt window showed on its own simulated movie (``okf/plugins/emtk-ports/img_tracking/qt_values.json``, captured by
``scripts/capture_qt_populated.py`` before the port), (b) the Qt tool itself, constructed offscreen and run on the
same data, and (c) a written-out run of the core functions that does not go through the shared view model.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fluorescence.imaging import tracking as tk
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, hermetic_env
from chisurf.plugins.microscopy.img_tracking import core
from chisurf.plugins.microscopy.img_tracking.gui.app import ImgTrackingApp, make_app

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
EVIDENCE = REPO / "okf/plugins/emtk-ports/img_tracking"
QT_VALUES = json.loads((EVIDENCE / "qt_values.json").read_text(encoding="utf-8"))
QT_CSV = (EVIDENCE / "qt_exported.csv").read_text(encoding="utf-8")
QT_SPEC = json.loads((PLUGIN / "gui" / "tracking.view.json").read_text(encoding="utf-8"))
EMTK_SPEC = json.loads((PLUGIN / "gui" / "tracking_emtk.view.json").read_text(encoding="utf-8"))

#: The settings of the small simulated movie the Qt baseline used.
SMALL = dict(use_simulation=True, sim_n_frames=40, sim_size=160, sim_n_particles=6, sim_diffusion=0.5,
             sim_seed=1, max_distance=4.0, n_bootstrap=50)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def drv(app):
    return Driver(app, (1000, 700))


@pytest.fixture(scope="module")
def movie_frames():
    frames, _ = tk.simulate_particle_movie(n_frames=40, shape=(160, 160), n_particles=6, diffusion_coefficient=0.5,
                                           sigma_psf=1.5, amplitude=250.0, background=10.0, seed=1)
    return frames


@pytest.fixture
def tiff(tmp_path, movie_frames):
    tifffile = pytest.importorskip("tifffile")
    path = tmp_path / "movie.tif"
    tifffile.imwrite(str(path), movie_frames.astype(np.float32))
    return path


def dialog_open(drv):
    """Whether a file dialog is on screen (its caption is the window title, which the painter does not draw)."""
    return "Cancel" in drv.draw(1).strings and drv.app.dialog is not None


def use(app, **settings):
    for name, value in settings.items():
        setattr(app.model, name, value)


def tracked(app, drv, **settings):
    """Press the Track button with the real pointer and wait for the worker."""
    use(app, **(settings or SMALL))
    drv.click("track")
    drv.settle()
    return app.model


# ── 1. the numbers: equal to what the Qt window showed ─────────────────────────────────────────────────────────── #


def test_the_track_button_gives_the_numbers_the_qt_window_showed(app, drv):
    m = tracked(app, drv)
    qt = QT_VALUES["simulated"]
    assert m.status_line == qt["status"] == "6 tracks, D = 0.5581 ± 0.098"
    assert m.results_text == qt["results_text"]
    fit = m.result.fit
    assert fit.diffusion_coefficient == pytest.approx(qt["fit"]["D"], rel=1e-12)
    assert fit.diffusion_coefficient_error == pytest.approx(qt["fit"]["D_err"], rel=1e-9)
    np.testing.assert_allclose(np.asarray(fit.msd), qt["fit"]["msd"], rtol=1e-12)
    assert len(m.result.detections) == qt["n_detections"] and len(m.result.tracks) == qt["n_tracks"]
    assert [int(v) for v in m.result.track_lengths()] == qt["track_lengths"]
    assert m.result.tracks_table()[:12] == qt["tracks_table"]
    assert len(m.detection_markers()) == qt["n_markers"]
    assert [s["name"] for s in m.msd_series()] == qt["msd_series_names"]


def test_the_fit_alpha_checkbox_gives_the_qt_numbers_for_the_anomalous_fit(app, drv):
    use(app, **SMALL)
    drv.click("fit_alpha")
    assert app.model.fit_alpha is True
    drv.click("track")
    drv.settle()
    qt = QT_VALUES["fit_alpha"]
    assert app.model.status_line == qt["status"] == "6 tracks, D = 0.5256 ± 0.13"
    assert app.model.result.fit.alpha == pytest.approx(qt["fit"]["alpha"], rel=1e-9)
    assert app.model.result.fit.diffusion_coefficient == pytest.approx(qt["fit"]["D"], rel=1e-9)


def test_the_core_functions_give_the_same_answer_without_the_view_model(movie_frames):
    """A written-out run of the pipeline with the Qt tool's defaults: no shared view model in the path."""
    result = core.analyse(movie_frames, max_distance=4.0, min_track_length=10, n_bootstrap=50, fix_alpha=1.0)
    qt = QT_VALUES["simulated"]
    assert result.fit.diffusion_coefficient == pytest.approx(qt["fit"]["D"], rel=1e-9)
    assert result.fit.diffusion_coefficient == pytest.approx(0.5, rel=0.25)  # the truth the movie was simulated with
    assert result.report() == qt["results_text"]


def test_a_tiff_gives_the_same_tracks_as_the_simulation(app, drv, tiff):
    use(app, max_distance=4.0, n_bootstrap=50)
    app.model.open_path(str(tiff))
    drv.click("track")
    drv.settle()
    assert app.model.status_line == QT_VALUES["file_tracked"]["status"]
    assert app.model.result.fit.diffusion_coefficient == pytest.approx(QT_VALUES["file_tracked"]["fit"]["D"], rel=1e-9)


def test_the_tracks_table_shows_what_the_qt_table_showed(app, drv):
    m = tracked(app, drv)
    qt_rows = QT_VALUES["simulated"]["track_rows_head"]
    shown = [{"track": str(r["track"]), "length": str(r["length"]), "frames": r["frames"], "net": f"{r['net']:.2f}"}
             for r in m.track_table_rows()[:5]]
    assert shown == qt_rows
    drv.click_text("Tracks")  # the tab
    strings = drv.draw(2).strings
    assert {"#", "Points", "Frames", "Net [px]"} <= set(strings)


# ── 2. the live Qt tool on the same data ─────────────────────────────────────────────────────────────────────── #


@pytest.fixture(scope="module")
def qt_tool():
    """The legacy Qt tool, offscreen, on temporary settings. Skipped only when Qt is not installed."""
    if importlib.util.find_spec("qtpy") is None:
        pytest.skip("Qt is not installed")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qtpy import QtWidgets

    from chisurf.plugins.microscopy.img_tracking.gui.tool import ImgTrackingTool

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    tool = ImgTrackingTool()
    tool._qapp = qapp
    yield tool
    tool.close()


def qt_table_cells(tool):
    from qtpy import QtWidgets

    table = next(t for t in tool.findChildren(QtWidgets.QTableWidget) if t.rowCount() or t.columnCount() == 4)
    return [[table.item(r, c).text() for c in range(table.columnCount())] for r in range(table.rowCount())]


SCENARIOS = {"defaults": {}, "quantile detector": {"method": "quantile"}, "anomalous fit": {"fit_alpha": True},
             "tight link": {"max_distance": 2.0, "max_frame_gap": 0}, "short tracks only": {"min_track_length": 30}}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_the_qt_tool_and_the_emtk_app_agree_on_every_result(app, drv, qt_tool, scenario):
    settings = dict(SMALL, **SCENARIOS[scenario])
    qt_tool.model.fit_alpha, qt_tool.model.method = False, "wavelet"
    for name, value in settings.items():
        setattr(qt_tool.model, name, value)
    assert qt_tool.model.compute()
    qt_tool._on_finished(True)
    qt_tool._refresh()
    m = tracked(app, drv, **settings)
    assert m.results_text == qt_tool.model.results_text
    assert m.status_line == qt_tool.statusBar().currentMessage()
    assert m.result.fit.diffusion_coefficient == qt_tool.model.result.fit.diffusion_coefficient
    assert [r["track"] for r in m.track_rows()] == [r["track"] for r in qt_tool.model.track_rows()]
    assert m.track_series() and m.track_series() == qt_tool.model.track_series()
    assert m.msd_series() == qt_tool.model.msd_series() and m.length_series() == qt_tool.model.length_series()
    qt_cells = qt_table_cells(qt_tool)
    emtk_cells = [[str(r["track"]), str(r["length"]), r["frames"], f"{r['net']:.2f}"] for r in m.track_table_rows()]
    assert qt_cells == emtk_cells


@pytest.mark.parametrize("attr", [s["attr"] for s in QT_SPEC["sections"][0]["sections"][0]["sections"][0]["sections"]
                                  if False] or [
    "channel", "max_frames", "sim_n_particles", "sim_n_frames", "sim_size", "sim_seed", "min_area", "max_frame_gap",
    "min_track_length", "n_bootstrap", "max_drawn_tracks", "sim_diffusion", "sim_amplitude", "sim_background",
    "threshold", "min_separation", "max_distance", "pixel_size", "frame_interval"])
def test_typed_extremes_are_clamped_to_the_range_the_qt_spin_box_enforced(app, drv, qt_tool, attr):
    from chisurf.gui.autoform.sections.builtin import ValueWidget

    editors = {vw._section.attr: vw.editor for vw in qt_tool.findChildren(ValueWidget) if getattr(vw, "_section", None)}
    editor = editors[attr]
    drv.draw(2)
    if attr not in app.form.rects:  # fields inside a folded panel
        for fold in ("Simulate instead.fold", "3. Transport.fold"):
            if fold in app.form.rects:
                drv.click(fold)
    from qtpy import QtWidgets

    whole = isinstance(editor, QtWidgets.QSpinBox)
    for qt_value in (1_000_000_000, -5):
        editor.setValue(qt_value if whole else float(qt_value))
        drv.type_into(attr, str(qt_value))
        qt_result = editor.value()  # incl. sim_diffusion: the Qt box shows 4 decimals and rounds its minimum 1e-06 to 0.0, and so does the emtk field
        assert getattr(app.model, attr) == pytest.approx(qt_result, rel=1e-9), (attr, qt_value)


# ── 3. the buttons ─────────────────────────────────────────────────────────────────────────────────────────── #


def test_track_with_nothing_loaded_says_why_and_starts_nothing(app, drv):
    drv.click("track")
    assert app.model.status_line == QT_VALUES["empty_track"]["status"] == "Load an image stack, or tick Simulate."
    assert not app.job.busy and app.model.result is None
    assert QT_VALUES["empty_track"]["status"] in drv.strings()


def test_track_with_a_missing_file_says_which(app, drv, tmp_path):
    app.model.filename = str(tmp_path / "missing.tif")
    drv.click("track")
    assert app.model.status_line == "missing.tif does not exist." == QT_VALUES["missing_file"]["status"]
    assert not app.job.busy


def test_a_corrupt_file_reports_in_the_report_and_keeps_no_stale_movie(app, drv, tmp_path):
    bad = tmp_path / "bad.tif"
    bad.write_bytes(b"not a tiff")
    app.model.open_path(str(bad))
    drv.click("track")
    drv.settle()
    assert app.model.status_line == QT_VALUES["corrupt_file"]["status"]
    assert app.model.results_text.startswith("Could not load the images")
    assert app.model.result is None and app.model.movie_image() is None
    assert "Could not load the images" in " ".join(drv.strings())


def test_the_track_button_is_greyed_while_a_run_is_in_flight(app, drv):
    use(app, **SMALL)
    drv.click("track")
    assert app.job.busy
    runs = []
    app.model.track = lambda: runs.append(1)  # a press now must not even reach the action
    drv.click("track")
    assert runs == []
    drv.settle()


def test_the_settings_form_is_greyed_while_a_run_is_in_flight(app, drv):
    use(app, **SMALL)
    drv.click("track")
    before = app.model.threshold
    drv.click("threshold", fx=0.3)
    assert not app.io.want_capture_keyboard  # the field is greyed: it takes no keys
    drv.type_text("9")
    drv.enter()
    assert app.model.threshold == before
    drv.settle()
    assert app.model.result is not None


def test_open_button_opens_the_file_dialog_and_a_chosen_file_becomes_the_movie(app, drv, tiff):
    app.model.folder = str(tiff.parent)
    drv.click("open_file")
    assert dialog_open(drv) and app.dialog.title == "Open image stack"
    drv.click_text("movie.tif")
    drv.click_text("Open", last=True)
    assert Path(app.model.filename) == tiff
    assert app.model.status_line == "Loaded movie.tif. Press Track."
    assert not dialog_open(drv)
    assert app.model.folder == str(tiff.parent)


def test_open_dialog_cancel_changes_nothing(app, drv, tiff):
    app.model.folder = str(tiff.parent)
    drv.click("open_file")
    drv.click_text("Cancel")
    assert app.model.filename == "" and not dialog_open(drv)


def test_a_path_typed_into_the_field_is_taken_on_enter(app, drv, tiff):
    drv.type_into("filename", str(tiff))
    assert Path(app.model.filename) == tiff
    assert app.model.status_line.startswith("Loaded movie.tif")


def test_a_path_typed_but_not_confirmed_is_not_taken(app, drv, tiff):
    drv.type_into("filename", str(tiff), enter=False)
    assert app.model.filename == ""
    drv.click("max_frames", fx=0.3)  # clicking away commits, as the Qt line edit did on losing focus
    assert Path(app.model.filename) == tiff


def test_dropping_a_file_on_the_window_loads_it(app, drv, tiff):
    assert drv.drop(tiff) is True
    assert Path(app.model.filename) == tiff
    assert app.files_dropped([]) is False  # nothing dropped
    assert Path(app.model.filename) == tiff


def test_dropping_while_a_run_is_in_flight_is_refused(app, drv, tiff):
    use(app, **SMALL)
    drv.click("track")
    assert app.job.busy
    assert app.files_dropped([str(tiff)]) is False and app.model.filename == ""
    drv.settle()


def test_export_without_a_result_says_so(app, drv):
    drv.click("request_export")
    assert app.model.status_line == "Run the tracker first." and not dialog_open(drv)


def test_export_csv_writes_the_file_the_qt_tool_wrote(app, drv, tmp_path, tiff):
    app.model.open_path(str(tiff))
    use(app, max_distance=4.0, n_bootstrap=50)
    drv.click("track")
    drv.settle()
    drv.click("request_export")
    painter = drv.draw(2)
    assert dialog_open(drv) and app.dialog.title == "Export tracks" and "movie.tracks.csv" in painter.strings  # the Qt default name
    drv.click_text("Save", last=True)
    written = tmp_path / "movie.tracks.csv"
    assert written.is_file()
    assert written.read_text() == QT_CSV
    assert app.model.status_line == f"Wrote {written}"


def test_export_csv_to_a_typed_name_appends_the_extension_and_cancel_writes_nothing(app, drv, tmp_path):
    tracked(app, drv)
    app.model.folder = str(tmp_path)
    drv.click("request_export")
    drv.draw(2)
    drv.click_text("Cancel")
    assert not list(tmp_path.glob("*.csv")) and not dialog_open(drv)
    drv.click("request_export")
    drv.draw(2)
    drv.click_text("file name")  # the empty name field's hint: a simulation has no source name to propose
    assert app.io.want_capture_keyboard
    drv.type_text("mytracks")
    drv.click_text("Save", last=True)
    written = tmp_path / "mytracks.csv"
    assert written.is_file() and written.read_text().startswith("track,frame,y,x,intensity")
    assert app.model.status_line == f"Wrote {written}" and not dialog_open(drv)


def test_export_to_an_unwritable_place_reports_instead_of_raising(app, drv, tmp_path):
    tracked(app, drv)
    app.model.write_export(str(tmp_path / "no" / "such" / "dir" / "x.csv"))
    assert app.model.status_line.startswith("Could not write")
    assert "Could not write" in " ".join(drv.strings())


# ── 4. every setting: typing, arrows, toggles, the choice ────────────────────────────────────────────────────── #

SPIN_FIELDS = {
    # attr: (step the Qt spin box moved by, start value)
    "channel": 1, "max_frames": 1, "min_area": 1, "max_frame_gap": 1, "min_track_length": 1, "n_bootstrap": 1,
    "max_drawn_tracks": 1, "threshold": 1.0, "min_separation": 1.0, "max_distance": 1.0, "pixel_size": 1.0,
    "frame_interval": 1.0,
}


def open_all_folds(drv):
    for fold in ("Simulate instead.fold",):
        if fold in drv.app.form.rects:
            drv.click(fold)


@pytest.mark.parametrize("attr", list(SPIN_FIELDS))
def test_each_arrow_steps_its_field_by_the_qt_step(app, drv, attr):
    drv.draw(2)
    start = getattr(app.model, attr)
    x, y, w, h = drv.rect(f"{attr}.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert getattr(app.model, attr) == pytest.approx(start + SPIN_FIELDS[attr]), attr
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    expected = start - SPIN_FIELDS[attr]
    lo = {"channel": 0, "max_frames": 0, "min_area": 1, "max_frame_gap": 0, "min_track_length": 3, "n_bootstrap": 0,
          "max_drawn_tracks": 1, "threshold": 0.5, "min_separation": 0.0, "max_distance": 0.1, "pixel_size": 1e-5,
          "frame_interval": 1e-6}[attr]
    assert getattr(app.model, attr) == pytest.approx(max(expected, lo), abs=1e-5), attr


def test_the_simulation_fields_are_typed_and_clamped(app, drv):
    drv.click("Simulate instead.fold")
    for attr, text, expected in (("sim_diffusion", "2.5", 2.5), ("sim_n_particles", "12", 12), ("sim_n_frames", "1", 2),
                                 ("sim_size", "10000", 2048), ("sim_amplitude", "300", 300.0),
                                 ("sim_background", "-4", 0.0), ("sim_seed", "7", 7)):
        drv.type_into(attr, text)
        assert getattr(app.model, attr) == pytest.approx(expected), attr


def test_simulate_checkbox_and_the_folding_panels_are_clicked(app, drv):
    drv.click("Simulate instead.fold")
    assert "use_simulation" in app.form.rects
    drv.click("use_simulation")
    assert app.model.use_simulation is True
    drv.click("use_simulation")
    assert app.model.use_simulation is False
    for fold in ("1. Detect.fold", "2. Link.fold", "3. Transport.fold", "Movie.fold"):
        assert "threshold" in app.form.rects or fold != "1. Detect.fold"
        drv.click(fold)
    drv.draw(2)
    assert not {"threshold", "max_distance", "pixel_size", "channel"} & set(app.form.rects)  # all four closed
    for fold in ("1. Detect.fold", "2. Link.fold", "3. Transport.fold", "Movie.fold"):
        drv.click(fold)
    assert {"threshold", "max_distance", "pixel_size", "channel"} <= set(drv.draw(2) and app.form.rects)


def test_the_detector_choice_lists_the_two_methods_and_each_can_be_picked(app, drv):
    drv.click("method")
    shown = drv.draw(1).strings
    assert "quantile" in shown and shown.count("wavelet") >= 1
    drv.click_text("quantile", last=True)
    assert app.model.method == "quantile"
    drv.click("method")
    drv.click_text("wavelet", last=True)
    assert app.model.method == "wavelet"


def test_escape_closes_the_open_detector_list_without_choosing(app, drv):
    drv.click("method")
    assert "quantile" in drv.draw(1).strings
    drv.escape()
    assert app.model.method == "wavelet"


# ── 5. the views ──────────────────────────────────────────────────────────────────────────────────────────── #


def test_every_view_says_what_to_do_before_there_is_a_result(app, drv):
    for tab, message in (("Movie", "Press Track (or tick Simulate)"), ("Trajectories", "Press Track: the linked"),
                         ("MSD", "Press Track: the mean squared"), ("Track lengths", "Press Track: the histogram")):
        drv.click_text(tab)
        assert any(s.startswith(message) for s in drv.draw(2).strings), tab


def test_every_view_is_drawn_after_a_run(app, drv):
    tracked(app, drv)
    for tab, expect in (("Movie", {"Z slice", "Play", "Colormap"}), ("Trajectories", {"x / px", "y / px"}),
                        ("MSD", {"lag", "MSD", "measured", "fit"}), ("Track lengths", {"track length / frames", "tracks"}),
                        ("Tracks", {"#", "Points", "Frames", "Net [px]"})):
        drv.click_text(tab)
        strings = set(drv.draw(2).strings)
        assert expect <= strings, (tab, expect - strings)


def test_the_movie_markers_follow_the_frame(app, drv):
    tracked(app, drv)
    drv.click_text("Movie")
    panel = app.panels["movie"]
    assert panel.frame == 0
    x, y, w, h = drv.rect("Z slice") if "Z slice" in app.form.rects else (0, 0, 0, 0)
    marks = app.model.detection_markers()
    on_frame_0 = [m for m in marks if m[0] == 0]
    on_frame_9 = [m for m in marks if m[0] == 9]
    assert len(on_frame_0) == len(on_frame_9) == 6 and on_frame_0 != on_frame_9  # the particles moved


def test_play_advances_the_frames_pause_holds_and_stop_returns_to_the_first(app, drv):
    tracked(app, drv)
    drv.click_text("Movie")
    panel = app.panels["movie"]
    now = [100.0]
    panel.clock = lambda: now[0]
    panel.fps = 8
    drv.click_text("Play")
    assert panel.playing
    for _ in range(3):
        now[0] += 0.25  # 8 fps: two frames per step
        drv.draw(1)
    assert panel.frame == 6
    drv.click_text("Pause")
    held = panel.frame
    now[0] += 5.0
    drv.draw(2)
    assert not panel.playing and panel.frame == held
    drv.click_text("Stop")
    assert panel.frame == 0 and not panel.playing


def test_playback_wraps_when_loop_is_on_and_stops_at_the_last_frame_when_off(app, drv):
    tracked(app, drv)
    drv.click_text("Movie")
    panel = app.panels["movie"]
    now = [0.0]
    panel.clock = lambda: now[0]
    drv.click_text("Play")
    now[0] += 4.5  # 45 frames at 10 fps over a 40-frame movie: wraps to 5
    drv.draw(1)
    assert panel.playing and panel.frame == 5
    drv.click_text("Pause")
    drv.click("movie.loop") if "movie.loop" in app.item_rects else drv.click(panel.rects["loop"])
    assert panel.loop is False
    drv.click_text("Play")
    now[0] += 10.0
    drv.draw(1)
    assert panel.frame == 39 and not panel.playing


def test_the_fps_field_takes_a_typed_speed_and_clamps_to_the_qt_range(app, drv):
    tracked(app, drv)
    panel = app.panels["movie"]
    drv.draw(2)
    for text, expected in (("25", 25), ("500", 120), ("0", 1)):
        drv.click(panel.rects["fps"], fx=0.3)
        assert app.io.want_capture_keyboard
        drv.select_all()
        drv.type_text(text)
        drv.enter()
        assert panel.fps == expected, text


def test_the_fps_arrows_step_by_one_and_stop_at_the_qt_limits(app, drv):
    tracked(app, drv)
    panel = app.panels["movie"]
    drv.draw(2)
    x, y, w, h = panel.form.rects["fps.stepper"]
    drv.click_at(x + w / 2, y + h * 0.25)
    assert panel.fps == 11
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    assert panel.fps == 9
    panel.fps = 120
    drv.click_at(x + w / 2, y + h * 0.25)
    assert panel.fps == 120


def test_the_fps_field_is_greyed_for_a_single_image(app, drv):
    from chisurf.plugins.microscopy.imaging_emtk.views import ImagePanel

    panel = ImagePanel("single", movie=True)
    assert panel.movie and panel.fps == 10 and panel.loop is True and panel.playing is False


def test_the_z_slice_slider_scrubs_the_movie(app, drv):
    tracked(app, drv)
    panel = app.panels["movie"]
    drv.draw(2)
    label = [t for t in drv.painter.texts if t[5] == "Z slice"][0]
    left, y = panel.rects["image"][0], label[1] + label[3] / 2
    drv.click_at(left + 30, y)
    near_start = panel.frame
    assert near_start <= 10
    drv.drag((left + 30, y), (label[0] - 40, y))
    assert panel.frame >= 30
    drv.drag((label[0] - 40, y), (left + 30, y))
    assert panel.frame <= 10


def numeric_ticks(painter):
    return [t for t in painter.strings if t.lstrip("-").replace(".", "").isdigit()]


def test_the_colormap_combo_gamma_and_levels_are_operated(app, drv):
    tracked(app, drv)
    canvas = app.panels["movie"].canvas
    combo = [t for t in drv.draw(2).texts if t[5] == "magma"][0][:4]
    drv.click_at(combo[0] + 10, combo[1] + combo[3] / 2)
    drv.click_text("viridis", last=True)
    assert canvas.colormap == "viridis"
    drv.click_text("Automatic levels")
    assert canvas.auto_levels is False
    assert {"Display minimum", "Display maximum"} <= set(drv.draw(2).strings)  # the manual levels appear
    drv.click_text("Automatic levels")
    assert canvas.auto_levels is True
    gamma = [t for t in drv.draw(2).texts if t[5] == "1.0"][0][:4]
    drv.click_at(gamma[0] + 5, gamma[1] + gamma[3] / 2)  # a click on the slider track sets the gamma
    assert canvas.gamma != 1.0


def test_reset_view_restores_the_image_after_a_pan(app, drv):
    tracked(app, drv)
    drv.draw(3)
    x, y, w, h = app.panels["movie"].rects["image"]
    original = numeric_ticks(drv.draw(2))
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.3))
    panned = numeric_ticks(drv.draw(2))
    assert panned != original
    drv.click_text("Reset view")
    assert numeric_ticks(drv.draw(3)) == original


def test_a_drag_pans_the_trajectory_plot(app, drv):
    tracked(app, drv)
    drv.click_text("Trajectories")
    drv.draw(3)
    x, y, w, h = app.item_rects["Trajectories"]
    before = [s for s in drv.draw(2).strings if s.isdigit()]
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.4))
    after = [s for s in drv.draw(2).strings if s.isdigit()]
    assert before != after


def test_a_drag_pans_the_msd_plot(app, drv):
    tracked(app, drv)
    drv.click_text("MSD")
    drv.draw(3)
    x, y, w, h = app.item_rects["MSD"]
    before = [s for s in drv.draw(2).strings if s.replace(".", "").isdigit()]
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.35, y + h * 0.4))
    after = [s for s in drv.draw(2).strings if s.replace(".", "").isdigit()]
    assert before != after


def table_values(drv, expect):
    """The ``net`` cells in the order they are drawn."""
    return [t[5] for t in drv.draw(2).texts if t[5] in expect]


def header_rect(drv, prefix):
    hits = [t[:4] for t in drv.draw(1).texts if prefix in t[5]]
    assert hits, prefix
    return hits[0]


def test_the_tracks_table_header_sorts_by_value_and_a_row_click_changes_nothing(app, drv):
    tracked(app, drv)
    drv.click_text("Tracks")
    nets = {f"{r['net']:.2f}" for r in app.model.track_table_rows()}
    unsorted = table_values(drv, nets)
    assert len(unsorted) == 6
    drv.click(header_rect(drv, "Net [px]"))
    ascending = table_values(drv, nets)
    assert ascending == sorted(unsorted, key=float)
    drv.click(header_rect(drv, "Net [px]"))
    assert table_values(drv, nets) == sorted(unsorted, key=float, reverse=True)
    before = app.model.export_settings()
    drv.click_text(unsorted[0])
    assert app.model.export_settings() == before and app.model.result is not None


# ── 6. guide, help, persistence, host ────────────────────────────────────────────────────────────────────── #


def test_help_button_opens_the_help_and_its_buttons_work(app, drv):
    drv.click("help")
    assert app.help_window.open
    assert {"Start Guided Tour", "Close"} <= set(drv.draw(2).strings)
    drv.click_text("Close", last=False)
    drv.escape() if app.help_window.open else None
    assert not app.help_window.open


BIG = (1200, 800)


def test_guide_button_starts_the_tour_and_close_tour_ends_it(app):
    drv = Driver(app, BIG)  # the card is clear of the form here; see the xfail below for the overlapping case
    drv.click("guide")
    assert app.tour.active
    drv.click_text("Close Tour")
    assert not app.tour.active


@pytest.mark.xfail(strict=True, reason="emtk gap: a tour card drawn over a control of a window cannot be pressed: the control "
                   "underneath claims the pointer (hovered id) first; see REPORT.md section 10")
def test_the_tour_card_buttons_work_when_the_card_lies_over_a_form_field(app, drv):
    drv.click("guide")
    drv.click_text("Close Tour")
    assert not app.tour.active


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(app, drv):
    drv.click("guide")
    guard = 0
    while app.tour.active and guard < 30:
        guard += 1
        drv.draw(2)
        step = app.tour.steps[app.tour.step_idx]
        target = step.get("target") or {}
        if app.tour.awaiting:
            if target.get("name") == "Simulate instead.fold":
                drv.click("Simulate instead.fold")
            elif target.get("attr") == "use_simulation":
                drv.click("use_simulation")
            elif target.get("name") == "computed":
                use(app, **SMALL)
                drv.click("track")
                drv.settle()
            drv.draw(2)
            assert not app.tour.awaiting, f"{step['title']}: operating the control did not release the step"
        drv.click_text("Finish ✓" if app.tour.step_idx == len(app.tour.steps) - 1 else "Next ►", last=True)
    assert not app.tour.active and app.model.use_simulation and app.model.result is not None


def test_every_guide_target_is_a_drawn_control_or_window(app, drv):
    seen = set()
    for step in app.tour.steps:
        target = step.get("target") or {}
        if not target:
            continue
        app.tour.start(app.tour.steps.index(step))
        key = app.tour._target_key(target)
        drv.draw(3)
        if key == "computed" or key.endswith("fold") or target.get("attr"):
            pass
        rect = app.tour.get_target_rect(key)
        if key in ("Movie", "MSD") and rect is None:
            tracked(app, drv)
            drv.draw(3)
            rect = app.tour.get_target_rect(key)
        if target.get("attr") == "use_simulation" and rect is None:
            drv.click("Simulate instead.fold")
            drv.draw(3)
            rect = app.tour.get_target_rect(key)
        assert rect and rect[2] > 0 and rect[3] > 0, f"{step['title']}: nothing drawn for {key!r}"
        seen.add(key)
    app.tour.stop()
    assert {"Simulate instead.fold", "use_simulation", "method", "max_distance", "computed", "Movie", "MSD",
            "fit_alpha"} <= seen


def test_settings_round_trip_and_invalid_values_are_ignored(app, drv):
    use(app, threshold=7.5, method="quantile", fit_alpha=True, max_frames=12, folder="/tmp")
    saved = json.loads(json.dumps(app.export_settings()))
    other = make_app()
    other.restore_settings(saved)
    assert other.export_settings() == saved and other.model.threshold == 7.5 and other.model.method == "quantile"
    other.restore_settings({"threshold": "high", "method": "nonsense", "fit_alpha": 3, "max_frames": 2.5, "folder": 4})
    assert other.model.threshold == 7.5 and other.model.method == "quantile"
    assert other.model.fit_alpha is True and other.model.max_frames == 12 and other.model.folder == "/tmp"
    other.restore_settings("garbage")  # not a dict: ignored
    assert "filename" not in saved  # the data is never persisted


def test_the_imaging_hub_contract(app, drv):
    app.apply_setup_settings({"detectors": {"a": {}}})
    app.apply_pipeline_context({"source": "/x/y.tif"})
    assert app.model.filename == ""  # the Qt tool adopted neither
    sink = []
    app.model.pipeline_sink = sink.append  # the hub assigns this attribute
    app.set_frame_request_callback(lambda: None)
    app.close()


def test_the_window_draws_empty_and_populated_at_both_sizes(app, drv):
    for size in ((1200, 800), (800, 600)):
        strings = set(drv.draw(3, size).strings)
        assert {"Settings", "Report", "Track", "Open", "Export CSV"} <= strings
    tracked(app, drv)
    for size in ((1200, 800), (800, 600)):
        strings = set(drv.draw(3, size).strings)
        assert any("D = 0.5581" in s for s in strings)


def test_a_worker_that_raises_is_reported_not_swallowed(app, drv, monkeypatch):
    use(app, **SMALL)

    def boom(*a, **k):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(core, "analyse", boom)
    drv.click("track")
    drv.settle()
    assert "detector exploded" in app.model.results_text or "detector exploded" in app.model.status_line


def test_the_idle_window_does_not_ask_for_frames(app, drv):
    drv.draw(3)
    assert not app.animating() or not app.job.busy
    assert app.job.busy is False


# ── 7. the wheel ──────────────────────────────────────────────────────────────────────────────────────────── #


def test_the_wheel_scrolls_the_settings_window_when_the_form_is_taller_than_it(app):
    drv = Driver(app, (800, 400))
    drv.draw(3)
    top = app.form.rects["track"][1]
    drv.wheel(150, 200, -5)
    assert app.form.rects["track"][1] < top
    drv.wheel(150, 200, 8)
    assert app.form.rects["track"][1] == top


@pytest.mark.xfail(strict=True, reason="emtk gap: the wheel does not reach a spin field inside a DockManager window (it does in a plain "
                   "window); see REPORT.md section 10")
def test_the_wheel_over_a_spin_field_steps_it(app, drv):
    x, y, w, h = drv.rect("max_distance")
    start = app.model.max_distance
    drv.wheel(x + w * 0.3, y + h / 2, 1)
    assert app.model.max_distance == pytest.approx(start + 1.0)


@pytest.mark.xfail(strict=True, reason="emtk gap: the wheel never reaches an implot inside a DockManager window, so no docked plot "
                   "can be zoomed with it; see REPORT.md section 10")
def test_the_wheel_zooms_the_trajectory_plot(app, drv):
    tracked(app, drv)
    drv.click_text("Trajectories")
    drv.draw(3)
    before = numeric_ticks(drv.draw(2))
    x, y, w, h = app.item_rects["Trajectories"]
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert numeric_ticks(drv.draw(2)) != before


# ── 8. the spec, the tooltips, no Qt ───────────────────────────────────────────────────────────────────────── #


def walk(sections):
    for section in sections:
        yield section
        yield from walk(section.get("sections", []))


def test_every_spec_key_exists_on_the_model():
    model = make_app().model
    for section in walk(EMTK_SPEC["sections"]):
        options = section.get("options") or {}
        for name in (section.get("attr"), section.get("source"), section.get("call"), section.get("options_source"),
                     options.get("source"), options.get("markers")):
            if name:
                assert hasattr(model, name), (section.get("title"), name)
        for name in (section.get("call"), section.get("options_source"), options.get("source"), options.get("markers")):
            if name:
                assert callable(getattr(model, name)) or name in ("report_text",), name
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        for column in options.get("columns", []):
            assert column["key"] in ("track", "length", "frames", "net")


def test_every_qt_setting_is_in_the_emtk_spec_with_the_same_range():
    def values(sections):
        return {s["attr"]: s for s in walk(sections) if s.get("type") in ("value", "toggle", "choice") and s.get("attr")}

    qt, emtk = values(QT_SPEC["sections"]), values(EMTK_SPEC["sections"])
    assert set(qt) == set(emtk), set(qt) ^ set(emtk)
    for attr, spec in qt.items():
        for key in ("minimum", "maximum", "decimals", "label"):
            assert spec.get(key) == emtk[attr].get(key), (attr, key)
        assert emtk[attr].get("description") == spec.get("description"), attr


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("img_tracking"))
    assert inventory["controls_without_tooltip"] == []
    for section in walk(EMTK_SPEC["sections"]):
        if section.get("type") in ("value", "choice", "toggle", "table", "custom", "panel", "info"):
            assert section.get("description"), section.get("attr") or section.get("title")
        for column in (section.get("options") or {}).get("columns", []):
            assert column.get("description"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_the_populated_window_has_a_tooltip_on_every_control_too(app, drv):
    from test.gui.emtk_port_parity import ControlRecorder

    tracked(app, drv)
    recorder = ControlRecorder()
    with recorder.installed():
        for _ in range(3):
            recorder.rows.clear()
            drv.draw(1)
    missing = sorted({f"{r['kind']}: {r['label']}" for r in recorder.rows if not r["tooltip"]})
    assert missing == [], missing


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("img_tracking")
    assert result["ok"], result["output"]


def test_the_qt_host_delivers_a_dropped_file_to_the_app(app, tiff):
    pytest.importorskip("qtpy")
    from emtk.qt_host import ControlHost
    from qtpy import QtCore, QtGui, QtWidgets

    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    host = ControlHost(app)
    host.resize(900, 600)
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(str(tiff))])
    enter = QtGui.QDragEnterEvent(QtCore.QPoint(10, 10), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    host.dragEnterEvent(enter)
    assert enter.isAccepted(), "the host refused the drag: the app has no drop hook"
    drop = QtGui.QDropEvent(QtCore.QPointF(10, 10), QtCore.Qt.CopyAction, mime, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier)
    host.dropEvent(drop)
    assert Path(app.model.filename) == tiff and qapp is not None
    host.close()
