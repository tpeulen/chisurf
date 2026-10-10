"""Tests for the photon table: the model, and the Qt-free native app.

The TTTR object is faked with plain numpy attributes — the model reads only
``micro_times``, ``macro_times``, ``routing_channels``,
``header.macro_time_resolution`` and ``get_number_of_micro_time_channels``.
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
    assert lines[0] == "photon\tidx\tchannel\tmicro\tmacro_ms"
    assert len(lines) == 4
    assert lines[1].split("\t")[0] == "0"


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
