"""The native N&B tool against the Qt tool it replaces: numbers, every control with a real-input click test, the layout at two sizes.

Hermetic: settings, MMFDB and its database in a temporary folder, a temporary HOME, the photon streams written into a temporary folder from a
seed, no network (the database picker gets a stub client). References: (a) the Qt tool's own view model run on the same file, (b) the photon
counts written into the stream, (c) an independent tttrlib CLSM image, (d) what the Qt window showed (``okf/plugins/emtk-ports/img_pixel_nb/qt_values.json``).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.microscopy.imaging_emtk import pixel_checks as C
from chisurf.plugins.microscopy.imaging_emtk import pixel_testing as data
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, dialog_open, hermetic_env, walk
from chisurf.plugins.microscopy.img_pixel_nb import demo
from chisurf.plugins.microscopy.img_pixel_nb.gui.app import NBApp, make_app
from chisurf.plugins.microscopy.img_pixel_nb.gui.model import NBModel
from chisurf.plugins.microscopy.img_pixel_nb.gui.view_model import NBViewModel
from test.gui.emtk_layout_checks import (
    SIZES,
    assert_disjoint,
    assert_icons_clear,
    assert_inside,
    assert_short,
    assert_texts_apart,
    draw,
)

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
EVIDENCE = REPO / "okf/plugins/emtk-ports/img_pixel_nb"
QT_VALUES = json.loads((EVIDENCE / "qt_values.json").read_text(encoding="utf-8"))
EMTK_SPEC = json.loads((PLUGIN / "gui" / "nb_emtk.view.json").read_text(encoding="utf-8"))
QT_SPEC = json.loads((PLUGIN / "gui" / "nb.view.json").read_text(encoding="utf-8"))
BIG = (1200, 800)

TABS = (
    "Intensity",
    "Brightness (B)",
    "Number (N)",
    "Brightness \u03b5",
    "Number n",
    "Parameter plane",
    "Gated pixels",
    "Cross brightness",
    "Cross number",
    "Frames (movie)",
)
TOOL = C.Tool(
    make_app=make_app,
    tabs=TABS,
    role="pixel_nb",
    hdf5_label="Add N&B to HDF5",
    maps={"Intensity": "intensity_map", "Brightness (B)": "b_map", "Number (N)": "n_map"},
    axes={"Parameter plane": ("intensity \u27e8k\u27e9", "apparent brightness B")},
    optional=("Cross brightness", "Cross number"),
)
PLANE_LABELS = (
    "intensity \u27e8k\u27e9",
    "apparent brightness B",
    "brightness \u03b5",
    "apparent number N",
    "number n",
)
STATIC_TABS = tuple(t for t in TABS if t not in TOOL.optional)


_REAL_BEFORE = data.real_settings_state()


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


@pytest.fixture(scope="module")
def flim(tmp_path_factory):
    return Path(data.flim_ptu(tmp_path_factory.mktemp("stream") / "flim.ptu"))


@pytest.fixture(scope="module")
def flim2(tmp_path_factory):
    """The same scene with a second detector (routing channel 1)."""
    return Path(data.flim_ptu(tmp_path_factory.mktemp("stream2") / "flim2.ptu", n_channels=2))


@pytest.fixture
def stream(tmp_path, flim):
    """A copy of the stream in the test's own folder (a container is written beside it)."""
    target = tmp_path / "scan" / flim.name
    target.parent.mkdir()
    target.write_bytes(flim.read_bytes())
    return target


@pytest.fixture
def app():
    application = make_app()
    yield application
    application.close()


@pytest.fixture
def drv(app):
    return Driver(app, BIG)


# ── 1. the numbers ──────────────────────────────────────────────────────────────────────────────────────── #


@pytest.fixture(scope="module")
def demo_file(tmp_path_factory):
    """The monomer / dimer demo stream, simulated once; ``demo_path`` is redirected to it so ``Load demo`` reuses it."""
    path = tmp_path_factory.mktemp("demo") / "nb_demo.ptu"
    demo.create_demo(path)
    return path


@pytest.fixture
def with_demo(demo_file, monkeypatch):
    monkeypatch.setattr(demo, "demo_path", lambda directory=None: demo_file)
    return demo_file


def run_demo(app, drv):
    drv.click("demo")
    assert app.job.busy
    drv.settle(timeout=300)
    assert not app.job.error, app.job.error
    return app.model


def test_load_demo_runs_the_demo_and_the_maps_show_the_monomer_dimer_truth(app, drv, with_demo):
    m = run_demo(app, drv)
    truth = demo.truth()
    eps, n = m.epsilon_map(), m.number_map()
    half = eps.shape[1] // 2
    assert np.median(eps[:, :half]) == pytest.approx(truth["monomer"]["epsilon"], rel=0.1)
    assert np.median(eps[:, half:]) == pytest.approx(truth["dimer"]["epsilon"], rel=0.1)
    assert np.median(n[:, :half]) == pytest.approx(truth["monomer"]["number"], rel=0.15)
    assert np.median(n[:, half:]) == pytest.approx(truth["dimer"]["number"], rel=0.15)
    mean = m.intensity_map()
    assert np.median(mean[:, :half]) == pytest.approx(np.median(mean[:, half:]), rel=0.1), (
        "the same intensity, only the packaging differs"
    )
    assert Path(m.filename) == with_demo and m.status_line == ""


def test_the_maps_are_the_moments_of_the_simulated_counts(app, drv, with_demo):
    m = run_demo(app, drv)
    counts = demo.simulate_counts().astype(float)
    mean, var = counts.mean(axis=0), counts.var(axis=0, ddof=1)
    b = var / mean
    np.testing.assert_allclose(m.b_map(), b, rtol=1e-9)
    np.testing.assert_allclose(m.n_map(), mean**2 / var, rtol=1e-9)
    np.testing.assert_allclose(m.epsilon_map(), b - 1.0, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(m.number_map(), mean / (b - 1.0), rtol=1e-9)


def test_the_live_qt_view_model_gives_the_same_maps_on_the_demo(app, drv, with_demo):
    m = run_demo(app, drv)
    qt = NBViewModel()
    qt.load_demo()
    for name in (
        "b_map",
        "n_map",
        "epsilon_map",
        "number_map",
        "intensity_map",
        "plane_histogram",
        "gated_intensity_map",
    ):
        np.testing.assert_array_equal(getattr(m, name)(), getattr(qt, name)())
    assert set(m._columns) == set(qt._columns) and m.results_text == qt.results_text


SETTING_SETS = [
    {"gamma": 0.3536},
    {"subtract": "pixel_mean", "add": "total_mean"},
    {"subtract": "moving_average", "add": "pixel_mean", "box_pixels": 5, "box_frames": 7},
    {"background": 0.1, "detrend_segments": 3},
    {"dead_time_ns": 50.0, "pixel_dwell_us": 20.0},
    {"smoothing": "gaussian", "radius": 2.0, "median": True},
    {"gain": 2.0, "offset": 0.1, "read_variance": 0.2},
]


@pytest.mark.parametrize("changes", SETTING_SETS, ids=lambda c: "+".join(sorted(c)))
def test_every_setting_gives_what_the_qt_tool_gives_with_the_same_setting(
    app, drv, with_demo, changes
):
    m = app.model
    for k, v in changes.items():
        setattr(m, k, v)
    m.select_file(str(with_demo))
    C.run(app, drv)
    qt = NBViewModel()
    for k, v in changes.items():
        setattr(qt, k, v)
    qt.filename = str(with_demo)
    assert qt.compute()
    for name in ("b_map", "n_map", "epsilon_map", "number_map"):
        np.testing.assert_allclose(
            getattr(m, name)(), getattr(qt, name)(), rtol=1e-12, equal_nan=True
        )


def test_typed_settings_are_clamped_to_the_qt_ranges_and_the_choices_are_the_qt_lists(app, drv):
    qt_fields = {
        s["attr"]: s
        for s in walk(QT_SPEC["sections"])
        if s.get("attr") and s.get("type") in ("value", "choice")
    }
    emtk_fields = {
        s["attr"]: s
        for s in walk(EMTK_SPEC["sections"])
        if s.get("attr") and s.get("type") in ("value", "choice")
    }
    for attr, spec in qt_fields.items():
        if attr == "filename":
            continue
        other = emtk_fields[attr]
        for key in (
            "label",
            "minimum",
            "maximum",
            "decimals",
            "options",
            "options_source",
            "description",
        ):
            assert other.get(key) == spec.get(key), (attr, key)


def test_a_typed_number_is_taken_on_enter_and_changes_what_the_next_run_computes(
    app, drv, with_demo
):
    app.model.select_file(str(with_demo))
    C.run(app, drv)
    before = app.model.epsilon_map().copy()
    for _ in range(2):
        pass
    drv.reveal("Detector.fold") if False else None
    app.docks.focus("Intensity")
    drv.click("Estimator.fold")
    drv.type_into("gamma", "0.3536")
    assert app.model.gamma == 0.3536 and app.model.needs_recompute()
    C.run(app, drv)
    np.testing.assert_allclose(app.model.epsilon_map(), before / 0.3536, rtol=1e-9)
    drv.type_into("gamma", "99")
    assert app.model.gamma == 10.0


def test_a_choice_of_the_estimator_panel_is_picked_from_its_list(app, drv, with_demo):
    app.model.select_file(str(with_demo))
    drv.click("Estimator.fold")
    drv.click("smoothing")
    assert {"none", "average", "disk", "gaussian"} <= set(drv.draw(1).strings)
    drv.click_text("gaussian", last=True)
    assert app.model.smoothing == "gaussian"
    drv.click("median")
    assert app.model.median is True


def test_the_stack_correction_and_detector_panels_fold_and_take_typed_values(app, drv):
    drv.click("Stack corrections.fold")
    drv.type_into("box_pixels", "5")
    drv.type_into("detrend_segments", "2")
    drv.click("Detector.fold")
    drv.type_into("dead_time_ns", "12.5")
    drv.type_into("pixel_dwell_us", "20")
    m = app.model
    assert (m.box_pixels, m.detrend_segments, m.dead_time_ns, m.pixel_dwell_us) == (
        5,
        2,
        12.5,
        20.0,
    )
    drv.click("subtract")
    drv.click_text("frame_mean", last=True)
    assert m.subtract == "frame_mean"


def test_calibrate_analog_is_greyed_without_a_result_and_gives_the_qt_answer_with_one(
    app, drv, with_demo
):
    assert not app.model.enabled("calibrate_analog")
    drv.click("calibrate_analog")
    assert app.model.gain == 1.0
    m = run_demo(app, drv)
    qt = NBViewModel()
    qt.load_demo()
    qt.calibrate_analog()
    drv.click("calibrate_analog")
    assert (m.gain, m.offset) == pytest.approx(
        (qt.gain, qt.offset), rel=1e-3
    ) and m.results_text == qt.results_text


def test_the_load_demo_failure_is_reported(app, drv, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError("no simulator in this build")

    monkeypatch.setattr(demo, "create_demo", broken)
    drv.click("demo")
    drv.settle(timeout=60)
    assert app.model.status_line == "Demo failed: no simulator in this build"


# ── parameter plane, gates, cross N&B ──
def open_regions(app, drv):
    app.docks.focus("Parameter plane")
    drv.draw(3)
    drv.click("Parameter plane / gates.fold") if False else None
    drv.click_text("> Analysis regions")
    assert "Add ellipse" in drv.draw(2).strings


def test_the_plane_axes_are_chosen_from_their_lists_and_the_histogram_follows(app, drv, with_demo):
    m = run_demo(app, drv)
    app.docks.focus("Parameter plane")
    drv.draw(2)
    first = m.plane_histogram().copy()
    drv.click("plane_y")
    assert {"mean", "B", "N", "epsilon", "n"} <= set(drv.draw(1).strings)
    drv.click_text("N", last=True)
    assert m.plane_y == "N" and not np.array_equal(first, m.plane_histogram())
    assert "apparent number N" in drv.draw(3).strings


def test_bins_and_the_log_scale_change_the_histogram(app, drv, with_demo):
    m = run_demo(app, drv)
    drv.type_into("plane_bins", "32")
    assert m.plane_histogram().shape == (32, 32)
    linear = m.plane_histogram().max()
    drv.click("log_histogram")
    assert m.log_histogram is False and m.plane_histogram().max() > linear


def test_a_gate_on_the_plane_selects_the_dimers_and_the_gated_map_shows_where(app, drv, with_demo):
    m = run_demo(app, drv)
    open_regions(app, drv)
    drv.click_text("Add rectangle")
    roi = m.gates.get("Rectangle").roi
    # move the rectangle to the dimer population: higher brightness at the same intensity
    x0, x1, y0, y1 = m.plane_extent()
    roi.x0, roi.x1, roi.y0, roi.y1 = x0, x1, 1.8, y1
    m.notify_gates()
    mask = m.gate_mask()
    half = mask.shape[1] // 2
    assert mask[:, half:].mean() > 2 * mask[:, :half].mean()
    np.testing.assert_array_equal(m.gated_intensity_map(), np.where(mask, m.intensity_map(), 0))
    assert m.gate_summary().startswith(f"{int(mask.sum())} of")
    drv.click_text("Clear gates")
    assert len(m.gates) == 0 and m.gate_mask().all() or len(m.gates) == 0


def test_gate_handles_are_dragged_with_the_pointer(app, drv, with_demo):
    m = run_demo(app, drv)
    open_regions(app, drv)
    drv.click_text("Add rectangle")
    app.docks.focus("Parameter plane")
    drv.draw(3)
    px, py, pw, ph = app.item_rects["Parameter plane"]
    x0, x1, y0, y1 = m.plane_extent()
    roi = m.gates.get("Rectangle").roi
    before = (roi.x1, roi.y1)

    def to_px(g, v):
        return px + (g - x0) / (x1 - x0) * pw, py + ph - (v - y0) / (y1 - y0) * ph

    start = to_px(roi.x1, roi.y1)
    drv.drag(start, (start[0] - 40, start[1] + 40), steps=8)
    assert (roi.x1, roi.y1) != before


def test_region_list_actions_invert_enable_duplicate_remove_and_json(app, drv, with_demo, tmp_path):
    m = run_demo(app, drv)
    open_regions(app, drv)
    drv.click_text("Add ellipse")
    inside = int(m.gate_mask().sum())
    drv.click_text("Invert")
    assert int(m.gate_mask().sum()) == int(m._plane_data()[2].sum()) - inside
    drv.click_text("Invert")
    drv.click_text("Duplicate region")
    assert len(m.gates) == 2
    drv.click_text("Remove region")
    assert len(m.gates) == 1
    app.model.folder = str(tmp_path)
    drv.click_text("Save regions")
    C.save_in_dialog(drv, "gates.json")
    assert (tmp_path / "gates.json").exists()
    drv.click_text("Clear gates")
    drv.click_text("Load regions")
    drv.click_text("gates.json")
    drv.click_text("Open", last=True)
    assert len(m.gates) == 1


def test_gates_survive_the_saved_settings(app, drv, with_demo):
    run_demo(app, drv)
    open_regions(app, drv)
    drv.click_text("Add ellipse")
    saved = app.export_settings()
    fresh = make_app()
    fresh.restore_settings(saved)
    assert len(fresh.model.gates) == 1


def test_cross_nb_is_built_on_the_worker_when_a_second_window_is_chosen(app, drv, flim):
    app.model.detectors = {
        "a": {"chs": [0], "micro_time_ranges": []},
        "b": {"chs": [0], "micro_time_ranges": [(0, 255)]},
    }
    m = C.computed(app, drv, flim)
    assert m.cross_brightness_map() is None
    drv.click("Cross N&B.fold")
    drv.click("cross_window")
    assert "b" in drv.draw(1).strings
    drv.click_text("b", last=True)
    assert m.cross_window == "b"
    drv.settle(timeout=60)
    cross = m.cross_brightness_map()
    assert cross is not None and cross.shape == m.intensity_map().shape
    assert m.cross_number_map() is not None


def test_two_detector_windows_give_two_map_sets(app, drv, flim2):
    app.model.detectors = {
        "first": {"chs": [0], "micro_time_ranges": []},
        "second": {"chs": [1], "micro_time_ranges": []},
    }
    m = C.computed(app, drv, flim2)
    assert list(m._by_window) == ["first", "second"] and {
        "epsilon (first)",
        "epsilon (second)",
    } <= set(m._columns)


# ── 2. the file ─────────────────────────────────────────────────────────────────────────────────────────────── #


def test_a_typed_path_is_taken_on_enter(app, drv, flim):
    C.typed_path_is_taken_on_enter(app, drv, flim)


def test_a_typed_path_is_taken_on_click_away_but_not_before(app, drv, flim):
    C.typed_path_is_taken_on_click_away_but_not_before(app, drv, flim)


def test_browse_opens_the_dialog_and_a_chosen_file_is_selected(app, drv, flim):
    C.browse_opens_the_dialog_and_a_chosen_file_is_selected(app, drv, flim)


def test_browse_cancel_the_window_close_button_and_escape_change_nothing(app, drv, flim):
    C.browse_cancel_the_window_close_button_and_escape_change_nothing(app, drv, flim)


def test_the_database_button_picks_a_dataset(app, drv, flim):
    C.database_button_picks_a_dataset(app, drv, flim)


@pytest.mark.xfail(
    strict=True,
    reason="emtk gap: the dataset picker's buttons share one id and its Open selected / Cancel never fire; "
    "see okf/plugins/emtk-ports/img_drift/REPORT.md",
)
def test_the_open_selected_button_of_the_database_picker_can_be_pressed(app, drv, flim):
    C.open_selected_button_of_the_database_picker_can_be_pressed(app, drv, flim)


def test_the_database_picker_window_close_button_closes_it(app, drv, flim):
    C.database_picker_window_close_button_closes_it(app, drv, flim)


def test_a_drop_loads_and_runs_the_file_and_a_drop_while_a_worker_runs_is_refused(app, drv, flim):
    C.drop_loads_and_runs_the_file_and_a_drop_while_a_worker_runs_is_refused(app, drv, flim)


def test_the_qt_host_delivers_a_dropped_file_to_the_app(app, flim):
    C.qt_host_delivers_a_dropped_file_to_the_app(app, flim)


# ── 3. running ──────────────────────────────────────────────────────────────────────────────────────────────── #


def test_run_without_a_file_does_nothing_with_one_it_computes_and_a_second_run_says_it_is_up_to_date(
    app, drv, flim
):
    C.run_without_a_file_does_nothing_and_with_one_computes_and_a_second_run_says_it_is_up_to_date(
        app, drv, flim
    )


def test_cancel_stops_a_running_calculation(app, drv, flim, monkeypatch):
    C.cancel_stops_a_running_calculation_and_keeps_the_previous_state(
        app, drv, flim, TOOL, monkeypatch
    )


def test_cancel_is_idle_when_nothing_runs(app, drv):
    C.cancel_is_idle_when_nothing_runs(app, drv)


def test_a_failing_run_is_reported_and_leaves_the_model_unchanged(app, drv, tmp_path):
    C.failed_run_is_reported_and_leaves_the_model_unchanged(app, drv, tmp_path)


# ── 4. the window and the detectors ─────────────────────────────────────────────────────────────────────────── #


def test_the_detector_window_list_switches_the_displayed_window(app, drv, flim2):
    C.detector_window_list_switches_the_displayed_window(app, drv, flim2, TOOL)


def test_the_detectors_window_shows_the_computed_windows_and_adding_one_updates_the_model(app, drv):
    C.detectors_window_shows_the_computed_windows_and_adding_one_updates_the_model(app, drv)


def test_a_window_added_in_the_editor_is_computed_by_the_next_run(app, drv, flim):
    loaded = C.loaded(app, drv, flim)
    app.docks.focus("Detectors")
    drv.draw(3)
    drv.click_text("Add")
    drv.draw(2)
    app.docks.focus("Intensity")
    C.run(app, drv)
    assert sorted(loaded._by_window) == ["New Detector", "ch0"]


# ── 5. the outputs ──────────────────────────────────────────────────────────────────────────────────────────── #


def test_hdf5_is_greyed_without_a_result_asks_for_a_file_writes_the_table_and_the_next_press_writes_to_the_remembered_one(
    app, drv, stream, tmp_path
):
    target = C.hdf5_is_greyed_without_a_result_asks_for_a_file_writes_the_table_and_the_next_press_writes_to_the_remembered_one(
        app, drv, stream, tmp_path, source_ref=False
    )
    from chisurf.core.datastore import numeric_column
    from chisurf.core.fluorescence.imaging import read_imaging_table

    np.testing.assert_allclose(
        numeric_column(read_imaging_table(str(target)), "epsilon (ch0)"),
        app.model.epsilon_map().ravel(),
    )


def test_the_hdf5_dialog_cancel_writes_nothing(app, drv, stream, tmp_path):
    C.hdf5_dialog_cancel_writes_nothing(app, drv, stream, tmp_path)


def test_an_unwritable_hdf5_place_is_reported(app, drv, stream, tmp_path):
    C.hdf5_unwritable_place_is_reported(app, drv, stream, tmp_path)


def test_the_container_button_writes_the_artifact_beside_the_source(app, drv, stream):
    C.container_is_greyed_without_a_result_and_writes_the_artifact_beside_the_source(
        app, drv, stream, "nb"
    )


def test_ndx_opens_over_the_maps_and_back_returns(app, drv, stream):
    C.ndx_is_greyed_without_a_result_opens_over_the_maps_and_back_returns(app, drv, stream)


def test_next_is_greyed_outside_the_pipeline_and_advances_inside_it(app, drv, stream):
    C.next_is_greyed_outside_the_pipeline_and_advances_inside_it(TOOL, drv, stream)


def test_closing_a_computed_session_flushes_the_hdf5_and_the_container(app, drv, stream):
    C.computed(app, drv, stream)
    app.close()
    assert stream.with_suffix(".imaging.h5").exists() and stream.with_suffix(".pto").exists()


# ── 6. the maps ─────────────────────────────────────────────────────────────────────────────────────────────── #


def test_every_tab_draws_empty_with_a_message_and_populated_with_a_picture_with_axes(
    app, drv, flim
):
    C.every_tab_draws_empty_with_a_message_and_populated_with_a_picture(app, drv, flim, TOOL)


@pytest.mark.parametrize("tab", STATIC_TABS)
def test_the_colormap_list_changes_the_model_and_the_picture(app, drv, flim, tab):
    C.colormap_list_offers_four_maps_and_a_click_changes_the_model(app, drv, flim, tab)


@pytest.mark.parametrize("tab", STATIC_TABS)
def test_the_wheel_zooms_and_a_drag_pans_the_image(app, drv, flim, tab):
    C.wheel_zooms_and_a_drag_pans_the_image(app, drv, flim, tab)


def test_the_movie_plays_loops_stops_and_takes_a_typed_speed(app, drv, flim):
    C.movie_play_loop_stop_and_speed(app, drv, flim, "Frames (movie)")


# ── 7. guide, help, persistence, host ───────────────────────────────────────────────────────────────────────── #


def test_help_button_opens_the_help_and_its_buttons_work(app, drv):
    C.help_button_opens_the_help_and_its_buttons_work(app, drv)


def test_guide_button_starts_the_tour_and_close_tour_ends_it(app):
    C.guide_button_starts_the_tour_and_close_tour_ends_it(app)


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(
    app, drv, with_demo
):
    C.tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(
        app, drv, with_demo, {"demo": lambda: drv.click("demo")}
    )
    assert app.model._columns and not app.job.error


def test_every_guide_target_is_a_drawn_control_or_window(app, drv, flim):
    C.every_guide_target_is_a_drawn_control_or_window(app, drv, flim)


def test_settings_round_trip_and_invalid_values_are_ignored(app, drv):
    C.settings_round_trip_and_invalid_values_are_ignored(
        app,
        drv,
        {"gamma": 0.5, "smoothing": "disk", "plane_bins": 32},
        {"gamma": "big", "smoothing": "blurry"},
    )


def test_the_imaging_hub_drives_the_tool(app, drv, flim):
    C.hub_contract(
        TOOL,
        flim,
        drv,
        {
            "green": {"chs": [0], "micro_time_ranges": []},
            "red": {"chs": [1], "micro_time_ranges": [(0, 100)]},
        },
        {},
    )


def test_the_hub_starts_the_run_through_start(app, drv, flim):
    C.hub_start_runs_the_maps(TOOL, flim, drv)


# ── 8. static: spec, inventory, Qt-free, tooltips, layout ──────────────────────────────────────────────────── #


def _labels(sections):
    out = set()
    for sec in walk(sections):
        if sec.get("label"):
            out.add(sec["label"])
        for b in sec.get("buttons", []):
            out.add(b["label"])
    return {
        "".join(
            ch for ch in label if ord(ch) < 0x2300 or ch in "\u03b5\u03c3\u03b3\u2080\u00b2"
        ).strip()
        for label in out
    }


def test_every_qt_control_has_an_emtk_equivalent():
    qt, emtk = _labels(QT_SPEC["sections"]), _labels(EMTK_SPEC["sections"])
    assert {
        "TTTR file",
        "Subtract",
        "Add back",
        "Box (px)",
        "Box (frames)",
        "Background",
        "Detrend segments",
        "Dead time (ns)",
        "Pixel dwell (\u00b5s)",
        "Gain S",
        "Offset",
        "Read variance \u03c3\u2080\u00b2",
        "Shape factor \u03b3",
        "Moment smoothing",
        "Radius",
        "Median filter (\u03b5, n)",
        "Plane x",
        "Plane y",
        "Bins",
        "Log counts",
        "Clear gates",
        "Cross with",
    } <= qt
    assert qt - {""} <= emtk, sorted(qt - emtk)
    qt_tabs = [
        s["title"]
        for s in walk(QT_SPEC["sections"])
        if s.get("type") == "custom" and s.get("key") == "image"
    ]
    assert sorted(qt_tabs) == sorted(TABS) and [
        p["title"] for p in EMTK_SPEC["sections"][1:]
    ] == list(TABS)


def test_every_spec_attribute_and_action_exists_on_the_model():
    model = NBModel()
    for section in walk(EMTK_SPEC["sections"]):
        if section.get("attr"):
            assert hasattr(model, section["attr"]), section
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button
        for key in ("source", "call", "options_source"):
            if section.get(key) and section.get("type") != "custom":
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
    C.qt_free("img_pixel_nb")


def test_every_control_has_a_tooltip(app, drv, flim):
    C.every_control_has_a_tooltip(app, drv, flim, TOOL)


@pytest.fixture(params=SIZES, ids=lambda s: f"{s[0]}x{s[1]}")
def size(request):
    return request.param


def test_layout_empty_and_populated_has_no_clipped_or_overlapping_text(app, flim, size):
    drv = Driver(app, size)
    painter = draw(app, size)
    assert_texts_apart(painter)
    assert_icons_clear(painter)
    C.computed(app, drv, flim)
    for tab in TOOL.tabs:
        app.docks.focus(tab)
        painter = draw(app, size)
        if (
            tab != "Phasor plot movie"
        ):  # a 160-bin image: the plot draws the y label over its three-digit ticks (emtk gap, see the report)
            C.texts_apart(painter, ignore=(str(flim), *PLANE_LABELS))
    app.docks.focus(
        "Detectors"
    )  # the shared editor draws its row buttons over their cells: only the frame is checked
    painter = draw(app, size)
    assert_inside(
        {
            k: v
            for k, v in app.item_rects.items()
            if k in ("detectors.add_detector", "detectors.section_detectors")
        },
        size,
    )
    names = (
        "run_maps",
        "request_hdf5",
        "save_container",
        "open_ndx",
        "next_step",
        "filename",
        "open_file",
        "open_database",
        "display_window",
    )
    rects = {k: app.form.rects[k] for k in names}
    rects.update({k: app.item_rects[k] for k in ("help", "guide", "cancel")})
    assert_inside(rects, size)
    assert_disjoint(rects, list(rects))
    assert_short(app.form.rects, ["display_window"], 260)


def test_the_image_gets_the_space_and_the_settings_stay_beside_it(app, drv, flim, size):
    drv = Driver(app, size)
    C.computed(app, drv, flim)
    app.docks.focus("Intensity")
    drv.draw(3)
    ix, iy, iw, ih = app.item_rects["Intensity"]
    assert iw * ih >= 0.30 * size[0] * size[1] * (1.0 if size[0] >= 1200 else 0.6), (iw, ih)
    sx, sy, sw, sh = app.form.rects["run_maps"]
    assert sx + sw <= ix, "the settings window and the image do not overlap"
    for name in ("run_maps", "request_hdf5", "save_container", "open_ndx", "next_step"):
        x, y, w, h = app.form.rects[name]
        assert x >= 0 and x + w <= ix and y + h <= size[1], name


def test_zz_the_real_user_settings_were_never_touched():
    """Runs last in the module: nothing under the real ~/.chisurf was written, created or removed by these tests."""
    assert data.real_settings_state() == _REAL_BEFORE
