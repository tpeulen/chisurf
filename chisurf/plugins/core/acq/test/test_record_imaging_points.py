"""Imaging with a scanner, picking molecules and measuring them point by point in the Record tool.

* the whole flow on the simulator: a scan, *Auto-pick* (the spot finder's single-molecule
  workflow), *Measure points*, each molecule's trace analysed and the table stored with the image;
* the trace analysis against a known answer: spots of one and two molecules with set bleaching
  times give one and two bleaching steps at those times;
* the hardware path without hardware: libphacq's fake TCSPC unit with raster line markers and the
  PI E-725 simulator -- the live image equals tttrlib's reading of the recorded file;
* the scanner from a settings file; a click on the image adds a point; screenshots.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.core.acq.live import settings_file
from chisurf.plugins.core.acq.live.molecules import analyse_point
from chisurf.plugins.core.acq.live.points import BleachDetector, PointSequence
from chisurf.plugins.core.acq.live.realism import REALISTIC
from chisurf.plugins.core.acq.live.scanner import (
    ImagingSample,
    PointSimSource,
    ScanSettings,
    SimScanner,
)
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver

SIZE = (1500, 950)
SHOTS = Path(__file__).resolve().parents[5] / "test" / "native_emtk" / "screenshots"


@pytest.fixture(autouse=True)
def _quiet_hmm():
    logging.getLogger("chisurf.core.math.hmm").setLevel(logging.ERROR)


def _phacq_with(*drivers):
    phacq = pytest.importorskip("phacq")
    have = set(phacq.DriverRegistry.instance().driver_names())
    if not set(drivers) <= have:
        pytest.skip(f"this phacq lacks {set(drivers) - have}")
    return phacq


def _scan_example(model: RecordModel) -> None:
    model.mode = "image"
    model.mode_changed()
    model.load_example()
    if model.laser is not None:
        model.laser.set_head(200, intensity_pct=100)
        model.laser.set_emission(True)
    assert model.start(), model.status_detail
    while model.running:
        model.poll()
        time.sleep(0.02)
    model.poll(force=True)


def test_scan_autopick_and_point_measurements_in_the_simulator(tmp_path, monkeypatch):
    model = RecordModel(output_dir=tmp_path, realtime=False)
    _scan_example(model)
    assert model.image_snapshot["lines_done"] == 64 * 4
    model.autopick_max = 4
    assert model.autopick() == 4
    # the brightest first, and each on a spot of the image
    bright = [p["brightness"] for p in model.points]
    assert bright == sorted(bright, reverse=True)
    image = model.image_snapshot["images"]["Intensity"]
    for p in model.points:
        px, py = model.image_um_to_pixel(p["x_um"], p["y_um"])
        assert image[int(py), int(px)] > np.percentile(image, 90)
    assert model.measure_points()
    assert model.running and not model.enabled("start") and not model.enabled("autopick")
    model.wait_points(120)
    assert not model.running
    assert len(model.molecules) == 4
    for m in model.molecules.values():
        assert m.photons > 0 and m.steps >= 1 and m.bleach_s is not None
        assert m.efficiency is not None and m.lifetime_ns is not None
    rows = model.point_rows()
    assert [r["status"] for r in rows] == ["bleached"] * 4
    assert "stored with the image" in model.molecules_saved
    # each point is a recording of its own, its point in the header (SymPhoTime's tags)
    ptus = sorted(Path(tmp_path).rglob("*_p00*.ptu"))
    assert len(ptus) == 4
    assert model.image_ptu.parent.name == model.image_ptu.stem
    assert all(path.parent == model.image_ptu.parent / "traces" for path in ptus)
    tags = settings_file.read_ptu_tags(ptus[2])
    assert tags["ImgHdr_Dimensions"] == 1 and tags["ImgHdr_Ident"] == 6
    assert tags["ImgHdr_X0"] == pytest.approx(model.points[2]["x_um"])
    assert tags["ChiSurf_Point_SourceImage"] == model.image_ptu.name
    from chisurf.plugins.core.acq.live import provenance
    for result in model.sequence.results:
        assert Path(str(result.session._dataset.address)) == result.run.ptu
        address, _ = provenance._address_of(result.run.dataset_uid)
        assert Path(address) == result.run.ptu
    monkeypatch.setattr(provenance, "_address_of", lambda value: (str(value), ""))
    monkeypatch.setattr(provenance, "_container_record", lambda *args: None)
    assert Path(provenance.backtrace(ptus[2])["image_path"]) == model.image_ptu.resolve()
    import tttrlib
    assert len(tttrlib.TTTR(str(model.image_ptu))) > 0
    assert all(len(tttrlib.TTTR(str(path))) > 0 for path in ptus)


def test_image_and_trace_publication_never_replace_existing_files(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.live.image_storage import allocate_image, publish_point
    import os

    _, image = allocate_image(tmp_path, "scan")
    image.write_bytes(b"original image")
    _, second_image = allocate_image(tmp_path, "scan")
    assert second_image.parent != image.parent
    traces = image.parent / "traces"
    traces.mkdir()
    target = traces / "points_p000.ptu"
    target.write_bytes(b"original trace")
    stage = traces / ".private"
    stage.mkdir()
    staged = stage / target.name
    staged.write_bytes(b"new trace")
    published = publish_point(staged, target)
    assert target.read_bytes() == b"original trace"
    assert published.read_bytes() == b"new trace"
    assert image.read_bytes() == b"original image"
    stage.mkdir()
    staged.write_bytes(b"partial photons")
    monkeypatch.setattr(os, "link", lambda *args: (_ for _ in ()).throw(OSError("unavailable")))
    with pytest.raises(OSError):
        publish_point(staged, target)
    assert staged.read_bytes() == b"partial photons"


def test_successful_publication_survives_cleanup_failure(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.live.image_storage import publish_point

    stage = tmp_path / ".point-recording-private"
    stage.mkdir()
    staged = stage / "trace.ptu"
    staged.write_bytes(b"photons")
    original = Path.unlink
    def reject_stage(path, *args, **kwargs):
        if path == staged:
            raise OSError("cleanup failed")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", reject_stage)
    published = publish_point(staged, tmp_path / "trace.ptu")
    assert published.read_bytes() == b"photons" and staged.read_bytes() == b"photons"


def test_failed_trace_publication_reports_and_retains_recording(tmp_path, monkeypatch):
    import os
    import tttrlib

    model = RecordModel(output_dir=tmp_path, realtime=False)
    _scan_example(model)
    model.add_point(2, 2)
    model.point_time_s = 0.03
    monkeypatch.setattr(os, "link", lambda *args: (_ for _ in ()).throw(OSError("link failed")))
    assert model.measure_points()
    model.wait_points(30)
    staged = list((model.image_ptu.parent / "traces").glob(".point-recording-*/*.ptu"))
    assert len(staged) == 1 and str(staged[0]) in model.sequence.error
    assert len(tttrlib.TTTR(str(staged[0]))) > 0
    from chisurf.plugins.core.acq.live import provenance
    monkeypatch.setattr(provenance, "_address_of", lambda value: (str(value), ""))
    monkeypatch.setattr(provenance, "_container_record", lambda *args: None)
    assert Path(provenance.backtrace(staged[0])["image_path"]) == model.image_ptu.resolve()
    model.close()


@pytest.mark.parametrize("name", ["../outside", "/tmp/outside", "dir/scan", "dir\\scan", "..", "C:scan"])
def test_recording_names_cannot_escape_output_directory(tmp_path, name):
    from chisurf.plugins.core.acq.live.image_storage import allocate_image, point_paths
    with pytest.raises(ValueError):
        allocate_image(tmp_path, name)
    with pytest.raises(ValueError):
        point_paths([tmp_path], name)
    model = RecordModel(output_dir=tmp_path)
    model.run_name = name
    assert not model.start()
    model.add_point(1, 1)
    assert not model.measure_points()
    model.close()


def test_mixed_image_points_are_written_to_their_own_image(tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.live import provenance

    model = RecordModel(output_dir=tmp_path)
    first, second = tmp_path / "one.ptu", tmp_path / "two.ptu"
    model.image_ptu, model.image_uid = first, "one"
    a = model.add_point(1, 1)
    model.image_ptu, model.image_uid = second, "two"
    b = model.add_point(2, 2)
    for p in (a, b):
        p["dataset_uid"] = f"point-{p['index']}"
        model.molecules[p["index"]] = object()
    writes = []
    monkeypatch.setattr(provenance, "write_point_record", lambda *args: None)
    monkeypatch.setattr(provenance, "write_image_points",
                        lambda path, uid, points: writes.append((path, uid, list(points))))
    model._record_points()
    assert writes == [(str(first), "one", [a]), (str(second), "two", [b])]
    outputs = []
    monkeypatch.setattr(model, "molecule_table", lambda points: ({"n": [len(points)]}, {}))
    monkeypatch.setattr(provenance, "_put", lambda path, uid, *args, **kw:
                        outputs.append((path, uid, args[1])) or path)
    model._store_molecules()
    assert [(path, uid, table["n"]) for path, uid, table in outputs] == [
        (str(first), "one", [1]), (str(second), "two", [1])]
    model.close()


class _SetBleaching(PointSimSource):
    """The simulated focus with the emitters and bleaching times the test sets."""

    def __init__(self, *args, spots, **kwargs):
        super().__init__(*args, **kwargs)
        self.spots = spots  # {(x, y): [bleach_s, ...]}, emitters at the spot's centre

    def start(self):
        x, y = (float(v) for v in self.scanner.position())
        self._emitters = [(x, y, 0)] * len(self.spots[(x, y)])
        super().start()
        self.truth["bleach_s"] = list(self.spots[(x, y)])


def test_bleaching_steps_and_times_are_recovered(tmp_path):
    """Spots of one and two molecules, bleaching at set times: the trace analysis (binning of
    the intensity-trace tool, the shared HMM) finds one and two steps at those times."""
    spots = {(1.0, 1.0): [1.0], (2.0, 1.0): [0.8, 2.0], (3.0, 1.0): [1.5, 3.0],
             (4.0, 1.0): [2.2]}
    scanner = SimScanner()
    sample = ImagingSample(n_beads=0, bead_brightness=40.0, cell=False)
    source = _SetBleaching(scanner, ScanSettings(), sample, REALISTIC, realtime=False,
                           spots=spots)
    seq = PointSequence(scanner, source, ScanSettings(points=list(spots), point_ms=4500),
                        out_dir=tmp_path, name="steps")
    results = seq.run()
    assert len(results) == 4
    for r in results:
        truth = spots[r.target]
        m = analyse_point(r.run.ptu, r.index, r.target)
        assert m.steps == len(truth), (r.target, m.steps, m.state_khz)
        assert m.bleach_s == pytest.approx(max(truth), abs=0.05)
        assert m.on_s == pytest.approx(max(truth), abs=0.05)
        # every molecule adds its brightness: the brightest level is n x 40 kHz (+ background)
        assert max(m.state_khz) == pytest.approx(40.0 * len(truth), rel=0.1)


def test_the_point_trace_is_live_with_the_bleach_rule(tmp_path):
    spots = {(1.0, 1.0): [0.8]}
    scanner = SimScanner()
    sample = ImagingSample(n_beads=0, bead_brightness=40.0, cell=False)
    source = _SetBleaching(scanner, ScanSettings(), sample, REALISTIC, realtime=False,
                           spots=spots)
    seq = PointSequence(scanner, source, ScanSettings(points=list(spots), point_ms=4000),
                        out_dir=tmp_path, until_bleached=True,
                        bleach=lambda: BleachDetector(background_kcps=1.4))
    (result,) = seq.run()
    trace = result.session.point_trace()
    assert result.run.stop_reason == "bleached"
    assert trace["bleached_at_s"] == pytest.approx(0.8, abs=0.1)
    assert trace["threshold_kcps"] < trace["level_kcps"]
    total = sum(trace["counts"].values()) / trace["bin_s"] / 1e3
    assert np.mean(total[10:60]) == pytest.approx(41.4, rel=0.15)
    assert np.nanmean(trace["mean_arrival_ns"][:60]) > 1.0


def test_a_real_scan_path_fake_tcspc_and_the_pi_simulator(tmp_path):
    """The device records the line markers of the raster (libphacq's fake unit standing in for
    the HydraHarp with the E-725's trigger outputs cabled to its marker inputs) while the PI
    simulator rasters: the image builds from the markers, equals tttrlib's reading of the file,
    the file carries SymPhoTime's ImgHdr tags, and the points are measured on the device."""
    _phacq_with("fake", "pi")
    import tttrlib

    from chisurf.plugins.core.acq.live import devices

    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.mode, model.source_kind = "image", "device"
    dev = devices.open_device("fake:")
    for name, value in (("raster_lines", 16), ("raster_line_ms", 3.2), ("raster_gap_ms", 1.0),
                        ("raster_delay_ms", 1.0)):
        dev.set_parameter(name, float(value))
    model.device = dev
    model._device_form_from_device()
    assert not model.enabled("start")  # a real scan needs the scanner
    # the fake unit's raster markers are its inputs 1 and 2 (the MT200's are 3 and 4, falling)
    assert model.connect_scanner({"driver": "pi", "address": "sim:",
                                  "line_markers": {"start": 1, "stop": 2, "edge": "rising"},
                                  "settings": {"learn_s": 0.5}})
    assert model.enabled("start")
    model.set_scan({"pixels_x": 32, "pixels_y": 16, "area_x_um": 3.2, "area_y_um": 1.6,
                    "x0_um": 10.0, "y0_um": 10.0, "dwell_ms": 0.1, "frames": 1})
    assert model.start(), model.status_detail
    while model.running:
        model.poll()
        time.sleep(0.02)
    model.poll(force=True)
    snap = model.image_snapshot
    assert snap["lines_done"] == 16 and snap["unclosed_lines"] == 0
    recorded = np.asarray(tttrlib.CLSMImage(tttr_data=tttrlib.TTTR(str(model.saved_path)))
                          .intensity).sum(axis=0)
    assert np.array_equal(recorded, snap["images"]["Intensity"].astype(int))
    tags = settings_file.read_ptu_tags(model.saved_path)
    assert tags["ImgHdr_PixX"] == 32 and tags["ImgHdr_PixY"] == 16
    assert tags["ImgHdr_LineStart"] == 1 and tags["ImgHdr_LineStop"] == 2
    assert "ImgHdr_Frame" not in tags  # the E-725 sends no frame marker
    assert tags["ImgHdr_X0"] == pytest.approx(10.0)
    model.add_point(11.0, 10.5)
    model.add_point(12.0, 11.0)
    model.point_time_s = 0.3
    assert model.measure_points(), model.status_detail
    model.wait_points(60)
    assert [p["status"] for p in model.points] == ["done", "done"]
    assert model.scanner.position() == pytest.approx((12.0, 11.0))
    model.close()


def test_the_scanner_comes_from_the_settings_file(tmp_path):
    _phacq_with("pi")
    doc = settings_file.new_settings(name="scan", scanner={
        "driver": "pi", "address": "sim:", "settings": {"learn_s": 2.0},
        "line_markers": {"start": 3, "stop": 4, "edge": "falling"}})
    assert settings_file.validate(doc) == []
    bad = settings_file.new_settings(scanner={"driver": "galvo", "settings": {"learn_s": -1}})
    problems = " ".join(settings_file.validate(bad))
    assert "scanner.driver" in problems and "scanner.settings.learn_s" in problems
    for path, _name in settings_file.shipped_profiles():
        profile = settings_file.load(path)
        if Path(path).name.startswith("mt200"):
            assert profile["scanner"]["driver"] == "pi" and profile["scanner"]["address"] == ""
    model = RecordModel(output_dir=tmp_path, realtime=False)
    model.source_kind = "simulator"
    assert model.adopt_settings(doc, "scan", [])
    assert model.scanner is not None and model.scanner.device.get_parameter("learn_s") == 2.0
    # the form: the stage position; the controller's timing in Advanced; never the raster
    simple = set(model.scanner_form.params())
    assert {"x_um", "y_um"} <= simple and "learn_s" not in simple and "pixels_x" not in simple
    model.advanced = True
    model.advanced_changed()
    assert "learn_s" in model.scanner_form.params()
    saved = model.form_settings()
    assert saved["scanner"]["address"] == "sim:" and saved["scanner"]["settings"]["learn_s"] == 2.0
    model.close()


def test_picking_on_the_image_and_the_screens(tmp_path):
    """A click adds a point, Auto-pick adds the molecules, the table and the image show them; a
    point measurement draws its live trace with the bleach rule; a finished molecule's row shows
    its trace and HMM path. Screenshots of the three states."""
    from emtk.export import save_png

    model = RecordModel(output_dir=tmp_path, realtime=False)
    app = RecordApp(model)
    try:
        ui = Driver(app, SIZE)
        model.mode = "image"
        model.mode_changed()
        ui.draw(2)
        assert app.docks.windows["points"].visible
        ui.click("load_example")
        if model.laser is not None:
            model.laser.set_head(200, intensity_pct=100)
            model.laser.set_emission(True)
        ui.click("start")
        while model.running:
            ui.draw(1)
            time.sleep(0.02)
        ui.draw(3)
        x, y, w, h = ui.rect("live_image")
        ui.hover(x + w * 0.3, y + h * 0.5)  # the pointer arrives, then presses: not a pan
        ui.click_at(x + w * 0.3, y + h * 0.5)
        assert len(model.points) == 1 and model.points[0]["origin"] == "click"
        app.focus_dock("points")
        ui.draw(1)
        ui.click("autopick")
        ui.draw(2)
        assert len(model.points) > 5
        ui.hover(5, SIZE[1] - 10)
        ui.draw(2)
        SHOTS.mkdir(parents=True, exist_ok=True)
        save_png(app, str(SHOTS / "record_points_picked.png"), size=SIZE)
        model.clear_points()
        model.autopick_max = 3
        model.autopick()
        model.realtime = True  # the points at measurement pace: a live trace to look at
        model.point_time_s = 2.0
        ui.click("measure_points")
        end = time.monotonic() + 1.5
        while time.monotonic() < end:
            ui.draw(1)
            time.sleep(0.03)
        assert "Point" in " ".join(ui.strings())
        ui.hover(5, SIZE[1] - 10)
        ui.draw(1)
        save_png(app, str(SHOTS / "record_points_running.png"), size=SIZE)
        model.realtime = False
        while model.running or not model._sequence_finished:
            ui.draw(1)
            time.sleep(0.05)
        ui.draw(3)
        model.selected_point = model.points[0]["index"]
        app.focus_dock("plot_trace")
        ui.draw(3)
        assert "Molecule 1" in " ".join(ui.strings())
        save_png(app, str(SHOTS / "record_points_done.png"), size=SIZE)
        # the ✕ of a row removes its point
        n = len(model.points)
        model.remove_point_row(model.point_rows()[-1])
        assert len(model.points) == n - 1
    finally:
        app.close()


def test_the_line_markers_come_from_the_settings_file():
    """Which marker inputs carry the scanner's line triggers is the instrument's cabling: the
    settings file declares it (the MT200 profiles: 3 and 4, falling), nothing is assumed."""
    import json
    from pathlib import Path

    from chisurf.plugins.core.acq.live import settings_file
    from chisurf.plugins.core.acq.live.scanner import ScanSettings
    from chisurf.plugins.core.acq.live.scanning import line_markers, scanner_scan

    profiles = Path(settings_file.__file__).resolve().parents[1] / "profiles"
    for path in sorted(profiles.glob("mt200_*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        assert line_markers(doc["scanner"]) == {"start": 3, "stop": 4, "edge": "falling"}
    scan = scanner_scan(ScanSettings(), {"start": 3, "stop": 4, "edge": "falling"})
    assert (scan.line_start_marker, scan.line_stop_marker, scan.frame_marker) == (3, 4, 0)
    for bad in ({}, {"line_markers": {"start": 3, "stop": 3, "edge": "falling"}},
                {"line_markers": {"start": 3, "stop": 5, "edge": "falling"}},
                {"line_markers": {"start": 3, "stop": 4, "edge": "both"}}):
        with pytest.raises(ValueError):
            line_markers(bad)
    problems = settings_file.validate({"scanner": {"driver": "pi", "address": ""}})
    assert any("line_markers" in p for p in problems)
