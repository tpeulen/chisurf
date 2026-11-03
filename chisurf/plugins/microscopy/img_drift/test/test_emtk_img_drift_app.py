"""The drift-correction app: numbers, every action and every error path.

Hermetic: settings in a temporary folder, files in ``tmp_path``, no network (the database picker gets a
stub client). The oracle is the drift written into the test stack (``data/make_data.py``: every frame is
the first one rolled by (dy, dx) = (2, -1) px per frame), which is known exactly, and the header of the
real photon stream.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.fio.image import imread, imwrite
from chisurf.plugins.emtk_layout import action_caption, help_close_caption
from chisurf.plugins.microscopy.imaging_emtk.testing import (
    Driver,
    dialog_open,
    hermetic_env,
    numeric_ticks,
    pick_from_workspace,
    walk,
)
from chisurf.plugins.microscopy.img_drift import core
from chisurf.plugins.microscopy.img_drift.gui.app import ImgDriftApp, make_app

HERE = Path(__file__).parent
PLUGIN = HERE.parent
REPO = next(p for p in HERE.parents if (p / "pyproject.toml").exists())
DATA = HERE / "data"
BASE_SPEC = json.loads((PLUGIN / "gui" / "drift.view.json").read_text(encoding="utf-8"))
EMTK_SPEC = json.loads((PLUGIN / "gui" / "drift_emtk.view.json").read_text(encoding="utf-8"))
HT3 = REPO / "test/data/clsm/PQ_Olympus_MFIS.ht3"
BIG = (1200, 800)

_make = importlib.util.spec_from_file_location("drift_make_data", DATA / "make_data.py")
assert _make is not None and _make.loader is not None, "data/make_data.py missing"
_data = importlib.util.module_from_spec(_make)
_make.loader.exec_module(_data)


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def drv(app):
    return Driver(app, (1000, 700))


@pytest.fixture
def tiff(tmp_path):
    path = tmp_path / "drift.tif"
    imwrite(path, _data.drifting_stack())
    return path


def measured(app, drv, path):
    """Choose *path* the way a person does (pick it in the Input section) and wait for the automatic measurement."""
    pick_from_workspace(app, path)
    drv.settle()
    return app.model


def shifts_of(model):
    return np.asarray(model.result.shifts, dtype=float)


#: The drift written into the stack, (dy, dx) per frame.
TRUTH = np.array([[2 * k, -k] for k in range(12)], dtype=float)
#: The largest planted displacement, |(22, -11)|.
MAX_DRIFT = float(np.hypot(22, 11))


def status_for(shifts):
    """The status line the app writes for *shifts*: the largest displacement over the frames."""
    return f"Max drift {np.hypot(*np.asarray(shifts).T).max():.1f} px over {len(shifts)} frames."


def expected_rows(shifts):
    """The shift table for *shifts* ((dy, dx) per frame), formatted as the table shows it."""
    return [
        {"frame": k, "dx": f"{dx:+.2f}", "dy": f"{dy:+.2f}", "magnitude": f"{np.hypot(dy, dx):.2f}"}
        for k, (dy, dx) in enumerate(shifts)
    ]


# ── 1. the numbers ──────────────────────────────────────────────────────────────────────────────────────────── #


def test_choosing_a_drifting_stack_measures_exactly_the_injected_drift(app, drv, tiff):
    m = measured(app, drv, tiff)
    assert m.status_line == "Max drift 24.6 px over 12 frames."
    np.testing.assert_array_equal(shifts_of(m), TRUTH)
    assert m.result.total_drift == pytest.approx(MAX_DRIFT, rel=1e-12)
    # the projection sums every frame: its total is the total of the stack
    stack_sum = float(_data.drifting_stack().astype(float).sum())
    assert float(np.asarray(m.before_image()).sum()) == pytest.approx(stack_sum, rel=1e-6)
    assert (
        np.asarray(m.after_image()).std() > 2 * np.asarray(m.before_image()).std() / 2
    )  # sharper: the correction worked
    assert m.channel == "ch0" and m.channel_names == ["ch0"]


def test_the_options_recover_the_planted_drift(app, drv, tiff):
    m = measured(app, drv, tiff)
    m.reference, m.mode, m.smooth, m.subpixel = "previous", "constant", 0.0, True
    drv.click("measure")
    drv.settle()
    np.testing.assert_allclose(shifts_of(m), TRUTH, atol=0.05)  # sub-pixel: near, not on, the grid
    assert m.status_line == status_for(shifts_of(m))
    m.reference, m.mode, m.smooth, m.subpixel = "mean", "wrap", 2.0, False
    drv.click("measure")
    drv.settle()
    on_the_streak(shifts_of(m))
    assert m.status_line == status_for(shifts_of(m))


def on_the_streak(shifts):
    """Against the stack mean (a streak along the drift) each frame lands a whole number of drift steps off its truth."""
    residual = shifts - TRUTH
    steps = residual[:, 1] / -1.0
    np.testing.assert_allclose(residual, np.outer(steps, [2.0, -1.0]), atol=1e-9)
    np.testing.assert_allclose(steps, np.round(steps), atol=1e-9)
    assert np.abs(steps).max() <= len(TRUTH)


@pytest.mark.skipif(not HT3.exists(), reason="CLSM test data not present")
def test_the_real_photon_stream_is_measured_over_its_frames_and_channels(app, drv):
    m = measured(app, drv, HT3)
    assert m.result.kind == "tttr" and m.result.n_frames == 40
    assert m.status_line.endswith("over 40 frames.")
    assert m.channel_names == ["ch0", "ch1", "ch4", "ch5"]  # the routing channels in the header
    assert "No image loaded." not in drv.strings()


def test_the_shift_table_lists_the_planted_drift(app, drv, tiff):
    m = measured(app, drv, tiff)
    shown = [
        {
            "frame": r["frame"],
            "dx": f"{r['dx']:+.2f}",
            "dy": f"{r['dy']:+.2f}",
            "magnitude": f"{r['magnitude']:.2f}",
        }
        for r in m.shift_table_rows()
    ]
    assert shown == expected_rows(TRUTH)
    drv.click_text("Shifts")
    assert {"Frame", "dx / px", "dy / px", "|d| / px"} <= set(drv.draw(2).strings)


# ── 2. every scenario recovers the planted drift ──────────────────────────────────────────────────────────── #

SCENARIOS = {
    "defaults": {},
    "previous frame": {"reference": "previous"},
    "stack mean": {"reference": "mean"},
    "blanking": {"mode": "constant"},
    "no smoothing, subpixel": {"smooth": 0.0, "subpixel": True},
    "heavy smoothing": {"smooth": 6.0},
}


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_every_scenario_recovers_the_planted_drift_in_status_trace_and_table(
    app, drv, tiff, scenario
):
    settings = SCENARIOS[scenario]
    m = measured(app, drv, tiff)
    for k, v in settings.items():
        setattr(m, k, v)
    drv.click("measure")
    drv.settle()
    shifts = shifts_of(m)
    if scenario == "stack mean":
        on_the_streak(shifts)
    elif settings.get("subpixel"):
        np.testing.assert_allclose(shifts, TRUTH, atol=0.05)
    else:
        np.testing.assert_array_equal(shifts, TRUTH)
    assert m.status_line == status_for(shifts)
    series = {s["name"]: s["y"] for s in m.drift_series()}
    np.testing.assert_array_equal(series["dx"], shifts[:, 1])
    np.testing.assert_array_equal(series["dy"], shifts[:, 0])
    np.testing.assert_allclose(series["|d|"], np.hypot(shifts[:, 0], shifts[:, 1]))
    cells = [
        {
            "frame": r["frame"],
            "dx": f"{r['dx']:+.2f}",
            "dy": f"{r['dy']:+.2f}",
            "magnitude": f"{r['magnitude']:.2f}",
        }
        for r in m.shift_table_rows()
    ]
    assert cells == expected_rows(shifts)


@pytest.mark.parametrize("attr", ["smooth"])
def test_typed_extremes_are_clamped_to_the_spec_range(app, drv, attr):
    drv.click("Estimator.fold")
    for typed, clamped in (("1000000000.0", 20.0), ("-5.0", 0.0)):  # the spec's 0 .. 20
        drv.type_into(attr, typed)
        assert getattr(app.model, attr) == pytest.approx(clamped), (attr, typed)


def test_the_choice_lists_offer_only_what_the_core_accepts(app):
    """'middle', 'nearest' and 'reflect' are refused by the core, so the lists do not offer them."""
    spec = {s["attr"]: s for s in walk(EMTK_SPEC["sections"]) if s.get("type") == "choice"}
    for attr, labels in (
        ("reference", ["First frame", "Previous frame", "Stack mean"]),
        ("mode", ["Wrapping (keep all signal)", "Blanking (drop what leaves)"]),
    ):
        assert spec[attr]["labels"] == labels
        assert spec[attr]["options"] == (
            ["first", "previous", "mean"] if attr == "reference" else ["wrap", "constant"]
        )


# ── 3. choosing a file: typed, Browse, Database, drop ─────────────────────────────────────────────────────── #


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
                        "original_filename": "stored_drift.tif",
                    }
                ],
                "total": 1,
            }
        if method == "mmfdb.datasets.open":
            return {"local_path": self.path}
        raise AssertionError(method)


def open_picker(app, drv, tiff):
    import time

    app.picker.client = FakeClient(tiff)
    drv.click("open_database")
    drv.draw(2)
    assert app.picker.is_open
    end = time.monotonic() + 10
    while "stored_drift.tif [raw_data] (tif)" not in drv.draw(1).strings and time.monotonic() < end:
        time.sleep(0.02)


# ── 4. errors ──────────────────────────────────────────────────────────────────────────────────────────────── #


def test_measure_with_nothing_loaded_says_so(app, drv):
    drv.click("measure")
    assert app.model.status_line == "No image loaded."
    assert not app.job.busy and app.model.result is None
    assert "No image loaded." in drv.strings()


def test_a_corrupt_file_reports_the_reason(app, drv, tmp_path):
    bad = tmp_path / "bad.tif"
    bad.write_bytes(b"not a tiff")
    pick_from_workspace(app, bad)
    drv.settle()
    assert app.model.status_line.startswith("Could not read the image:")
    assert app.model.status_line == app.model.status and app.model.result is None
    assert app.model.before_image() is None and "Could not read the image" in " ".join(
        drv.strings()
    )


def test_a_single_frame_file_is_refused_with_a_reason(app, drv, tmp_path):
    one = tmp_path / "one.tif"
    imwrite(one, np.zeros((16, 16), dtype=np.float32))
    pick_from_workspace(app, one)
    drv.settle()
    assert app.model.status_line == "1 frame(s): drift correction needs at least two."
    assert app.model.result is None


def test_a_new_bad_file_clears_the_previous_result(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    assert app.model.result is not None
    bad = tmp_path / "bad.tif"
    bad.write_bytes(b"nope")
    pick_from_workspace(app, bad)
    drv.settle()
    assert (
        app.model.result is None
        and app.model.shift_table_rows() == []
        and app.model.drift_series() == []
    )


def test_the_actions_and_the_form_are_greyed_while_a_run_is_in_flight(app, drv, tiff):
    from chisurf.emtk import job_gate

    # Hold the run open: on a small file it ends within the click's own frames, and the
    # controls were enabled again by the time they were clicked.
    job_gate.arm()
    try:
        app.model.open_path(str(tiff))
        assert app.job.busy
        runs = []
        app.model.measure = lambda: runs.append(1)
        drv.click("measure")
        assert runs == [] and app.job.busy
        drv.click("reference")
        assert "Previous frame" not in drv.draw(1).strings  # the list did not open
        job_gate.release()
        drv.settle()
    finally:
        job_gate.disarm()


def test_a_worker_that_raises_is_reported_not_swallowed(app, drv, tiff, monkeypatch):
    measured(app, drv, tiff)

    def boom(*a, **k):
        raise RuntimeError("correlation exploded")

    monkeypatch.setattr(core, "measure_drift", boom)
    drv.click("measure")
    drv.settle()
    assert "correlation exploded" in app.model.status_line and app.model.result is None


# ── 5. the settings: choices, estimator, toggles ─────────────────────────────────────────────────────────── #


def pick(drv, field, label):
    drv.click(field)
    assert label in drv.draw(1).strings, (field, label)
    drv.click_text(label, last=True)


def test_the_reference_list_offers_the_three_references_and_each_is_picked(app, drv):
    for label, value in (
        ("Previous frame", "previous"),
        ("Stack mean", "mean"),
        ("First frame", "first"),
    ):
        pick(drv, "reference", label)
        assert app.model.reference == value
        assert label in drv.draw(2).strings


def test_the_apply_by_list_offers_wrapping_and_blanking(app, drv):
    pick(drv, "mode", "Blanking (drop what leaves)")
    assert app.model.mode == "constant"
    pick(drv, "mode", "Wrapping (keep all signal)")
    assert app.model.mode == "wrap"


def test_escape_closes_an_open_list_without_choosing(app, drv):
    drv.click("reference")
    assert "Previous frame" in drv.draw(1).strings
    drv.escape()
    assert app.model.reference == "first"


def test_the_channel_list_names_the_channels_of_the_file_and_the_chosen_one_is_measured(app, drv):
    if not HT3.exists():
        pytest.skip("CLSM test data not present")
    measured(app, drv, HT3)
    drv.click("channel")
    shown = drv.draw(1).strings
    assert {"ch0", "ch1", "ch4", "ch5"} <= set(shown)
    drv.click_text("ch4", last=True)
    assert app.model.channel == "ch4"
    drv.click("measure")
    drv.settle()
    expected = core.measure_drift(
        str(HT3), "ch4"
    )  # an independent call of the core on the chosen channel
    np.testing.assert_array_equal(shifts_of(app.model), np.asarray(expected.shifts, dtype=float))
    assert app.model.status_line.startswith("Max drift")


def test_the_estimator_panel_opens_and_smoothing_and_subpixel_refine_the_measurement(
    app, drv, tiff
):
    drv.click("Estimator.fold")
    assert {"smooth", "subpixel"} <= set(app.form.rects)
    measured(app, drv, tiff)
    default = shifts_of(app.model).copy()
    drv.type_into("smooth", "0")
    drv.click("subpixel")
    assert app.model.smooth == 0.0 and app.model.subpixel is True
    drv.click("measure")
    drv.settle()
    np.testing.assert_allclose(shifts_of(app.model), TRUTH, atol=0.05)
    assert not np.array_equal(
        shifts_of(app.model), default
    )  # sub-pixel refinement moved the answer off the whole pixels
    drv.click("subpixel")
    assert app.model.subpixel is False


def test_each_arrow_steps_smoothing_by_one_and_stops_at_its_limits(app, drv):
    drv.click("Estimator.fold")
    x, y, w, h = drv.rect("smooth.stepper")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.smooth == pytest.approx(3.0)
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    drv.click_at(x + w / 2, y + h * 0.75)
    assert app.model.smooth == pytest.approx(0.0)
    drv.type_into("smooth", "20")
    drv.click_at(x + w / 2, y + h * 0.25)
    assert app.model.smooth == 20.0


def test_changing_a_setting_does_not_re_measure_by_itself(app, drv, tiff):
    measured(app, drv, tiff)
    before = app.model.status_line
    pick(drv, "reference", "Stack mean")
    assert not app.job.busy and app.model.status_line == before
    assert app.model.result.total_drift == pytest.approx(MAX_DRIFT)  # still the first-frame result


# ── 6. exports ────────────────────────────────────────────────────────────────────────────────────────────── #


def test_exports_without_a_result_say_so(app, drv):
    drv.click("request_export_stack")
    assert app.model.status_line == "Measure the drift first." and not dialog_open(drv)
    drv.click("request_export_shifts")
    assert app.model.status_line == "Measure the drift first." and not dialog_open(drv)


def test_export_shifts_writes_the_planted_drift_as_csv(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    drv.click("request_export_shifts")
    painter = drv.draw(2)
    assert (
        dialog_open(drv)
        and app.dialog.title == "Export drift shifts"
        and "drift.drift.csv" in painter.strings
    )
    drv.click_text("Save", last=True)
    written = tmp_path / "drift.drift.csv"
    expected = "frame,dx_px,dy_px,magnitude_px\n" + "".join(
        f"{k:.4f},{dx:.4f},{dy:.4f},{np.hypot(dy, dx):.4f}\n" for k, (dy, dx) in enumerate(TRUTH)
    )
    assert written.read_text() == expected
    assert app.model.status_line == f"Wrote {written}" and not dialog_open(drv)


def test_export_stack_writes_the_corrected_tiff(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    drv.click("request_export_stack")
    painter = drv.draw(2)
    assert (
        dialog_open(drv)
        and app.dialog.title == "Export corrected stack"
        and "drift.corrected.tif" in painter.strings
    )
    drv.click_text("Save", last=True)
    drv.settle()
    written = tmp_path / "drift.corrected.tif"
    corrected = np.asarray(imread(str(written)))
    raw = np.asarray(imread(str(tiff)))
    # wrapping moves pixels and drops none: the corrected stack keeps the shape and the total signal
    assert corrected.shape == raw.shape == (12, 128, 128)
    assert float(corrected.sum()) == pytest.approx(float(raw.astype(float).sum()), rel=1e-6)
    assert app.model.status_line == f"Wrote {written}"
    # every corrected frame lies on the first one: the drift is gone
    assert (
        np.abs(corrected[5] - corrected[0]).mean() < 3.0 < np.abs(raw[5] - raw[0]).mean()
    )  # 3.0: the noise floor of two frames


def test_export_dialog_cancel_writes_nothing(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    drv.click("request_export_stack")
    drv.draw(2)
    drv.click_text("Cancel")
    assert not list(tmp_path.glob("*.corrected.tif")) and not dialog_open(drv)


def test_export_to_an_unwritable_place_reports_instead_of_raising(app, drv, tiff, tmp_path):
    measured(app, drv, tiff)
    blocker = tmp_path / "afile"
    blocker.write_text("not a folder")
    app.model.write_shifts(str(blocker / "s.csv"))
    assert app.model.status_line.startswith("Could not write")
    assert "Could not write" in " ".join(drv.strings())
    app.model.write_stack(str(blocker / "c.tif"))
    drv.settle()
    assert app.model.status_line.startswith("Could not write the corrected stack")


# ── 7. the views ─────────────────────────────────────────────────────────────────────────────────────────────── #


def test_every_view_says_what_to_do_before_there_is_a_result(app, drv):
    for tab, message in (
        ("Drift trace", "Choose an image or press Measure"),
        ("Projection", "Measure a file"),
    ):
        drv.click_text(tab)
        assert any(s.startswith(message) for s in drv.draw(2).strings), tab


def test_every_view_is_drawn_after_a_measurement(app, drv, tiff):
    measured(app, drv, tiff)
    for tab, expect in (
        ("Drift trace", {"frame", "displacement / px", "dx", "dy", "|d|"}),
        ("Projection", {"Before", "After", "Colormap", "Reset view"}),
        ("Shifts", {"Frame", "dx / px", "dy / px", "|d| / px"}),
    ):
        drv.click_text(tab)
        strings = set(drv.draw(2).strings)
        assert expect <= strings, (tab, expect - strings)


def test_the_two_projections_share_one_colormap(app, drv, tiff):
    measured(app, drv, tiff)
    drv.click_text("Projection")
    drv.draw(2)
    combos = [t[:4] for t in drv.draw(1).texts if t[5] == "inferno"]
    assert len(combos) == 2
    x, y, w, h = combos[0]
    drv.click_at(x + 10, y + h / 2)
    drv.click_text("viridis", last=True)
    assert app.model.colormap == "viridis"
    assert [t[5] for t in drv.draw(2).texts].count("viridis") == 2  # the second combo followed


def test_a_drag_pans_the_drift_trace_and_an_image(app, drv, tiff):
    measured(app, drv, tiff)
    drv.click_text("Drift trace")
    drv.draw(3)
    x, y, w, h = app.item_rects["Drift trace"]
    before = numeric_ticks(drv.draw(2))
    drv.drag((x + w * 0.5, y + h * 0.5), (x + w * 0.3, y + h * 0.4))
    assert numeric_ticks(drv.draw(2)) != before
    drv.click_text("Projection")
    drv.draw(3)
    bx, by, bw, bh = app.item_rects["before.image"]
    original = numeric_ticks(drv.draw(2))
    drv.drag((bx + bw * 0.5, by + bh * 0.5), (bx + bw * 0.3, by + bh * 0.3))
    assert numeric_ticks(drv.draw(2)) != original
    drv.click_text("Reset view")  # the first one belongs to the Before image
    assert numeric_ticks(drv.draw(3)) == original


def table_values(drv, expect):
    return [t[5] for t in drv.draw(2).texts if t[5] in expect]


def test_the_shift_table_header_sorts_by_value_and_a_row_click_changes_nothing(app, drv, tiff):
    measured(app, drv, tiff)
    drv.click_text("Shifts")
    magnitudes = {f"{r['magnitude']:.2f}" for r in app.model.shift_table_rows()}
    unsorted = table_values(drv, magnitudes)
    assert unsorted == [f"{r['magnitude']:.2f}" for r in app.model.shift_table_rows()]

    def header():
        return [t[:4] for t in drv.draw(1).texts if "|d| / px" in t[5]][0]

    drv.click(header())
    assert table_values(drv, magnitudes) == sorted(unsorted, key=float)
    drv.click(header())
    assert table_values(drv, magnitudes) == sorted(unsorted, key=float, reverse=True)
    before = app.model.export_settings()
    drv.click_text(unsorted[3])
    assert app.model.export_settings() == before and app.model.result is not None


def test_the_wheel_zooms_the_drift_trace(app, drv, tiff):
    measured(app, drv, tiff)
    drv.click_text("Drift trace")
    drv.draw(3)
    before = numeric_ticks(drv.draw(2))
    x, y, w, h = app.item_rects["Drift trace"]
    drv.wheel(x + w / 2, y + h / 2, 3)
    assert numeric_ticks(drv.draw(2)) != before


def test_the_wheel_over_the_smoothing_field_steps_it(app, drv):
    drv.click("Estimator.fold")
    x, y, w, h = drv.rect("smooth")
    drv.wheel(x + w * 0.3, y + h / 2, 1)
    assert app.model.smooth == pytest.approx(3.0)


def test_the_wheel_scrolls_the_settings_window_when_the_form_is_taller_than_it(app):
    drv = Driver(app, (800, 200))
    drv.draw(3)
    top = app.form.rects["measure"][1]
    drv.click("Estimator.fold")
    drv.wheel(150, 150, -5)
    assert app.form.rects["measure"][1] < top
    drv.wheel(150, 150, 8)
    assert app.form.rects["measure"][1] == top


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
    drv = Driver(
        app, BIG
    )  # the card is clear of the form here; see the xfail below for the overlapping case
    drv.click("guide")
    assert app.tour.active
    drv.click_text("Close Tour")
    assert not app.tour.active


def test_the_tour_is_walked_to_the_end_with_the_user_operating_each_highlighted_control(app, tiff):
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
                drv.settle()
            elif target.get("attr") == "filename":
                pick_from_workspace(app, tiff)
                drv.settle()
            elif target.get("name") == "computed":
                drv.click("measure")
                drv.settle()
            drv.draw(2)
            assert not app.tour.awaiting, (
                f"{step['title']}: operating the control did not release the step"
            )
        drv.click_text(
            "Finish ✓" if app.tour.step_idx == len(app.tour.steps) - 1 else "Next ►", last=True
        )
    assert not app.tour.active and app.model.result is not None


def test_the_load_step_explains_and_a_file_chosen_in_the_dialog_loads(app, tiff):
    drv = Driver(app, BIG)
    app.model.folder = str(tiff.parent)
    drv.click("guide")
    app.tour.start(
        next(
            i
            for i, s in enumerate(app.tour.steps)
            if (s.get("target") or {}).get("attr") == "filename"
        )
    )
    drv.draw(2)
    assert not app.tour.awaiting  # Load example already loaded a stack; your own is optional
    pick_from_workspace(app, tiff)
    drv.settle()
    assert app.model.filename.endswith("drift.tif")


def test_every_guide_target_is_a_drawn_control_or_window(app, drv, tiff):
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
            measured(app, drv, tiff)
            drv.draw(3)
            app.tour.start(index)
            drv.draw(3)
            rect = app.tour.get_target_rect(key)
        assert rect and rect[2] > 0 and rect[3] > 0, f"{step['title']}: nothing drawn for {key!r}"
        seen.add(key)
    app.tour.stop()
    assert {"filename", "reference", "channel", "computed", "Drift trace", "Projection"} <= seen


def test_settings_round_trip_and_invalid_values_are_ignored(app, drv):
    app.model.reference, app.model.mode, app.model.smooth, app.model.subpixel = (
        "mean",
        "constant",
        3.5,
        True,
    )
    app.model.colormap, app.model.folder = "viridis", "/tmp"
    saved = json.loads(json.dumps(app.export_settings()))
    other = make_app()
    other.restore_settings(saved)
    assert (
        other.export_settings() == saved
        and other.model.reference == "mean"
        and other.model.mode == "constant"
    )
    other.restore_settings(
        {
            "reference": "middle",
            "mode": "reflect",
            "smooth": "high",
            "subpixel": 3,
            "colormap": 4,
            "folder": 4,
        }
    )
    assert other.export_settings() == saved
    other.restore_settings(None)
    assert "filename" not in saved and "channel" not in saved


def test_a_standalone_tool_takes_no_imaging_pipeline_context(app):
    """Drift Correction is its own ribbon entry, not an Image Tools step: it reads its own stack.

    It adopts neither the shared detector setup nor the pipeline's source, so it has no hub adapters.
    """
    for hook in ("apply_setup_settings", "apply_pipeline_context", "apply_calibration"):
        assert not hasattr(app.model, hook), hook
    app.set_frame_request_callback(lambda: None)
    app.close()


def test_the_window_draws_empty_and_populated_at_both_sizes(app, drv, tiff):
    for size in ((1200, 800), (800, 600)):
        assert {
            "Settings",
            "Measure",
            "Export stack",
            "Export shifts",
        } <= set(drv.draw(3, size).strings)
    measured(app, drv, tiff)
    for size in ((1200, 800), (800, 600)):
        assert any("Max drift 24.6 px" in s for s in drv.draw(3, size).strings)


def test_the_idle_window_does_not_ask_for_frames(app, drv):
    drv.draw(3)
    assert not app.job.busy


# ── 9. the spec, the tooltips, no Qt ───────────────────────────────────────────────────────────────────────── #


def test_every_spec_key_exists_on_the_model():
    model = make_app().model
    for section in walk(EMTK_SPEC["sections"]):
        options = section.get("options") if isinstance(section.get("options"), dict) else {}
        for name in (
            section.get("attr"),
            section.get("call"),
            section.get("options_source"),
            options.get("source"),
        ):
            if name:
                assert hasattr(model, name), (section.get("title"), name)
        for name in (section.get("call"), options.get("source")):
            if name:
                assert callable(getattr(model, name)), name
        for image in options.get("images", []):
            assert callable(getattr(model, image["source"]))
        for button in section.get("buttons", []):
            assert callable(getattr(model, button["action"])), button["action"]
        for column in options.get("columns", []):
            assert column["key"] in ("frame", "dx", "dy", "magnitude")


def test_every_setting_of_the_base_spec_is_in_the_emtk_spec_with_the_same_range():
    """``drift.view.json`` (read by the view model) and ``drift_emtk.view.json`` declare the same settings."""

    def values(sections):
        return {
            s["attr"]: s
            for s in walk(sections)
            if s.get("type") in ("value", "toggle", "choice") and s.get("attr")
        }

    base, emtk = values(BASE_SPEC["sections"]), values(EMTK_SPEC["sections"])
    assert set(base) - {"filename"} == set(emtk) - {"filename"}, set(base) ^ set(emtk)
    for attr, spec in base.items():
        for key in ("minimum", "maximum", "decimals", "label", "options", "labels", "description"):
            assert spec.get(key) == emtk[attr].get(key), (attr, key)


def test_every_control_has_a_tooltip():
    from test.gui.emtk_port_parity import build_emtk_app, emtk_inventory

    inventory = emtk_inventory(build_emtk_app("img_drift"))
    assert inventory["controls_without_tooltip"] == []
    for section in walk(EMTK_SPEC["sections"]):
        if section.get("type") in ("value", "choice", "toggle", "custom", "panel", "button_row"):
            assert section.get("description"), section.get("attr") or section.get("title")
        options = section.get("options") if isinstance(section.get("options"), dict) else {}
        for column in options.get("columns", []):
            assert column.get("description"), column
        for image in options.get("images", []):
            assert image.get("description"), image
        for button in section.get("buttons", []):
            assert button.get("description"), button


def test_the_populated_window_has_a_tooltip_on_every_control_too(app, drv, tiff):
    from test.gui.emtk_port_parity import ControlRecorder

    measured(app, drv, tiff)
    missing = set()
    for tab in ("Drift trace", "Projection", "Shifts"):
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

    result = qt_free("img_drift")
    assert result["ok"], result["output"]
