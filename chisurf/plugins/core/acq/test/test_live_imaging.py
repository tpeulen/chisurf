"""Imaging acquisition: the scan, the simulated scan, the live image, its quality lights,
the recording and the replay of an image file -- the live image equals tttrlib's CLSMImage."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.core.acq.live import settings_file
from chisurf.plugins.core.acq.live.imaging import (
    ImageRecordSession,
    LiveImage,
    image_replay_source,
    imaging_qc,
    scan_of_file,
)
from chisurf.plugins.core.acq.live.realism import REALISTIC
from chisurf.plugins.core.acq.live.scanner import (
    ImageSimSource,
    ImagingSample,
    ScanSettings,
    marker_bit,
    scan_from_tags,
)
from chisurf.plugins.core.acq.live.sources import SourceUnavailable


def _data(rel: str) -> Path:
    root = Path(os.environ.get("TTTRLIB_DATA", Path.home() / "dev" / "tttr-data"))
    path = root / rel
    if not path.exists():
        pytest.skip(f"{rel} not in the test data ({root})")
    return path


BEADS = "imaging/pq/Microtime200_HH400/beads.ptu"


def _clsm_sum(path) -> np.ndarray:
    data = tttrlib.TTTR(str(path))
    return np.asarray(tttrlib.CLSMImage(tttr_data=data).intensity).sum(axis=0)


def _record(tmp_path, scan, **kw):
    source = ImageSimSource(scan, ImagingSample(**kw), REALISTIC, speed=200.0, realtime=False)
    session = ImageRecordSession(
        source,
        scan,
        duration_s=scan.total_s + 0.01,
        ptu_path=tmp_path / "scan.ptu",
        name="scan",
    )
    session.start()
    result = session.wait(120)
    # the simulated scan ends with its last frame, or the duration ends it: the whole scan either way
    assert result is not None and result.stop_reason in ("duration reached", "source finished")
    return session, result


# -- the scan --------------------------------------------------------------------------------------
def test_marker_numbers_are_picoquant_bits():
    assert [marker_bit(n) for n in (1, 2, 3, 4)] == [1, 2, 4, 8]


def test_a_scan_validates_and_round_trips_through_its_tags():
    scan = ScanSettings(
        pixels_x=40,
        pixels_y=30,
        area_x_um=8.0,
        area_y_um=6.0,
        dwell_ms=0.2,
        frames=4,
        bidirectional=True,
    )
    assert scan.validate() == []
    back, missing = scan_from_tags(scan.imghdr_tags())
    assert missing == []
    for name in (
        "pixels_x",
        "pixels_y",
        "dwell_ms",
        "bidirectional",
        "frames",
        "line_start_marker",
        "line_stop_marker",
        "frame_marker",
    ):
        assert getattr(back, name) == getattr(scan, name), name
    assert back.area_x_um == pytest.approx(8.0)
    assert scan.line_s == pytest.approx(40 * 0.2e-3) and scan.total_s == pytest.approx(
        4 * 30 * 8e-3
    )
    bad = ScanSettings(pixels_x=0, line_start_marker=2, line_stop_marker=2)
    problems = bad.validate()
    assert any(p.startswith("pixels_x") for p in problems)
    assert any("different marker numbers" in p for p in problems)


def test_a_file_without_image_tags_is_not_a_scan():
    scan, missing = scan_from_tags({"MeasDesc_Resolution": 1e-12})
    assert scan is None and "not an image" in missing[0]


# -- the simulated scan, live and recorded ----------------------------------------------------------
def test_the_live_image_equals_clsmimage_of_the_recording(tmp_path):
    scan = ScanSettings(
        pixels_x=32, pixels_y=24, area_x_um=8.0, area_y_um=6.0, dwell_ms=0.05, frames=3
    )
    session, result = _record(tmp_path, scan)
    snap = session.snapshot()
    live = snap["images"]["Intensity"]
    offline = _clsm_sum(result.ptu)
    assert live.shape == offline.shape == (24, 32)
    assert np.array_equal(live, offline)
    assert live.sum() == result.photons > 0
    # the markers were consistent: every finished frame has the scan's lines
    assert snap["lines_done"] == 3 * 24 and snap["lines_in_frame"] == [24, 24]
    assert snap["unclosed_lines"] == 0 and snap["stray_stops"] == 0
    # the recording is a PicoQuant image: typed ImgHdr tags, read back as the scan
    tags = settings_file.read_ptu_tags(result.ptu)
    assert tags["ImgHdr_PixX"] == 32 and tags["ImgHdr_PixY"] == 24
    assert tags["ImgHdr_LineStart"] == 1 and tags["ImgHdr_Frame"] == 3
    assert isinstance(tags["ImgHdr_PixResol"], float) and tags["ImgHdr_BiDirect"] is False
    from chisurf.core.fio.classify import is_photon_image

    assert is_photon_image(result.ptu)


def test_the_imaging_lights(tmp_path):
    scan = ScanSettings(
        pixels_x=32, pixels_y=24, area_x_um=8.0, area_y_um=6.0, dwell_ms=0.05, frames=2
    )
    session, _ = _record(tmp_path, scan)
    qc = session.qc
    lights = {c["name"]: c["light"] for c in qc["checks"]}
    assert (
        qc["ready"] and lights["Lines per frame"] == "green" and lights["Line markers"] == "green"
    )
    assert lights["Pile-up"] == "green"
    snap = session.snapshot()
    # far too bright: the brightest pixel near the laser rate piles up
    hot = imaging_qc(
        {**snap, "max_pixel_rate_hz": 0.3 / ImageSimSource.N_MICRO / 2e-11},
        scan,
        sync_rate_hz=1 / (ImageSimSource.N_MICRO * 2e-11),
    )
    assert {c["name"]: c["light"] for c in hot["checks"]}["Pile-up"] == "red"
    # a lost line marker: a frame with too few lines turns its light red
    broken = imaging_qc({**snap, "lines_in_frame": [24, 23]}, scan, sync_rate_hz=3e7)
    assert {c["name"]: c["light"] for c in broken["checks"]}["Lines per frame"] == "red"
    assert broken["level"] == "red"


def test_settings_round_trip_with_the_scan(tmp_path):
    scan = ScanSettings(pixels_x=16, pixels_y=12, area_x_um=4.0, area_y_um=3.0, dwell_ms=0.05)
    _session, result = _record(tmp_path, scan)
    doc, missing = settings_file.from_ptu(result.ptu)
    back = ScanSettings.from_dict(doc["scan"])
    assert (back.pixels_x, back.pixels_y, back.dwell_ms) == (16, 12, 0.05)
    assert not [m for m in missing if m.startswith("scan")]
    full = settings_file.new_settings(scan=scan.to_dict())
    assert settings_file.validate(full) == []
    assert settings_file.loads(settings_file.dumps(full))["scan"] == scan.to_dict()
    wrong = settings_file.new_settings(scan={**scan.to_dict(), "pixels_x": 0})
    assert any(p.startswith("scan.pixels_x") for p in settings_file.validate(wrong))


# -- replaying an image of the workspace ----------------------------------------------------------
def _replay(path) -> LiveImage:
    source, scan = image_replay_source(str(path), realtime=False)
    chs = sorted(set(source._channel[source._event == 0].tolist()))
    live = LiveImage(
        scan,
        macro_clock_s=source.info.macro_clock_s,
        micro_res_s=source.info.micro_res_s,
        n_micro=source.info.n_micro,
        channels=chs,
    )
    source.start()
    while True:
        batch = source.read(0.1)
        if batch is None:
            if source.finished:
                break
            continue
        live.push(batch)
    live.flush()
    return live


def test_a_replayed_image_equals_clsmimage_of_the_file():
    path = _data(BEADS)
    scan, _missing = scan_of_file(str(path))
    assert (scan.nx, scan.ny, scan.line_start_marker, scan.line_stop_marker) == (50, 50, 3, 4)
    live = _replay(path)
    assert np.array_equal(live.intensity(), _clsm_sum(path))


def test_a_photon_stream_without_a_scan_is_refused():
    path = _data("pq/ptu/pq_ptu_hh_t3.ptu")
    with pytest.raises(SourceUnavailable, match="not an image|no scan markers"):
        image_replay_source(str(path), realtime=False)


def test_a_replay_records_nothing(tmp_path):
    path = _data(BEADS)
    source, scan = image_replay_source(str(path), realtime=False)
    session = ImageRecordSession(source, scan, ptu_path=None, name="replay")
    session.start()
    result = session.wait(120)
    assert result.ptu is None and result.stop_reason == "source finished"
    assert np.array_equal(session.snapshot()["images"]["Intensity"], _clsm_sum(path))
    assert list(tmp_path.iterdir()) == []
