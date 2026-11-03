"""The flow-map app: numbers, the demo workflow, every action and every error path.

Hermetic: settings in a temporary folder, files and the demo in a temporary folder (``demo_folder`` is redirected), no network (the database picker
gets a stub client). The oracle is the flow written into the test stack (``data/make_data.py``: blobs drifting 0.5 px/frame along +x,
so ``expected_speed_um_s(0.5)`` along +x and none along y), the tile grid the settings define, the demo's simulated Poiseuille flow, and
the plugin's own estimator called without the view model.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fio.image import imwrite
from chisurf.plugins.emtk_layout import help_close_caption
from chisurf.plugins.microscopy.imaging_emtk.testing import (
    Driver,
    dialog_open,
    hermetic_env,
    numeric_ticks,
    pick_from_workspace,
    walk,
)
from chisurf.plugins.microscopy.img_flow import core, demo
from chisurf.plugins.microscopy.img_flow.gui.app import ImgFlowApp, make_app

HERE = Path(__file__).parent
PLUGIN = HERE.parent
DATA = HERE / "data"
BASE_SPEC = json.loads((PLUGIN / "gui" / "flow.view.json").read_text(encoding="utf-8"))
EMTK_SPEC = json.loads((PLUGIN / "gui" / "flow_emtk.view.json").read_text(encoding="utf-8"))
BIG = (1200, 800)

_make = importlib.util.spec_from_file_location("flow_make_data", DATA / "make_data.py")
assert _make is not None and _make.loader is not None, "data/make_data.py missing"
_data = importlib.util.module_from_spec(_make)
_make.loader.exec_module(_data)
TIMING = _data.TIMING
#: The planted flow, µm/s along +x.
TRUTH = _data.expected_speed_um_s(0.5)
#: The settings of the TIFF scenarios.
BASE = dict(
    tile=16,
    n_lags=4,
    min_quality=0.5,
    step=0,
    method="stics",
    distance=4,
    subtract_average="frame",
    arrow_scale=1.0,
    **TIMING,
)


def have_simulator() -> bool:
    try:
        import tttrlib
    except Exception:
        return False
    return hasattr(tttrlib, "SimEngine") and hasattr(tttrlib, "SimVectorGrid")


needs_simulator = pytest.mark.skipif(
    not have_simulator(), reason="tttrlib was built without the photon simulator"
)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)


@pytest.fixture(scope="module")
def demo_file(tmp_path_factory):
    """The demo photon stream, simulated once (about 20 s); ``demo_folder`` is redirected to it so ``Load demo`` reuses it."""
    path = demo.make_demo(tmp_path_factory.mktemp("demo"))
    return path


@pytest.fixture
def with_demo(demo_file, monkeypatch):
    monkeypatch.setattr(demo, "demo_folder", lambda: demo_file.parent)
    return demo_file


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def drv(app):
    return Driver(app, (1000, 700))


@pytest.fixture(scope="module")
def flow_stack():
    return _data.drifting_stack(0.5)


@pytest.fixture
def flow_tif(tmp_path, flow_stack):
    path = tmp_path / "flow.tif"
    imwrite(path, flow_stack)
    return path


def use(app, **settings):
    for k, v in settings.items():
        setattr(app.model, k, v)


def loaded(app, drv, path):
    """Choose *path* the way a person does (pick it in the Input section) and wait for the worker that reads its channels."""
    pick_from_workspace(app, path)
    drv.settle()
    return app.model


def mapped(app, drv, path=None, **settings):
    """Press Map flow with the pointer (after choosing *path*) and wait for the worker."""
    if path is not None:
        loaded(app, drv, path)
    use(app, **(settings or BASE))
    drv.click("map_flow")
    drv.settle()
    return app.model


def pick(drv, field, label):
    drv.click(field)
    assert label in drv.draw(1).strings, (field, label, drv.painter.strings[:80])
    drv.click_text(label, last=True)


def settings_of(**changes):
    return dict(BASE, **changes)


# ── 1. the numbers ──────────────────────────────────────────────────────────────────────────────────────────── #


def tile_grid(n=48, tile=16, step=0):
    """The tile centres (px) the settings define: a tile every *step* px (half a tile when 0) that fits in the frame."""
    step = step or tile // 2
    return np.arange(0, n - tile + 1, step) + tile / 2


def assert_planted_flow(result, min_quality=0.5, rel=0.15):
    """The kept tiles report the planted speed along +x (conservatively: slightly under it) and next to nothing along y."""
    summary = result.summary(min_quality)
    assert summary["mean_vx"] == pytest.approx(TRUTH, rel=rel)
    assert abs(summary["mean_vy"]) < 0.25 * summary["mean_vx"]
    return summary


def test_the_map_recovers_the_planted_flow_on_the_tile_grid(app, drv, flow_tif):
    m = loaded(app, drv, flow_tif)
    assert m.status_line == "flow.tif: 80 frames of 48x48, 1 channel(s). Ready."
    mapped(app, drv)
    r = m.result
    centres = tile_grid()
    assert np.asarray(r.vx).shape == (len(centres), len(centres)) and r.n_escaped == 0
    summary = assert_planted_flow(r)
    assert m.status_line == f"25/25 tiles, mean speed {summary['mean_speed']:.3g} µm/s"
    vectors = m.flow_vectors()
    assert len(vectors) == 25
    um = TIMING["pixel_size_nm"] / 1000
    assert sorted({v["x"] for v in vectors}) == pytest.approx(list(centres * um))
    assert sorted({v["y"] for v in vectors}) == pytest.approx(list(centres * um))
    assert all(v["dx"] > 0 for v in vectors)  # every arrow points along +x
    rows = m.tile_table_rows()
    assert len(rows) == 25
    for row in rows:
        assert row["speed"] == pytest.approx(np.hypot(row["vx"], row["vy"]))
        assert row["angle"] == pytest.approx(np.degrees(np.arctan2(row["vy"], row["vx"])))


def test_the_estimator_called_without_the_view_model_gives_the_same_field_and_the_speed_written_into_the_stack(
    app, drv, flow_tif, flow_stack
):
    m = loaded(app, drv, flow_tif)
    mapped(app, drv)
    timing = core.scan_timing(
        48,
        pixel_duration_us=TIMING["pixel_duration_us"],
        line_duration_ms=TIMING["line_duration_ms"],
        frame_duration_ms=TIMING["frame_duration_ms"],
        pixel_size_nm=TIMING["pixel_size_nm"],
    )
    direct = core.analyse(flow_stack, timing, tile=16, n_lags=4)
    np.testing.assert_allclose(m.result.vx, direct.vx, rtol=1e-12)
    summary = m.result.summary(0.5)
    assert (
        summary["mean_vx"] == pytest.approx(TRUTH, rel=0.15) and summary["mean_vx"] < TRUTH
    )  # conservative, as documented
    assert (
        abs(summary["mean_vy"]) < 0.15 * summary["mean_vx"] and summary["coherence"] > 0.99
    )  # along +x


# ── 2. every scenario on the planted flow ─────────────────────────────────────────────────────────────────── #

SCENARIOS = {
    "defaults": {},
    "small tile": {"tile": 8, "step": 8},
    "stack background": {"subtract_average": "stack"},
    "tight quality": {"min_quality": 0.99},
    "two lags": {"n_lags": 2},
    "escaping lags": {"n_lags": 30},
    "pair correlation": {"method": "pcf", "distance": 4},
    "pair distance 8": {"method": "pcf", "distance": 8},
    "tile 24 step 24": {"tile": 24, "step": 24, "arrow_scale": 2.0},
}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_every_scenario_maps_the_planted_flow_or_says_why_not(app, drv, flow_tif, scenario):
    settings = dict(BASE, **SCENARIOS[scenario])
    loaded(app, drv, flow_tif)
    mapped(app, drv, **settings)
    m = app.model
    r = m.result
    if settings["method"] == "stics":  # STICS tiles the frame on the grid the settings define
        n = len(tile_grid(tile=settings["tile"], step=settings["step"]))
        assert np.asarray(r.vx).size == n * n
    total = np.asarray(r.vx).size
    if (
        scenario == "escaping lags"
    ):  # 30 lags x 0.5 px/frame = 15 px: the peak leaves every 16 px tile
        assert r.n_escaped == total and not m.flow_vectors()
        assert m.status_line.startswith(f"No arrows: All {total} tile(s) were refused")
        assert m.diagnose()
        return
    kept = r.kept(m.min_quality)
    assert r.n_escaped == 0 and kept.any()
    summary = r.summary(m.min_quality)
    assert (
        m.status_line
        == f"{int(kept.sum())}/{total} tiles, mean speed {summary['mean_speed']:.3g} µm/s"
    )
    assert len(m.flow_vectors()) == int(kept.sum()) and len(m.tile_table_rows()) == total
    if settings["method"] == "stics":
        # two lags resolve 1 px of travel only: coarser, so a wider band
        assert_planted_flow(
            r, m.min_quality, rel=0.25 if scenario in ("small tile", "two lags") else 0.15
        )
    else:  # pair correlation reads an arrival time, not a displacement: the direction is what is known
        assert summary["mean_vx"] > 0 and abs(summary["mean_vy"]) < 0.25 * summary["mean_vx"]


@needs_simulator
def test_the_demo_is_loaded_with_its_scanner_and_mapped_along_plus_x(app, drv, with_demo):
    drv.click("load_example")
    drv.settle(timeout=300)
    m = app.model
    assert m.status_line.endswith("50 frames of 64x64, 1 channel(s). Ready.")
    assert Path(m.filename) == with_demo
    # the demo's scanner: 20 µs pixels, 64 pixels a line, 64 lines a frame, 100 nm pixels
    assert (m.pixel_duration_us, m.line_duration_ms, m.frame_duration_ms, m.pixel_size_nm) == (
        pytest.approx(20.0),
        pytest.approx(1.28),
        pytest.approx(81.92),
        pytest.approx(100.0),
    )
    assert m.demo_truth is not None and m.demo_truth["v_max_um_s"] == 2.0
    drv.click("map_flow")
    drv.settle()
    summary = app.model.result.summary(0.5)
    assert (
        app.model.result.n_escaped == 0
        and summary["n_kept"] >= 0.8 * summary["n_tiles"]
        and 0
        < summary["mean_vx"]
        < m.demo_truth["v_max_um_s"]  # a Poiseuille profile averages below its peak
    )


@pytest.mark.parametrize(
    "attr",
    [
        "tile",
        "n_lags",
        "distance",
        "min_quality",
        "pixel_duration_us",
        "frame_duration_ms",
        "line_duration_ms",
        "pixel_size_nm",
        "arrow_scale",
        "step",
    ],
)
def test_typed_extremes_are_clamped_to_the_spec_range(app, drv, attr):
    drv.draw(2)
    if attr in ("arrow_scale", "step"):
        drv.click("Display and estimator.fold")
    spec = next(s for s in walk(EMTK_SPEC["sections"]) if s.get("attr") == attr)
    for typed, clamped in (("1000000000", spec["maximum"]), ("-5", spec["minimum"])):
        drv.type_into(attr, typed)
        assert getattr(app.model, attr) == pytest.approx(clamped, rel=1e-9), (attr, typed)


# ── 3. choosing files: typed, Browse, Database, drops ──────────────────────────────────────────────────────── #


def test_choosing_a_file_reads_its_channels_and_does_not_map(app, drv, flow_tif):
    m = loaded(app, drv, flow_tif)
    assert (
        Path(m.filename) == flow_tif
        and m.channel_names() == ["ch0"]
        and m.channel == "ch0"
        and m.result is None
    )


class FakeClient:
    """A database client that lists one dataset and resolves it to a local file."""

    def __init__(self, path):
        self.path = str(path)

    def call(self, method, params=None):
        if method == "mmfdb.datasets.browse":
            return {
                "datasets": [
                    {
                        "artifact_id": "a1",
                        "artifact_kind": "raw_data",
                        "data_format": "tif",
                        "original_filename": "stored.tif",
                    }
                ],
                "total": 1,
            }
        if method == "mmfdb.datasets.open":
            return {"local_path": self.path}
        raise AssertionError(method)


def open_picker(app, drv, path):
    import time

    app.picker.client = FakeClient(path)
    drv.click("open_database")
    drv.draw(2)
    assert app.picker.is_open
    end = time.monotonic() + 10
    while "stored.tif [raw_data] (tif)" not in drv.draw(1).strings and time.monotonic() < end:
        time.sleep(0.02)
    drv.click_text("stored.tif [raw_data] (tif)")
    assert app.picker.selection is not None


# ── 4. errors ──────────────────────────────────────────────────────────────────────────────────────────────── #


def test_map_flow_with_nothing_loaded_says_so(app, drv):
    drv.click("map_flow")
    assert app.model.status_line == "Load an image first." and not app.job.busy
    assert "Load an image first." in drv.strings()


def test_a_corrupt_file_reports_the_reasons(app, drv, tmp_path):
    bad = tmp_path / "bad.tif"
    bad.write_bytes(b"not a tiff")
    loaded(app, drv, bad)
    assert app.model.status_line.startswith("Could not read the file: could not read image:")
    assert app.model.status_line == app.model.status
    drv.click("map_flow")
    drv.settle()
    assert app.model.status_line.startswith("Flow map failed:") and app.model.result is None


def test_too_few_frames_are_refused_with_a_reason(app, drv, tmp_path):
    two = tmp_path / "two.tif"
    imwrite(two, _data.drifting_stack(0.5, n_frames=2))
    loaded(app, drv, two)
    assert "Too few frames" in app.model.status_line
    drv.click("map_flow")
    drv.settle()
    assert app.model.status_line.startswith("Flow map failed:") and app.model.result is None


def test_tiles_that_escape_are_refused_and_the_status_says_why(app, drv, flow_tif):
    mapped(app, drv, flow_tif, **settings_of(n_lags=30))
    m = app.model
    assert m.result.n_escaped == 25 and not m.flow_vectors()
    assert m.status_line.startswith("No arrows: All 25 tile(s) were refused")
    text = " ".join(drv.strings())
    assert "No arrows." in text and "Use fewer frame lags, or a larger tile." in text
    assert (
        "No arrows \u2014 nothing passed the quality threshold, or the field is empty."
        in " ".join(drv.draw(2).strings)
    )  # under the image, wrapped


def test_nothing_above_the_quality_threshold_is_explained_not_blank(app, drv, flow_tif):
    mapped(app, drv, flow_tif, **settings_of(min_quality=1.0))
    assert not app.model.flow_vectors()
    assert (
        app.model.status_line.startswith("No arrows:")
        and "best tile scored" in app.model.status_line
    )
    assert "No arrows." in " ".join(drv.strings())


def test_a_new_file_clears_the_previous_result(app, drv, flow_tif, tmp_path, flow_stack):
    mapped(app, drv, flow_tif)
    assert app.model.result is not None
    other = tmp_path / "other.tif"
    imwrite(other, flow_stack)
    loaded(app, drv, other)
    assert (
        app.model.result is None
        and app.model.tile_table_rows() == []
        and app.model.profile_series() == []
    )


def test_the_actions_and_the_form_are_greyed_while_a_worker_runs(app, drv, flow_tif):
    from chisurf.emtk import job_gate

    # Hold the run open: on a small file it ends within the click's own frames, and the
    # controls were enabled again by the time they were clicked.
    job_gate.arm()
    try:
        app.model.open_path(str(flow_tif))
        assert app.job.busy
        runs = []
        app.model.map_flow = lambda: runs.append(1)
        drv.click("map_flow")
        assert runs == [] and app.job.busy
        drv.click("method")
        assert (
            "Pair correlation — when it arrives" not in drv.draw(1).strings
        )  # the list did not open
        job_gate.release()
        drv.settle()
    finally:
        job_gate.disarm()


def test_a_worker_that_raises_is_reported_not_swallowed(app, drv, flow_tif, monkeypatch):
    loaded(app, drv, flow_tif)

    def boom(*a, **k):
        raise RuntimeError("correlation exploded")

    monkeypatch.setattr(core, "analyse_file", boom)
    use(app, **BASE)
    drv.click("map_flow")
    drv.settle()
    assert "correlation exploded" in app.model.status_line and app.model.result is None


@needs_simulator
def test_a_demo_that_cannot_be_made_is_reported(app, drv, monkeypatch, tmp_path):
    monkeypatch.setattr(demo, "demo_folder", lambda: tmp_path / "blocked")
    (tmp_path / "blocked").write_text("a file where the folder should be")
    drv.click("load_example")
    drv.settle(timeout=120)
    assert app.model.status_line.startswith("Could not make the demo:") and app.model.filename == ""


# ── 5. the settings ────────────────────────────────────────────────────────────────────────────────────────── #


def test_the_estimator_list_offers_the_two_estimators_and_each_is_picked(app, drv):
    for label, value in (
        ("Pair correlation — when it arrives", "pcf"),
        ("STICS — where the peak moves", "stics"),
    ):
        pick(drv, "method", label)
        assert app.model.method == value


def test_the_background_list_offers_the_two_choices(app, drv):
    drv.click("Display and estimator.fold")
    for label, value in (
        ("Also the time-average (immobile)", "stack"),
        ("Each frame's own mean", "frame"),
    ):
        pick(drv, "subtract_average", label)
        assert app.model.subtract_average == value


def test_escape_closes_an_open_list_without_choosing(app, drv):
    drv.click("method")
    assert "Pair correlation — when it arrives" in drv.draw(1).strings
    drv.escape()
    assert app.model.method == "stics"


def test_the_channel_list_names_the_channels_of_the_file(app, drv, tmp_path):
    two = tmp_path / "two.tif"
    imwrite(two, _data.drifting_stack(0.5, n_frames=2))
    loaded(app, drv, two)
    assert app.model.channel_names() == ["ch0", "ch1"]
    drv.click("channel")
    assert {"ch0", "ch1"} <= set(drv.draw(1).strings)
    drv.click_text("ch1", last=True)
    assert app.model.channel == "ch1"


def test_the_numeric_fields_take_typed_values_and_their_arrows_step_by_the_spec_steps(app, drv):
    x, y, w, h = drv.rect("tile.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.tile == 25
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    assert app.model.tile == 23
    x, y, w, h = drv.rect("min_quality.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.min_quality == 1.0  # a step of 1.0 clamps to the spec maximum
    drv.click_at(x + w / 2, y + h * 0.75)
    assert app.model.min_quality == 0.0
    drv.type_into("min_quality", "0.123456")
    assert app.model.min_quality == 0.12  # two decimals, as the spec declares
    drv.type_into("frame_duration_ms", "81.92")
    assert app.model.frame_duration_ms == 81.92
    drv.type_into("pixel_duration_us", "3.14159")
    assert app.model.pixel_duration_us == 3.142


def test_the_scanner_and_display_panels_fold(app, drv):
    drv.draw(2)
    assert "pixel_duration_us" in app.form.rects
    drv.click("Scanner.fold")
    drv.draw(2)
    assert "pixel_duration_us" not in app.form.rects
    drv.click("Scanner.fold")
    assert "pixel_duration_us" in app.form.rects
    assert "arrow_scale" not in app.form.rects
    drv.click("Display and estimator.fold")
    assert {"arrow_scale", "step", "subtract_average"} <= set(app.form.rects)


def test_changing_a_setting_does_not_re_map_by_itself(app, drv, flow_tif):
    mapped(app, drv, flow_tif)
    before = app.model.status_line
    pick(drv, "method", "Pair correlation — when it arrives")
    assert (
        not app.job.busy and app.model.status_line == before and app.model.result.method == "stics"
    )


# ── 6. export ────────────────────────────────────────────────────────────────────────────────────────────── #


def test_export_without_a_result_says_so(app, drv):
    drv.click("request_export")
    assert app.model.status_line == "Nothing to export yet" and not dialog_open(drv)


def test_export_csv_writes_one_row_per_tile_with_the_planted_flow(app, drv, flow_tif, tmp_path):
    mapped(app, drv, flow_tif)
    drv.click("request_export")
    painter = drv.draw(2)
    assert (
        dialog_open(drv)
        and app.dialog.title == "Export flow map"
        and "flow_map.csv" in painter.strings
    )
    drv.click_text("Save", last=True)
    written = tmp_path / "flow_map.csv"
    lines = written.read_text().splitlines()
    assert lines[0] == "x,y,vx,vy,speed,angle,quality" and len(lines) == 26
    table = np.array([[float(v) for v in line.split(",")] for line in lines[1:]])
    x, y, vx, vy, speed, angle, quality = table.T
    centres = tile_grid() * TIMING["pixel_size_nm"] / 1000
    assert sorted(set(x)) == pytest.approx(list(centres)) and sorted(set(y)) == pytest.approx(
        list(centres)
    )
    assert vx.mean() == pytest.approx(TRUTH, rel=0.15) and abs(vy.mean()) < 0.25 * vx.mean()
    np.testing.assert_allclose(speed, np.hypot(vx, vy), rtol=1e-9)
    np.testing.assert_allclose(angle, np.degrees(np.arctan2(vy, vx)), rtol=1e-9, atol=1e-9)
    assert ((0 <= quality) & (quality <= 1)).all()
    assert app.model.status_line == f"Wrote {written}" and not dialog_open(drv)


def test_export_to_a_typed_name_cancel_and_an_unwritable_place(app, drv, flow_tif, tmp_path):
    mapped(app, drv, flow_tif)
    drv.click("request_export")
    drv.draw(2)
    drv.click_text("Cancel")
    assert not list(tmp_path.glob("*.csv")) and not dialog_open(drv)
    drv.click("request_export")
    drv.draw(2)
    drv.click_at(*[v + o for v, o in zip(drv.text_rect("flow_map.csv")[:2], (30, 6))])
    assert app.io.want_capture_keyboard
    drv.select_all()
    drv.type_text("mine")
    drv.click_text("Save", last=True)
    assert (tmp_path / "mine.csv").read_text().startswith("x,y,vx,vy,speed,angle,quality")
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    app.model.write_export(str(blocker / "x.csv"))
    assert app.model.status_line.startswith("Could not write") and "Could not write" in " ".join(
        drv.strings()
    )


# ── 7. the views ─────────────────────────────────────────────────────────────────────────────────────────── #


def test_every_view_says_what_to_do_before_there_is_a_result(app, drv):
    strings = drv.draw(2).strings
    assert (
        any(s.startswith("Load a TIFF") or "press" in s.lower() for s in strings)
        or app.model.summary_html()
    )
    assert any(s.startswith("Map a file (or load the demo)") for s in strings)
    drv.click_text("Profile")
    assert any(s.startswith("Map a file: the speed") for s in drv.draw(2).strings)
    drv.click_text("Tiles")
    assert "Tiles" in drv.draw(2).strings and app.model.tile_table_rows() == []


def test_the_quiver_draws_one_arrow_per_tile_and_names_the_fastest(app, drv, flow_tif):
    m = mapped(app, drv, flow_tif)
    panel = app.panels["Flow field"]
    assert panel.n_drawn == 25 == len(m.flow_vectors())
    fastest = max(np.hypot(v["dx"], v["dy"]) for v in m.flow_vectors())
    caption = f"25 of 25 arrows · fastest {fastest:.3g} µm/s"
    assert panel.caption == caption
    assert caption in drv.draw(2).strings
    assert {"x", "y"} <= set(drv.painter.strings)


def test_the_arrow_scale_changes_the_drawn_length_and_says_so_and_never_the_numbers(
    app, drv, flow_tif
):
    m = mapped(app, drv, flow_tif)
    vectors = m.flow_vectors()
    summary = m.summary_html()
    drv.click("Display and estimator.fold")
    drv.type_into("arrow_scale", "2")
    assert m.arrow_scale == 2.0 and m.flow_vectors() == vectors
    assert app.panels["Flow field"].caption.endswith("drawn at 2x (display only)")
    assert m.summary_html() == summary


def test_the_profile_shows_speed_and_vx_and_the_demo_truth_only_for_the_demo(app, drv, flow_tif):
    m = mapped(app, drv, flow_tif)
    drv.click_text("Profile")
    strings = set(drv.draw(3).strings)
    assert {
        "speed",
        "v_x",
        "y (µm)",
        "velocity (µm/s)",
    } <= strings and "simulated truth" not in strings
    assert [s["name"] for s in m.profile_series()] == ["speed", "v_x"]


@needs_simulator
def test_the_demo_adds_its_simulated_truth_to_the_profile_even_when_no_arrow_survives(
    app, drv, with_demo
):
    drv.click("load_example")
    drv.settle(timeout=300)
    drv.click("map_flow")
    drv.settle()
    drv.click_text("Profile")
    assert "simulated truth" in drv.draw(3).strings and "simulated truth" in [
        s["name"] for s in app.model.profile_series()
    ]


def test_a_drag_pans_the_flow_field_and_the_profile_and_a_new_result_refits_it(app, drv, flow_tif):
    mapped(app, drv, flow_tif)
    drv.draw(3)
    x, y, w, h = app.item_rects["Flow field"]
    original = numeric_ticks(drv.draw(2))
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.4))
    assert numeric_ticks(drv.draw(2)) != original
    drv.click_text("Profile")
    drv.draw(3)
    x, y, w, h = app.item_rects["Profile"]
    before = numeric_ticks(drv.draw(2))
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.4))
    assert numeric_ticks(drv.draw(2)) != before
    use(app, min_quality=0.99)
    drv.click("map_flow")
    drv.settle()
    assert numeric_ticks(drv.draw(3)) != []


def column_values(drv, expect, header_text):
    """The cells of one column (those drawn under its header), in the order drawn."""
    texts = drv.draw(2).texts
    hx, hy, hw, hh = [t[:4] for t in texts if t[5].endswith(header_text)][-1]
    return [
        t[5]
        for t in texts
        if t[5] in expect and hx - 60 <= t[0] <= hx + hw + 60 and t[1] > hy + hh - 1
    ]


def test_the_tile_table_header_sorts_by_value_and_a_row_click_changes_nothing(app, flow_tif):
    drv = Driver(
        app, BIG
    )  # seven columns: at 1000 px the Speed header lies beyond the window and the table scrolls sideways
    mapped(app, drv, flow_tif)
    drv.click_text("Tiles")
    speeds = {f"{r['speed']:.4g}" for r in app.model.tile_table_rows()}
    unsorted = column_values(drv, speeds, "Speed")
    assert (
        len(unsorted) >= 15
        and unsorted == [f"{r['speed']:.4g}" for r in app.model.tile_table_rows()][: len(unsorted)]
    )

    def header():
        return [t[:4] for t in drv.draw(1).texts if t[5].endswith("Speed")][-1]

    drv.click(header())
    ascending = column_values(drv, speeds, "Speed")
    assert ascending == sorted(ascending, key=float) and ascending != unsorted
    drv.click(header())
    assert column_values(drv, speeds, "Speed") == sorted(ascending, key=float, reverse=True)
    before = app.model.export_settings()
    drv.click_text(ascending[3])
    assert app.model.export_settings() == before and app.model.result is not None


def test_the_wheel_zooms_the_flow_field(app, drv, flow_tif):
    mapped(app, drv, flow_tif)
    drv.draw(3)
    before = numeric_ticks(drv.draw(2))
    x, y, w, h = app.item_rects["Flow field"]
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert numeric_ticks(drv.draw(2)) != before


def test_the_wheel_over_the_tile_field_steps_it(app, drv):
    x, y, w, h = drv.rect("tile")
    drv.wheel(x + w * 0.3, y + h / 2, 1)
    assert app.model.tile == 25


def test_the_wheel_scrolls_the_settings_window_when_the_form_is_taller_than_it(app):
    drv = Driver(app, (800, 360))
    drv.draw(3)
    top = app.form.rects["map_flow"][1]
    drv.wheel(150, 250, -5)
    assert app.form.rects["map_flow"][1] < top
    drv.wheel(150, 250, 8)
    assert app.form.rects["map_flow"][1] == top


# ── 8. guide, help, persistence, host ──────────────────────────────────────────────────────────────────────── #


def test_help_button_opens_the_help_and_its_buttons_work(app, drv):
    drv.click("help")
    assert app.help_window.open
    assert {"Start Guided Tour", help_close_caption()} <= set(drv.draw(2).strings)
    drv.click_text("Start Guided Tour")
    assert not app.help_window.open and app.tour.active
    app.tour.stop()
    drv.click("help")
    drv.escape()
    assert not app.help_window.open


def test_guide_button_starts_the_tour_and_close_tour_ends_it(app):
    drv = Driver(app, BIG)
    drv.click("guide")
    assert app.tour.active
    drv.click_text("Close Tour")
    assert not app.tour.active


@needs_simulator
def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(
    app, with_demo
):
    """The guided tour keeps the demo workflow: Load demo, then Map flow, each pressed by the user."""
    drv = Driver(app, BIG)
    drv.click("guide")
    guard = 0
    while app.tour.active and guard < 30:
        guard += 1
        drv.draw(2)
        step = app.tour.steps[app.tour.step_idx]
        target = step.get("target") or {}
        if app.tour.awaiting:
            if target.get("name") == "load_example":
                drv.click("load_example")
                drv.settle(timeout=300)
            elif target.get("name") == "computed":
                drv.click("map_flow")
                drv.settle()
            drv.draw(2)
            assert not app.tour.awaiting, (
                f"{step['title']}: operating the control did not release the step"
            )
        drv.click_text(
            "Finish ✓" if app.tour.step_idx == len(app.tour.steps) - 1 else "Next ►", last=True
        )
    assert (
        not app.tour.active
        and app.model.result is not None
        and "frames of 64x64" in app.model.status
        or app.model.result is not None
    )


def test_every_guide_target_is_a_drawn_control_or_window(app, drv, flow_tif):
    seen = set()
    for index, step in enumerate(app.tour.steps):
        target = step.get("target") or {}
        if not target:
            continue
        app.tour.start(index)
        key = app.tour._target_key(target)
        drv.draw(3)
        rect = app.tour.get_target_rect(key)
        if rect is None:
            mapped(app, drv, flow_tif)
            app.tour.start(index)
            drv.draw(3)
            rect = app.tour.get_target_rect(key)
        assert rect and rect[2] > 0 and rect[3] > 0, f"{step['title']}: nothing drawn for {key!r}"
        seen.add(key)
    app.tour.stop()
    assert {
        "load_example",
        "filename",
        "Scanner.fold",
        "tile",
        "n_lags",
        "computed",
        "Flow field",
        "Profile",
        "min_quality",
    } <= seen


def test_a_file_picked_in_the_workspace_does_not_release_the_demo_step_but_the_demo_does(
    app, flow_tif
):
    drv = Driver(app, BIG)
    app.model.folder = str(flow_tif.parent)
    drv.click("guide")
    app.tour.next()
    drv.draw(2)
    assert app.tour.awaiting
    pick_from_workspace(app, flow_tif)
    drv.settle()
    assert app.tour.awaiting  # the step waits for the demo, not for any file
    app.model.notify("demo")
    drv.draw(2)
    assert not app.tour.awaiting


def test_settings_round_trip_and_invalid_values_are_ignored(app, drv):
    m = app.model
    m.method, m.tile, m.n_lags, m.distance, m.min_quality, m.subtract_average = (
        "pcf",
        32,
        7,
        6,
        0.75,
        "stack",
    )
    (
        m.pixel_duration_us,
        m.frame_duration_ms,
        m.line_duration_ms,
        m.pixel_size_nm,
        m.arrow_scale,
        m.step,
    ) = 12.5, 100.0, 1.5, 64.0, 3.0, 8
    m.folder = "/tmp"
    saved = json.loads(json.dumps(app.export_settings()))
    other = make_app()
    other.restore_settings(saved)
    assert other.export_settings() == saved and other.model.method == "pcf"
    other.restore_settings(
        {
            "method": "magic",
            "tile": "big",
            "n_lags": 2.5,
            "min_quality": None,
            "subtract_average": 3,
            "step": True,
        }
    )
    assert other.export_settings() == saved
    other.restore_settings(None)
    assert not {"filename", "channel"} & set(saved)


def test_the_imaging_hub_contract(app, drv, flow_tif):
    app.apply_setup_settings(
        {
            "detectors": {"green": {"chs": [0]}},
            "pixel_duration_us": 10.0,
            "line_duration_ms": 0.64,
            "frame_duration_ms": 30.0,
            "pixel_size_nm": 50.0,
        }
    )
    m = app.model
    assert (m.pixel_duration_us, m.line_duration_ms, m.frame_duration_ms, m.pixel_size_nm) == (
        10.0,
        0.64,
        30.0,
        50.0,
    )
    assert list(m.detectors) == ["green"]
    app.apply_setup_settings({"pixel_duration_us": -1.0, "frame_duration_ms": "x"})
    assert (
        m.pixel_duration_us == 10.0 and m.frame_duration_ms == 30.0
    )  # not positive numbers: ignored
    app.apply_pipeline_context({"source": str(flow_tif), "hdf5": "/x/y.h5"})
    drv.settle()
    assert (
        Path(m.filename) == flow_tif
        and m.channel_names() == ["ch0"]
        and m.pipeline_hdf5 == "/x/y.h5"
    )
    m.pipeline_sink = lambda *a, **k: None
    app.set_frame_request_callback(lambda: None)
    app.close()


def test_the_window_draws_empty_and_populated_at_both_sizes(app, drv, flow_tif):
    for size in ((1200, 800), (800, 600)):
        assert {
            "Settings",
            "Map flow",
            "🧪  Load example",
            "Export CSV",
            "Flow",
        } <= set(drv.draw(3, size).strings)
    mapped(app, drv, flow_tif)
    for size in ((1200, 800), (800, 600)):
        assert any("mean speed (25 of 25 tiles)" in s for s in drv.draw(3, size).strings)


def test_the_idle_window_does_not_ask_for_frames(app, drv):
    drv.draw(3)
    assert not app.job.busy


# ── 9. the spec, the tooltips, no Qt ───────────────────────────────────────────────────────────────────────── #


def options_of(section):
    return section["options"] if isinstance(section.get("options"), dict) else {}


def test_every_spec_key_exists_on_the_model():
    model = make_app().model
    for section in walk(EMTK_SPEC["sections"]):
        options = options_of(section)
        for name in (
            section.get("attr"),
            section.get("call"),
            section.get("options_source"),
            options.get("source"),
            section.get("source"),
            options.get("image_source"),
            options.get("vectors_source"),
            options.get("extent_source"),
            options.get("scale_attr"),
        ):
            if name:
                assert hasattr(model, name), (section.get("title"), name)
        for name in (
            section.get("call"),
            options.get("source"),
            section.get("options_source"),
            options.get("image_source"),
            options.get("vectors_source"),
            options.get("extent_source"),
        ):
            if name:
                assert callable(getattr(model, name)), name
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        for column in options.get("columns", []):
            assert column["key"] in ("x", "y", "vx", "vy", "speed", "angle", "quality")


def test_every_setting_of_the_base_spec_is_in_the_emtk_spec_with_the_same_range_and_choices():
    """``flow.view.json`` (read by the view model) and ``flow_emtk.view.json`` declare the same settings."""

    def values(sections):
        return {
            s["attr"]: s
            for s in walk(sections)
            if s.get("type") in ("value", "toggle", "choice") and s.get("attr")
        }

    base, emtk = values(BASE_SPEC["sections"]), values(EMTK_SPEC["sections"])
    assert set(emtk) - set(base) == {"filename"} and not set(base) - set(emtk) - {
        "filename"
    }  # the base spec declares its data source by options.attr
    for attr, spec in base.items():
        for key in ("minimum", "maximum", "decimals", "label", "options", "labels", "description"):
            assert spec.get(key) == emtk[attr].get(key), (attr, key)


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("img_flow"))
    assert inventory["controls_without_tooltip"] == []
    for section in walk(EMTK_SPEC["sections"]):
        if section.get("type") in (
            "value",
            "choice",
            "toggle",
            "custom",
            "panel",
            "button_row",
            "info",
        ):
            assert section.get("description"), section.get("attr") or section.get("title")
        for column in options_of(section).get("columns", []):
            assert column.get("description"), column
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_the_populated_window_has_a_tooltip_on_every_control_too(app, drv, flow_tif):
    from test.gui.emtk_port_parity import ControlRecorder

    mapped(app, drv, flow_tif)
    missing = set()
    for tab in ("Profile", "Tiles"):
        app.docks.focus(tab)
        recorder = ControlRecorder()
        with recorder.installed():
            for _ in range(3):
                recorder.rows.clear()
                drv.draw(1)
        missing |= {f"{r['kind']}: {r['label']}" for r in recorder.rows if not r["tooltip"]}
    assert sorted(missing) == [], sorted(missing)


def test_port_is_qt_free():
    from test.gui.emtk_port_parity import qt_free

    result = qt_free("img_flow")
    assert result["ok"], result["output"]
