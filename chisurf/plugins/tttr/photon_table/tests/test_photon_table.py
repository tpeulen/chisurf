"""Tests for the photon table: the model, and the Qt-free native app.

The TTTR object is faked with plain numpy attributes — the model reads only
``micro_times``, ``macro_times``, ``routing_channels``, ``event_types`` (when
present), ``header.macro_time_resolution`` and
``get_number_of_micro_time_channels``. The record kinds of real scans are
checked on ``test/data/clsm`` against tttrlib's own counts.
"""

from __future__ import annotations

import os

import numpy as np
import pytest


class _Header:
    macro_time_resolution = 1.0e-6  # 1 µs per macro-time unit


class _FakeTTTR:
    """A stand-in tttrlib.TTTR: 10 photons over two routing channels."""

    def __init__(self):
        self.micro_times = np.array(
            [10, 200, 3000, 40, 550, 660, 77, 8, 999, 1200], dtype=np.uint32
        )
        self.macro_times = np.array([0, 5, 5, 12, 12, 30, 30, 44, 47, 47], dtype=np.uint64)
        self.routing_channels = np.array([0, 1, 0, 1, 0, 1, 0, 1, 0, 1], dtype=np.uint8)
        self.header = _Header()

    def get_number_of_micro_time_channels(self) -> int:
        return 4096


@pytest.fixture
def model():
    from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

    m = PhotonTableModel()
    m.load_tttr(_FakeTTTR(), "/data/one.ptu")
    return m


# ── the model ─────────────────────────────────────────────────────────────


def test_load_counts_photons_and_channels(model):
    assert model.n_photons == 10
    assert model.used_channels == [0, 1]
    assert model.macro_resolution == pytest.approx(1e-6)
    assert model.n_micro_channels == 4096
    assert model.filename == "/data/one.ptu"


def test_acquisition_time_from_the_last_macro(model):
    # last macro time 47 units × 1 µs
    assert model.acquisition_time_s() == pytest.approx(47e-6)


def test_pages_are_in_file_order(model):
    rows = model.page(0, 4)
    assert [r["idx"] for r in rows] == [0, 1, 2, 3]
    assert rows[0]["channel"] == 0 and rows[1]["channel"] == 1
    # Macro time in ms: 5 units × 1 µs = 0.005 ms.
    assert rows[1]["macro"] == pytest.approx(0.005)


def test_channel_filter_selects_and_renumbers(model):
    rows = model.page(0, 100, channel=1)
    assert [r["photon"] for r in rows] == [0, 1, 2, 3, 4], "Photon numbers the filtered selection"
    assert [r["idx"] for r in rows] == [1, 3, 5, 7, 9]
    assert all(r["channel"] == 1 for r in rows)
    assert model.filtered_count(1) == 5
    assert model.filtered_count(None) == 10


def test_first_index_clamps_into_the_filtered_range(model):
    # Raw index 8 has no counterpart among the five channel-1 photons.
    assert model.clamp_first(8, 4, channel=1) == 1
    assert model.clamp_first(0, 4, channel=1) == 0
    assert model.clamp_first(-5, 4) == 0
    # A page never runs past the end.
    assert model.clamp_first(9, 4) == 6
    # An empty selection clamps to zero.
    assert model.clamp_first(3, 4, channel=99) == 0


def test_tsv_copies_the_visible_rows(model):
    tsv = model.page_tsv(0, 3)
    lines = tsv.strip().splitlines()
    assert lines[0] == "photon\tidx\tkind\tchannel\tmicro\tmacro_ms"
    assert len(lines) == 4
    assert lines[1].split("\t")[0] == "0"


# ── record kinds (photons and markers) ────────────────────────────────────


class _FakeMarkerTTTR(_FakeTTTR):
    """The ten photons with two marker records (event type 1) among them."""

    def __init__(self):
        super().__init__()
        self.event_types = np.array([0, 1, 0, 0, 1, 0, 0, 0, 0, 0], dtype=np.int8)


def test_a_source_without_event_types_is_all_photons(model):
    assert model.n_records == model.n_photons == 10
    assert model.n_markers == 0
    assert {r["kind_key"] for r in model.page(0, 10)} == {"photon"}


def test_markers_of_a_file_that_is_no_scan_are_other_markers():
    from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

    m = PhotonTableModel()
    m.load_tttr(_FakeMarkerTTTR(), "/data/m.ptu")
    assert (m.n_records, m.n_photons, m.n_markers) == (10, 8, 2)
    assert m.kind_counts()["other"] == 2
    assert [r["idx"] for r in m.page(0, 10, kind="markers")] == [1, 4]
    assert [r["kind_key"] for r in m.page(0, 10, kind="markers")] == ["other", "other"]
    assert m.filtered_count(kind="photon") == 8
    # the two filters combine: channel 1 holds markers 1 and photons 3, 5, 7, 9
    assert [r["idx"] for r in m.page(0, 10, channel=1, kind="photon")] == [3, 5, 7, 9]
    assert m.filtered_count(channel=1, kind="markers") == 1


def test_the_kinds_are_declared_once_with_vocabulary_colours():
    import tttrlib

    from chisurf.emtk.task_colors import categories
    from chisurf.plugins.tttr.photon_table.core.model import record_kinds

    if not hasattr(tttrlib, "CLSM_RECORD_PHOTON"):
        pytest.skip("tttrlib predates CLSMRecordKind: rebuild tttrlib")
    kinds = record_kinds()
    assert [k.key for k in kinds] == ["photon", "pixel", "line_start", "line_stop", "frame", "other"]
    codes = sorted(c for k in kinds for c in k.codes)
    assert codes == sorted([
        tttrlib.CLSM_RECORD_PHOTON, tttrlib.CLSM_RECORD_PIXEL_MARKER,
        tttrlib.CLSM_RECORD_LINE_START_MARKER, tttrlib.CLSM_RECORD_LINE_STOP_MARKER,
        tttrlib.CLSM_RECORD_FRAME_MARKER, tttrlib.CLSM_RECORD_OTHER_MARKER,
    ])
    palette = categories()
    fills = [palette[k.colour]["dark"]["fill"] for k in kinds if k.is_marker]
    assert len(set(fills)) == len(fills), "every marker kind has its own colour"
    assert all(k.description for k in kinds)


def _clsm_file(name):
    from pathlib import Path

    import tttrlib

    if not hasattr(tttrlib.CLSMImage, "get_record_kinds"):
        pytest.skip("tttrlib predates CLSMImage.get_record_kinds: rebuild tttrlib")

    repo = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
    path = repo / "test" / "data" / "clsm" / name
    if not path.exists():
        pytest.skip(f"test data not available: {path}")
    return path


@pytest.mark.parametrize("name", ["Leica_SP5.ptu", "Leica_SP8.ptu"])
def test_scan_kinds_equal_tttrlib_counts(name):
    """Every record is listed and each kind is counted as tttrlib's image reading names it."""
    import tttrlib

    from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

    path = _clsm_file(name)
    m = PhotonTableModel()
    m.load_file(path)
    tttr = tttrlib.TTTR(str(path))
    kinds = np.asarray(tttrlib.CLSMImage(tttr, build_pixels=False).get_record_kinds())
    et = np.asarray(tttr.event_types)
    assert m.n_records == len(et)
    assert m.n_photons == int(np.count_nonzero(et == 0))
    counts = m.kind_counts()
    for key, code in [
        ("photon", tttrlib.CLSM_RECORD_PHOTON),
        ("pixel", tttrlib.CLSM_RECORD_PIXEL_MARKER),
        ("line_start", tttrlib.CLSM_RECORD_LINE_START_MARKER),
        ("line_stop", tttrlib.CLSM_RECORD_LINE_STOP_MARKER),
        ("frame", tttrlib.CLSM_RECORD_FRAME_MARKER),
        ("other", tttrlib.CLSM_RECORD_OTHER_MARKER),
    ]:
        assert counts[key] == int(np.count_nonzero(kinds == code)), key
    assert sum(counts.values()) == m.n_records
    assert counts["line_start"] > 0 and counts["frame"] > 0


def test_sp5_marker_channels_follow_the_header():
    """Leica SP5 PTU: the kinds are the marker channels the header declares, counted with numpy.

    The header names frame marker 4, line start 1 and line stop 2. PicoQuant
    markers are bit fields: 210 of the SP5's frame markers share a record with
    the last line's stop (channel 6 = 4|2), and since tttrlib 5d126dec3
    ``CLSMImageInfo.from_header`` declares PTU frame markers as {4, 6}. So all
    231 are frames and none is *other* -- the table follows tttrlib's reading of
    the header, not a routine guess of its own.
    """
    import tttrlib

    from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

    path = _clsm_file("Leica_SP5.ptu")
    m = PhotonTableModel()
    m.load_file(path)
    tttr = tttrlib.TTTR(str(path))
    info = tttrlib.CLSMImageInfo.from_header(tttr.header)
    et = np.asarray(tttr.event_types)
    rc = np.asarray(tttr.routing_channels)
    marker = et == 1
    frames = list(info.marker_frame_start)
    counts = m.kind_counts()
    assert sorted(frames) == [4, 6]
    assert int(np.count_nonzero(marker & (rc == 4))) == 21
    assert int(np.count_nonzero(marker & (rc == 6))) == 210
    assert counts["frame"] == int(np.count_nonzero(marker & np.isin(rc, frames))) == 231
    assert counts["line_start"] == int(np.count_nonzero(marker & (rc == info.marker_line_start)))
    assert counts["line_stop"] == int(np.count_nonzero(marker & (rc == info.marker_line_stop)))
    assert counts["other"] == 0
    assert counts["pixel"] == 0
    rows = m.page(0, 5, kind="frame")
    assert {r["kind"] for r in rows} == {"frame"} and {r["channel"] for r in rows} == set(frames)


def test_standalone_factory_blocks_qt_imports():
    import subprocess
    import sys

    script = """
import sys
class BlockQt:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:
            raise AssertionError('Qt imported: ' + fullname)
sys.meta_path.insert(0, BlockQt())
# the standalone controller was replaced by the native app (gui/app.py, make_app)
from chisurf.plugins.tttr.photon_table.gui.app import make_app
app = make_app()
assert app.model.rows_per_page == 200
assert app.load_file('/missing/file.ptu') is True
app.model.request_open()
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
