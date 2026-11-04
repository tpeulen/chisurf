"""The Record tool's count-rate dock, plot viewing ranges, the optional stop timer, the
separate-PTU default and the laser drive slider.

Every drive here is the *simulated* laser and the *simulator* source: no hardware is
connected, no program is applied and no emission is switched on (an edit to the program
blocks emission, which the tests assert stays blocked).
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.core.acq.gui.record_app import (
    DOCKS,
    HERE,
    RecordApp,
    RecordModel,
    detector_rates,
    overall_mean_khz,
    _view_limit,
)
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver, hermetic_env

SIZE = (1500, 950)
SHOTS = Path(__file__).resolve().parents[5] / "test" / "native_emtk" / "screenshots"


@pytest.fixture
def model(tmp_path):
    m = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    yield m
    m.close()


@pytest.fixture
def app(tmp_path):
    model = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    application = RecordApp(model)
    yield application
    application.close()


def _pump(ui, model, until, timeout=120.0, max_frames=100_000):
    """Draw frames until *until(model)* holds (the run advances between frames)."""
    end = time.monotonic() + timeout
    for _ in range(max_frames):
        ui.draw(1)
        if until(model):
            return
        assert time.monotonic() < end, "the waited-for state never arrived"
    raise AssertionError("the waited-for state never arrived (frame cap)")


def _run_to_end(ui, model, timeout=180.0):
    _pump(ui, model, lambda m: (not m.running)
          and (m.session is None or m.session.result is not None),
          timeout=timeout)
    ui.draw(3)


# -- the stop timer ----------------------------------------------------------------------------


def test_stop_after_defaults_off_and_gates_the_duration(model):
    assert model.stop_after is False
    assert model.duration_s > 0  # a duration may be set ...
    assert model._run_duration() is None  # ... but without the checkbox nothing stops
    model.stop_after = True
    assert model._run_duration() == pytest.approx(model.duration_s)
    model.duration_s = 0.0
    assert model._run_duration() is None  # 0 stays "no limit"


def test_an_unchecked_run_is_truly_indefinite(model, tmp_path, monkeypatch):
    """Unlimited means unlimited: the run keeps measuring past Duration and only the
    user's Stop ends it."""
    hermetic_env(tmp_path, monkeypatch)
    model.output_dir = tmp_path / "rec"
    model.duration_s = 1.0
    model.stop_after = False
    ui = Driver(RecordApp(model), SIZE)
    ui.click("load_example")
    assert model.start(), model.status_detail
    _pump(ui, model, lambda m: float((m.snapshot or {}).get("elapsed_s", 0.0)) > 1.5)
    assert model.running, "the run stopped by itself despite Stop after being off"
    assert model.session.result is None and not model.session.stop_reason
    model.stop()
    _run_to_end(ui, model)
    assert model.session.result.stop_reason == "stopped"


def test_a_checked_run_stops_on_time(model, tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    model.output_dir = tmp_path / "rec"
    model.stop_after = True
    model.duration_s = 1.0
    ui = Driver(RecordApp(model), SIZE)
    ui.click("load_example")
    assert model.start(), model.status_detail
    _run_to_end(ui, model)
    result = model.session.result
    assert result.stop_reason == "duration reached"
    assert result.elapsed_s == pytest.approx(1.0, abs=1.0)


def test_the_settings_round_trip_carries_stop_after(app):
    saved = app.export_settings()
    assert saved["stop_after"] is False and saved["recording_store"] == "link"
    app.model.stop_after = True
    app.restore_settings(app.export_settings())
    assert app.model.stop_after is True


# -- the separate-PTU default ------------------------------------------------------------------


def test_recordings_default_to_a_separate_ptu_file(model, tmp_path, monkeypatch):
    """The default keeps the .ptu a file of its own (Link), not a copy inside the project."""
    hermetic_env(tmp_path, monkeypatch)
    model.output_dir = tmp_path / "rec"
    assert model.recording_store == "link"
    model.stop_after, model.duration_s = True, 1.0
    ui = Driver(RecordApp(model), SIZE)
    ui.click("load_example")
    assert model.start(), model.status_detail
    _run_to_end(ui, model)
    assert model.session.embed is False
    assert model.saved_path is not None and model.saved_path.exists()


# -- the count-rate dock -----------------------------------------------------------------------


def test_detector_rates_aggregate_the_windows_of_a_detector():
    snap = {
        "trace": {
            "bin_width_s": 1e-3,
            "first_bin": 0,
            "counts": {
                "prompt G|G": np.concatenate([np.full(1000, 100.0), np.zeros(1000)]),
                "delayed G|G": np.full(2000, 50.0),
                "prompt R|G": np.full(2000, 25.0),
            },
        }
    }
    rows = {r["name"]: r for r in detector_rates(snap)}
    assert set(rows) == {"G|G", "R|G"}
    assert rows["G|G"]["mean_khz"] == pytest.approx(100.0)  # (150·1s + 50·1s)/2s
    assert rows["G|G"]["khz"] == pytest.approx(50.0)  # the last second
    assert rows["R|G"]["mean_khz"] == pytest.approx(25.0)
    assert overall_mean_khz(snap) == pytest.approx(125.0)


def test_detector_rates_read_plain_streams_and_tolerate_nothing():
    plain = {"trace": {"bin_width_s": 2e-3, "first_bin": 0,
                       "counts": {"ch0": np.full(500, 10.0), "ch1": np.full(500, 30.0)}}}
    rows = {r["name"]: r for r in detector_rates(plain)}
    assert rows["ch0"]["mean_khz"] == pytest.approx(5.0)
    assert rows["ch1"]["mean_khz"] == pytest.approx(15.0)
    assert overall_mean_khz(plain) == pytest.approx(20.0)
    assert detector_rates(None) == [] and detector_rates({}) == []
    assert overall_mean_khz(None) is None and overall_mean_khz({}) is None


def test_the_count_rate_dock_is_compact_at_the_top_right(app):
    assert ("rates", "Count rates", "main") in DOCKS
    assert app.docks.windows["rates"].workspace
    app.focus_dock("rates")
    ui = Driver(app, SIZE)
    ui.draw(3)
    assert app.docks.windows["rates"].visible
    assert app.form.rects.get("live_rates"), "the rates section is not drawn"


def test_the_count_rate_dock_shows_the_rates_during_a_run(app, tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    app.model.output_dir = tmp_path / "rec"
    ui = Driver(app, SIZE)
    ui.click("load_example")
    assert app.model.start(), app.model.status_detail
    _pump(ui, app.model, lambda m: int((m.snapshot or {}).get("photons", 0)) > 0)
    app.focus_dock("rates")
    ui.draw(3)
    strings = ui.strings()
    assert "G|G" in strings and "R|G" in strings  # one row per detector
    assert any("kHz" in s for s in strings)
    assert "Mean recorded" in strings  # the mean rate row
    assert app.form.rects.get("live_rates")
    app.model.stop()
    _run_to_end(ui, app.model)
    SHOTS.mkdir(parents=True, exist_ok=True)
    painter = ui.draw(2)
    from emtk import testing

    painter = testing.PixelPainter(*SIZE)
    app.draw(painter, 0, 0, *SIZE)
    (SHOTS / "record_count_rates.png").write_bytes(
        testing.png_encode(painter.width, painter.height, painter.px)
    )


def test_the_count_rate_dock_shows_an_idle_devices_input_rates(app):
    app.model.device_rates_hz = [24e6, 1.2e6, 0.8e6]
    app.focus_dock("rates")
    ui = Driver(app, SIZE)
    ui.draw(2)
    strings = ui.strings()
    assert "Detector 0" in strings and "Detector 1" in strings and "Sync" in strings
    # Numeric rates and their automatic units occupy separate aligned columns.
    assert {'24.00', '1.20', '800.00', 'MHz', 'kHz'} <= set(strings)


class _StubInfo:
    def __init__(self, features, model="HydraHarp 400"):
        self.features = features
        self.model = model
        self.number_of_channels = 4


class _StubDevice:
    def __init__(self, features, model="HydraHarp 400"):
        self._info = _StubInfo(features, model)

    def information(self):
        return self._info


def test_an_unchecked_device_run_is_reported_finite_not_unlimited(app):
    """The pqusb backend starts a fixed 1 h when no duration is set: the tool says the run is
    finite instead of selling it as indefinite. A backend without demonstrated unlimited
    semantics gets the caution too."""
    model = app.model
    model.source_kind = "device"
    model.device = _StubDevice(["tttr", "t3", "pqusb"])
    note = model.device_limit_text
    assert "1 h" in note and "unlimited" in note, note
    # the same by driver attribute or model name, whatever the backend reports
    model.device = _StubDevice(["tttr"], model="HydraHarp 400")
    assert "1 h" in model.device_limit_text
    # no backend proves truly-unlimited semantics: the generic caution stands
    model.device = _StubDevice(["tttr"], model="MultiHarp 160")
    caution = model.device_limit_text
    assert "Stop after" in caution, caution
    # a simulator or replay run is not affected: no device caveat there
    model.source_kind = "simulator"
    model.device = _StubDevice(["tttr", "pqusb"])
    assert model.device_limit_text == ""
    model.device = None


def test_the_start_of_an_unchecked_device_run_says_the_limit(app):
    model = app.model
    model.source_kind = "device"
    model.stop_after = False
    model.status_detail = "/tmp/x.ptu"
    model._note_backend_limit()
    assert "1 h" not in model.status_detail  # no device connected: no claim either way
    model.device = _StubDevice(["tttr", "t3", "pqusb"])
    model._note_backend_limit()
    assert "1 h" in model.status_detail
    model.stop_after = True
    model.status_detail = "/tmp/x.ptu"
    model._note_backend_limit()
    assert "1 h" not in model.status_detail  # a checked run stops itself: no caveat
    model.device = None


def test_the_run_panel_draws_the_stop_after_toggle(app):
    ui = Driver(app, SIZE)
    ui.draw(3)
    assert app.form.rects.get("stop_after"), "the Stop after toggle is not drawn"
    assert app.form.rects.get("duration_s"), "the Duration field is not drawn"


# -- the quality table --------------------------------------------------------------------------


def test_quality_rows_carry_metric_value_range_status_and_guidance(model):
    model.snapshot = {
        "qc": {
            "ready": True,
            "level": "amber",
            "checks": [
                {"name": "bursts", "light": "green", "value": "412", "detail": "a good number",
                 "action": "", "range": "100 - 5000"},
                {"name": "crosstalk", "light": "amber", "value": "3.1 %",
                 "detail": "leakage raised", "action": "check the filters"},
                {"name": "P multi", "light": "red", "value": "12 %", "detail": "too concentrated",
                 "action": "dilute the sample"},
            ],
        }
    }
    rows = {r["metric"]: r for r in model.quality_rows()}
    assert set(rows) == {"bursts", "crosstalk", "P multi"}
    assert rows["bursts"]["value"] == "412"
    assert rows["bursts"]["acceptable"] == "100 - 5000"  # the checker's own configured range
    assert rows["crosstalk"]["acceptable"] == "—"  # none configured: none invented
    assert rows["bursts"]["status"] == "good"
    assert rows["crosstalk"]["status"] == "watch"
    assert rows["P multi"]["status"] == "act now"
    assert rows["P multi"]["guidance"] == "dilute the sample"
    model.snapshot = {"qc": {"ready": False, "why": "3 of 30 bursts"}}
    only = model.quality_rows()[0]
    assert only["status"] == "no verdict" and "3 of 30" in only["guidance"]
    model.snapshot = None


def test_the_quality_dock_draws_the_checks_as_a_table(app):
    app.model.ui_mode='advanced';app.model.ui_mode_changed()
    app.model.snapshot = {
        "bursts": 1, "burst_rate_hz": 1.0, "photons": 10, "elapsed_s": 1.0,
        "qc": {"ready": True, "level": "green", "checks": [
            {"name": "bursts", "light": "green", "value": "412", "detail": "fine",
             "action": "", "range": "100 - 5000"},
        ]},
    }
    app.focus_dock("quality")
    ui = Driver(app, SIZE)
    ui.draw(3)
    assert app.form.rects.get("quality_rows"), "the quality table is not drawn"
    strings = ui.strings()
    for column in ("Metric", "Value", "Limit", "Status"):
        assert column in strings, f"the column {column} is missing: {strings[:30]}"
    assert 'Guidance' not in strings  # guidance is available on hover, not as a column
    assert "bursts" in strings and "412" in strings and "100 - 5000" in strings


# -- adjustable plot viewing ranges ------------------------------------------------------------


def test_view_limit_zero_means_auto():
    assert _view_limit(0.0, 0.0, 1.0, 9.0) == (1.0, 9.0)
    assert _view_limit(2.0, 0.0, 1.0, 9.0) == (2.0, 9.0)
    assert _view_limit(0.0, 5.0, 1.0, 9.0) == (1.0, 5.0)
    assert _view_limit(2.0, 5.0, 1.0, 9.0) == (2.0, 5.0)


def test_the_range_fields_are_drawn_and_editable_by_wheel(app):
    app.model.ui_mode='advanced';app.model.ui_mode_changed()
    ui = Driver(app, SIZE)
    ui.draw(3)
    for dock, title, attrs in (
        ('plot_hist', 'Histogram range', ('hist_x_min', 'hist_x_max', 'hist_y_max')),
        ('plot_trace', 'Trace range', ('rates_x_min', 'rates_x_max', 'rates_y_max')),
        ('plot_decays', 'Decay range', ('decays_x_min', 'decays_x_max', 'decays_y_max')),
    ):
        app.focus_dock(dock)
        ui.click(title + '.fold')
        ui.draw(2)
        for attr in attrs:
            assert app.form.rects.get(attr), f"{attr} is not drawn when explicitly expanded"
    app.focus_dock('plot_trace')
    # a click focuses the field, the wheel steps it (view-form number fields)
    rect = ui.reveal("rates_x_max")
    ui.click(rect)
    before = app.model.rates_x_max
    ui.wheel(rect[0] + rect[2] / 2, rect[1] + rect[3] / 2, 3)
    assert app.model.rates_x_max > before, "wheeling the field did not edit the range"


def test_the_ranges_are_applied_to_the_rate_decay_and_histogram_plots(app, tmp_path, monkeypatch):
    import emtk.implot as implot

    hermetic_env(tmp_path, monkeypatch)
    app.model.output_dir = tmp_path / "rec"
    calls: list[tuple[int, float, float]] = []
    original = implot.setup_axis_limits

    def spy(axis, lo, hi, *rest):
        calls.append((int(axis), float(lo), float(hi)))
        return original(axis, lo, hi, *rest)

    monkeypatch.setattr(implot, "setup_axis_limits", spy)
    X1, Y1 = int(implot.AXIS_X1), int(implot.AXIS_Y1)
    model = app.model

    # -- a point run: the histogram and the decays carry the ranges
    ui = Driver(app, SIZE)
    ui.click("load_example")
    model.stop_after, model.duration_s = True, 60.0
    model.hist_x_max, model.decays_x_max = 0.37, 123.0
    assert model.start(), model.status_detail
    _pump(ui, model, lambda m: int((m.snapshot or {}).get("photons", 0)) > 0)
    ui.draw(3)
    assert any(a == X1 and hi == pytest.approx(0.37) for a, _lo, hi in calls), \
        f"the histogram x range was not applied: {calls}"
    app.focus_dock("plot_decays")
    ui.draw(1)
    assert any(a == X1 and hi == pytest.approx(123.0) for a, _lo, hi in calls), \
        f"the decays x range was not applied: {calls}"
    model.stop()
    _run_to_end(ui, model)

    # -- an image run: the rates plot carries the ranges
    calls.clear()
    model.mode = "image"
    model.mode_changed()
    ui.click("load_example")
    model.laser.set_head(200, intensity_pct=100)
    model.laser.set_emission(True)
    model.scan_pixels_x = model.scan_pixels_y = 24
    model.scan_frames = 2
    model.stop_after, model.duration_s = True, 60.0
    model.rates_x_max, model.rates_y_max = 7.5, 13.7
    assert model.start(), model.status_detail
    _pump(ui, model, lambda m: int((m.snapshot or {}).get("photons", 0)) > 0)
    app.focus_dock("plot_trace")
    ui.draw(3)
    assert any(a == X1 and hi == pytest.approx(7.5) for a, _lo, hi in calls), \
        f"the rates x range was not applied: {calls[-12:]}"
    assert any(a == Y1 and hi == pytest.approx(13.7) for a, _lo, hi in calls), \
        f"the rates y range was not applied: {calls[-12:]}"
    model.stop()
    _run_to_end(ui, model)


# -- the laser drive slider --------------------------------------------------------------------


def _laser_ready(app, ui):
    app.model.power_book.records.clear()
    app.model.ui_mode = "advanced"
    app.model.ui_mode_changed()
    app.focus_dock("laser")
    ui.draw(2)
    ui.click("connect_laser")
    ui.draw(2)
    assert app.model.laser_connected
    ui.reveal("laser_power")
    assert app.form.rects.get("laser_power"), "the laser power slider is not drawn"


def _slider_track(ui, head="488 nm"):
    """Use the actual slider, not a same-named cell in the advanced head table."""
    slot = 200 if head in ("488 nm", "485 nm") else 300
    rect = ui.reveal(f"laser_drive_{slot}")
    x0 = rect[0]
    return x0, rect[1] + rect[3] / 2.0


def _head(model, slot):
    return next(h for h in model.laser_program["heads"] if h.get("slot") == slot)


def test_the_laser_power_slider_drags_edits_and_clamps(app, tmp_path):
    ui = Driver(app, SIZE)
    _laser_ready(app, ui)
    model = app.model
    strings = ui.strings()
    assert any(w in strings for w in ("488 nm", "485 nm")) and "640 nm" in strings  # one slider per laser head

    x0, cy = _slider_track(ui)

    # -- drag: the drive follows the pointer, and nothing is energised
    ui.drag((x0 + 15.0, cy), (x0 + 15.0 + 140.0, cy), steps=8)
    dragged = float(_head(model, 200)["intensity_pct"])
    assert dragged > 5.0, f"dragging the slider did not raise the drive: {dragged}"
    assert model.laser.state().emission_blocked, "an edit must block emission"

    # -- type: double-click opens the field, Enter commits
    ui.draw(1)
    app.press(x0 + 200.0, cy, clicks=2)
    ui.draw(2)
    app.release()
    ui.draw(1)
    ui.type_text("88")
    ui.enter()
    ui.draw(1)
    assert float(_head(model, 200)["intensity_pct"]) == pytest.approx(88.0)
    assert model.laser.state().emission_blocked

    # -- a typed value beyond 100 is clamped (ALWAYS_CLAMP), never stored raw
    app.press(x0 + 200.0, cy, clicks=2)
    ui.draw(2)
    app.release()
    ui.draw(1)
    ui.type_text("150")
    ui.enter()
    ui.draw(1)
    assert float(_head(model, 200)["intensity_pct"]) == pytest.approx(100.0)
    assert model.laser.state().emission_blocked

    SHOTS.mkdir(parents=True, exist_ok=True)
    from emtk import testing

    painter = testing.PixelPainter(*SIZE)
    app.draw(painter, 0, 0, *SIZE)
    (SHOTS / "record_laser_power_slider.png").write_bytes(
        testing.png_encode(painter.width, painter.height, painter.px)
    )


# -- session metadata and the archive transfer -------------------------------------------------


def test_session_metadata_round_trips_and_reaches_the_run_header(app):
    m = app.model
    assert (m.operator_name, m.project_name, m.sample_name) == ("", "", "")
    assert (m.experiment_type, m.dye_names) == ("", "")
    m.operator_name, m.project_name = "ada", "lovelace"
    m.sample_name, m.experiment_type = "beads 100 nm", "PIE smFRET"
    m.dye_names = "Atto488+Atto647N"
    tags = m.run_header_tags()
    assert tags["ChiSurf_Operator"] == "ada" and tags["ChiSurf_Project"] == "lovelace"
    assert tags["ChiSurf_Sample"] == "beads 100 nm"
    assert tags["ChiSurf_ExperimentType"] == "PIE smFRET"
    assert tags["ChiSurf_Dyes"] == "Atto488+Atto647N"
    saved = app.export_settings()
    m.operator_name = ""
    app.restore_settings(saved)
    assert m.operator_name == "ada"


def test_the_session_panel_collects_the_metadata(app):
    ui = Driver(app, SIZE)
    ui.draw(2)
    for attr in ("operator_name", "project_name", "sample_name", "experiment_type", "dye_names"):
        assert app.form.rects.get(attr), f"{attr} is not drawn (Session panel)"
    assert app.form.rects.get("transfer_status"), "the transfer line is not drawn"


def _one_recording(app, tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    app.model.output_dir = tmp_path / "rec"
    ui = Driver(app, SIZE)
    ui.click("load_example")
    app.model.stop_after, app.model.duration_s = True, 1.0
    assert app.model.start(), app.model.status_detail
    _run_to_end(ui, app.model)
    return ui


def test_recordings_of_the_session_are_collected_for_the_transfer(app, tmp_path, monkeypatch):
    _one_recording(app, tmp_path, monkeypatch)
    assert app.model.saved_path in app.model.recorded_paths
    assert app.model.saved_path.exists()


def test_the_transfer_hook_gets_the_files_and_progress_and_never_deletes(app, tmp_path, monkeypatch):
    _one_recording(app, tmp_path, monkeypatch)
    m = app.model
    seen = {}

    def hook(paths, progress):
        seen["paths"] = [Path(p) for p in paths]
        progress(0.5, "copying")
        assert "50" in m.transfer_status and "copying" in m.transfer_status, \
            "the progress callback must show itself in the status"
        progress(1.0)

    m.transfer_hook = hook
    assert m.transfer_pending()
    assert seen["paths"] == [m.saved_path]
    assert seen["paths"][0].exists(), "the transfer must not remove the recording"
    assert "Transferred 1" in m.transfer_status


def test_a_failed_transfer_keeps_everything_and_reports_it(app, tmp_path, monkeypatch):
    _one_recording(app, tmp_path, monkeypatch)
    m = app.model

    def bad(paths, progress):
        progress(0.2)
        raise RuntimeError("drive gone")

    m.transfer_hook = bad
    assert not m.transfer_pending()
    assert m.saved_path.exists(), "a failed transfer must not lose the recording"
    assert "drive gone" in m.transfer_status and "stay" in m.transfer_status
    log = Path(m.output_dir) / "transfer_log.jsonl"
    assert log.exists() and "failed" in log.read_text() and str(m.saved_path) in log.read_text()


def test_closing_hands_the_recordings_to_the_hook(app, tmp_path, monkeypatch):
    _one_recording(app, tmp_path, monkeypatch)
    m = app.model
    calls = []
    m.transfer_hook = lambda paths, progress: calls.append([Path(p) for p in paths])
    app.close()  # the fixture closes again: a second close must not lose or duplicate
    assert calls and calls[0] == [m.saved_path]
    assert m.saved_path.exists()
    app.model.transfer_hook = None


def test_without_a_backend_closing_leaves_the_recordings_in_place(app, tmp_path, monkeypatch):
    _one_recording(app, tmp_path, monkeypatch)
    m = app.model
    assert m.transfer_hook is None
    app.close()
    assert m.saved_path.exists()
    assert "No transfer backend" in m.transfer_status
    m.transfer_hook = None
