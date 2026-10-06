"""The native mean micro-time tool against the Qt tool it replaces: numbers, every control with a real-input click test, the layout at two sizes.

Hermetic: settings, MMFDB and its database in a temporary folder, a temporary HOME, the photon streams written into a temporary folder from a
seed, no network (the database picker gets a stub client). References: (a) the Qt tool's own view model run on the same file, (b) the photon
counts written into the stream, (c) an independent tttrlib CLSM image, (d) what the Qt window showed (``okf/plugins/emtk-ports/img_pixel_micro_time/qt_values.json``).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.microscopy.imaging_emtk import pixel_checks as C
from chisurf.plugins.microscopy.imaging_emtk import pixel_testing as data
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, hermetic_env, walk
from chisurf.plugins.microscopy.img_pixel_micro_time.gui.app import MicroTimeApp, make_app
from chisurf.plugins.microscopy.img_pixel_micro_time.gui.model import MicroTimeModel
from chisurf.plugins.microscopy.img_pixel_micro_time.gui.view_model import MicroTimeViewModel
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
EVIDENCE = REPO / "okf/plugins/emtk-ports/img_pixel_micro_time"
QT_VALUES = json.loads((EVIDENCE / "qt_values.json").read_text(encoding="utf-8"))
EMTK_SPEC = json.loads((PLUGIN / "gui" / "micro_time_emtk.view.json").read_text(encoding="utf-8"))
QT_SPEC = json.loads((PLUGIN / "gui" / "micro_time.view.json").read_text(encoding="utf-8"))
BIG = (1200, 800)

TOOL = C.Tool(
    make_app=make_app,
    tabs=("Intensity", "Mean micro-time (ns)", "Mean micro-time movie"),
    role="pixel_micro_time",
    hdf5_label="Add mean micro-time to HDF5",
    maps={
        "Intensity": "intensity_map",
        "Mean micro-time (ns)": "mean_micro_time_map",
        "Mean micro-time movie": "mean_micro_time_frames",
    },
)


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


# ── 1. the numbers ──────────────────────────────────────────────────────────────────────────────────────────── #


def test_the_maps_match_the_stream_the_qt_numbers_and_the_expected_arrival_times(app, drv, flim):
    m = C.computed(app, drv, flim)
    truth = data.counts(1)[0]
    np.testing.assert_array_equal(m.intensity_map(), truth.sum(axis=0))
    mt = m.mean_micro_time_map()
    assert mt.shape == (32, 32) and mt.min() >= 0
    # the stream's decays: 1 ns on the left half, 3 ns on the right, 0.64 ns electronics offset, 8.2 ns window (clipped at the last bin)
    left, right = mt[:, :16].mean(), mt[:, 16:].mean()
    assert (
        left == pytest.approx(1.62, rel=0.04)
        and right == pytest.approx(3.38, rel=0.04)
        and right > 2 * left * 0.9
    )
    qt = QT_VALUES["mean_micro_time_map"]
    assert (
        float(mt.sum()) == pytest.approx(qt["sum"], rel=1e-12)
        and mt.min() == qt["min"]
        and mt.max() == qt["max"]
    )
    assert m.results_text == QT_VALUES["results_text"] == "flim.ptu: 32x32 px.\nWindows: ch0."


def test_the_live_qt_view_model_gives_the_same_maps_on_the_same_file(app, drv, flim):
    m = C.computed(app, drv, flim)
    qt = MicroTimeViewModel()
    qt.filename = str(flim)
    assert qt.compute()
    expected = np.maximum(np.nan_to_num(qt.mean_micro_time_map()), 0.0)
    np.testing.assert_array_equal(m.mean_micro_time_map(), expected)
    np.testing.assert_array_equal(m.intensity_map(), qt.intensity_map())
    assert "mean_micro_time (ch0)" in m._columns
    np.testing.assert_array_equal(m._columns["mean_micro_time (ch0)"], expected)


def test_an_independent_clsm_image_gives_the_same_mean_micro_time(app, drv, flim):
    import tttrlib

    m = C.computed(app, drv, flim)
    tttr = tttrlib.TTTR(str(flim))
    clsm = tttrlib.CLSMImage(tttr, channels=[0], fill=True)
    res = tttr.header.micro_time_resolution * 1e9
    ref = np.maximum(
        np.nan_to_num(np.asarray(clsm.get_mean_micro_time(tttr, res, 2, True), dtype=float)), 0.0
    )
    ref = ref[0] if ref.ndim == 3 else ref
    np.testing.assert_allclose(m.mean_micro_time_map(), ref, rtol=1e-9)


def test_min_photons_discriminates_pixels_and_needs_a_new_run(app, drv, flim):
    m = C.computed(app, drv, flim)
    assert (m.mean_micro_time_map() > 0).all()
    drv.type_into("n_ph_min", "100000")
    assert m.n_ph_min == 100000 and m.needs_recompute()
    C.run(app, drv)
    assert (m.mean_micro_time_map() == 0).all()
    drv.type_into("n_ph_min", "2")
    C.run(app, drv)
    assert (m.mean_micro_time_map() > 0).all()


def test_the_movie_has_one_mean_micro_time_image_per_frame(app, drv, flim):
    m = C.computed(app, drv, flim)
    movie = np.asarray(m.mean_micro_time_frames())
    assert movie.shape == (data.FRAMES, 32, 32) and movie.min() >= 0
    assert movie.max() < 8.3 and (movie > 0).mean() > 0.5
    assert movie[movie > 0].mean() == pytest.approx(m.mean_micro_time_map().mean(), rel=0.35)


def test_two_detector_windows_give_two_map_sets(app, drv, flim2):
    app.model.detectors = {
        "first": {"chs": [0], "micro_time_ranges": []},
        "second": {"chs": [1], "micro_time_ranges": []},
    }
    m = C.computed(app, drv, flim2)
    assert list(m._by_window) == ["first", "second"] and {
        "mean_micro_time (first)",
        "mean_micro_time (second)",
    } <= set(m._columns)
    truth = data.counts(2)
    np.testing.assert_array_equal(m._by_window["second"]["intensity"], truth[1].sum(axis=0))


def test_a_micro_time_range_selects_the_photons_of_the_window(app, drv, flim):
    app.model.detectors = {"early": {"chs": [0], "micro_time_ranges": [(0, 60)]}}
    m = C.computed(app, drv, flim)
    full = MicroTimeViewModel()
    full.filename = str(flim)
    full.compute()
    assert m.intensity_map().sum() < full.intensity_map().sum()
    assert m.mean_micro_time_map().max() < full.mean_micro_time_map().max()


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
        numeric_column(read_imaging_table(str(target)), "mean_micro_time (ch0)"),
        app.model.mean_micro_time_map().ravel(),
    )


def test_the_hdf5_dialog_cancel_writes_nothing(app, drv, stream, tmp_path):
    C.hdf5_dialog_cancel_writes_nothing(app, drv, stream, tmp_path)


def test_an_unwritable_hdf5_place_is_reported(app, drv, stream, tmp_path):
    C.hdf5_unwritable_place_is_reported(app, drv, stream, tmp_path)


def test_the_container_button_writes_the_artifact_beside_the_source(app, drv, stream):
    C.container_is_greyed_without_a_result_and_writes_the_artifact_beside_the_source(
        app, drv, stream, "mean_micro_time"
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


@pytest.mark.parametrize("tab", ["Intensity", "Mean micro-time (ns)", "Mean micro-time movie"])
def test_the_colormap_list_changes_the_model_and_the_picture(app, drv, flim, tab):
    C.colormap_list_offers_four_maps_and_a_click_changes_the_model(app, drv, flim, tab)


@pytest.mark.parametrize("tab", ["Intensity", "Mean micro-time (ns)", "Mean micro-time movie"])
def test_the_wheel_zooms_and_a_drag_pans_the_image(app, drv, flim, tab):
    C.wheel_zooms_and_a_drag_pans_the_image(app, drv, flim, tab)


def test_the_movie_plays_loops_stops_and_takes_a_typed_speed(app, drv, flim):
    C.movie_play_loop_stop_and_speed(app, drv, flim, "Mean micro-time movie")


# ── 7. guide, help, persistence, host ───────────────────────────────────────────────────────────────────────── #


def test_help_button_opens_the_help_and_its_buttons_work(app, drv):
    C.help_button_opens_the_help_and_its_buttons_work(app, drv)


def test_guide_button_starts_the_tour_and_close_tour_ends_it(app):
    C.guide_button_starts_the_tour_and_close_tour_ends_it(app)


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(
    app, drv, stream, tmp_path
):
    out = tmp_path / "walk"
    out.mkdir()

    def choose():
        app.model.folder = str(stream.parent)
        drv.click("open_file")
        drv.click_text(stream.name)
        drv.click_text("Open", last=True)

    def hdf5():
        app.model.folder = str(out)
        drv.click("request_hdf5")
        C.save_in_dialog(drv, "walk.imaging.h5")

    C.tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(
        app, drv, stream, {"file": choose, "run": lambda: drv.click("run_maps"), "saved": hdf5}
    )
    assert (out / "walk.imaging.h5").exists() and app.model._columns


def test_every_guide_target_is_a_drawn_control_or_window(app, drv, flim):
    C.every_guide_target_is_a_drawn_control_or_window(app, drv, flim)


def test_settings_round_trip_and_invalid_values_are_ignored(app, drv):
    C.settings_round_trip_and_invalid_values_are_ignored(
        app, drv, {"n_ph_min": 7}, {"n_ph_min": "many"}
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


def test_every_qt_control_has_an_emtk_equivalent():
    qt_labels = {s.get("label") for s in walk(QT_SPEC["sections"]) if s.get("label")}
    assert qt_labels == {"TTTR file", "Min. photons"}
    emtk = {s.get("label") for s in walk(EMTK_SPEC["sections"]) if s.get("label")} | {
        b["label"] for s in walk(EMTK_SPEC["sections"]) for b in s.get("buttons", [])
    }
    assert {
        "TTTR file",
        "Min. photons",
        "Run",
        "Add mean micro-time to HDF5",
        "ndX",
        "Next",
        "Detector window",
    } <= emtk
    qt_tabs = [s["title"] for s in walk(QT_SPEC["sections"]) if s.get("type") == "custom"]
    assert (
        qt_tabs
        == ["Intensity", "Mean micro-time (ns)", "Mean micro-time movie"]
        == [p["title"] for p in EMTK_SPEC["sections"][1:]]
    )


def test_every_spec_attribute_and_action_exists_on_the_model():
    model = MicroTimeModel()
    for section in walk(EMTK_SPEC["sections"]):
        if section.get("attr"):
            assert hasattr(model, section["attr"]), section
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button
        for key in ("source", "call", "options_source"):
            if section.get(key) and section.get("type") != "custom":
                assert hasattr(model, section[key]), (key, section)
        if section.get("type") == "custom":
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
    C.qt_free("img_pixel_micro_time")


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
        C.texts_apart(painter, ignore=(str(flim),))
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
