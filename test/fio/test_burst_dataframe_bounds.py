"""Burst-summary tables count the photon at the burst's inclusive stop index.

``chisurf.core.math.signal.find_bursts`` — the producer feeding the burst
selection API, the photon-filter wizard and the trace browser — returns
``(start, stop)`` pairs whose ``stop`` is the *last* photon of the burst. The
summary writers must use that same convention for the counts, not only for the
duration; otherwise every burst loses its last photon and the count rate is
biased low by ``N / (N + 1)``.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.datastore import row_count, rows_from_table
from chisurf.core.fio.fluorescence.burst import (
    generate_burst_dataframe,
)
from chisurf.core.math.signal import find_bursts

MACRO_TIME_RESOLUTION = 1e-6  # 1 µs per macro-time unit


class _Header:
    """Minimal stand-in for a TTTR header."""

    def __init__(self, macro_time_resolution: float) -> None:
        self.macro_time_resolution = macro_time_resolution


class _FakeTTTR:
    """Minimal stand-in for a TTTR object with the attributes the writers use."""

    def __init__(self, macro_times, micro_times, routing_channel) -> None:
        self.macro_times = np.asarray(macro_times, dtype=np.int64)
        self.micro_times = np.asarray(micro_times, dtype=np.int64)
        self.routing_channel = np.asarray(routing_channel, dtype=np.int64)
        self.header = _Header(MACRO_TIME_RESOLUTION)

    def __len__(self) -> int:
        return len(self.macro_times)


@pytest.fixture()
def burst_stream() -> _FakeTTTR:
    """Ten burst photons 1 µs apart, then one background photon 1 ms later."""
    macro = list(range(10)) + [1010]
    micro = [100] * 11
    rout = [0] * 11
    return _FakeTTTR(macro, micro, rout)


DETECTORS = {"g": {"chs": [0], "micro_time_ranges": [(0, 4096)]}}
WINDOWS = {"all": (0, 4096)}


def test_find_bursts_stop_is_the_last_burst_photon(burst_stream: _FakeTTTR) -> None:
    """The producer's stop index addresses the burst's last photon."""
    selected = np.zeros(len(burst_stream), dtype=np.uint8)
    selected[:10] = 1
    np.testing.assert_array_equal(find_bursts(selected), np.array([[0, 9]]))


def test_burst_dataframe_counts_the_photon_at_the_stop_index(
    burst_stream: _FakeTTTR,
) -> None:
    """All ten burst photons are counted, globally and per detector/window."""
    df = generate_burst_dataframe(
        start_stop=[(0, 9)],
        filename="synthetic.spc",
        tttr=burst_stream,
        windows=WINDOWS,
        detectors=DETECTORS,
        include_interleaved_zeros=False,
    )

    assert row_count(df) == 1
    row = rows_from_table(df)[0]
    assert row["First Photon"] == 0
    assert row["Last Photon"] == 9
    assert row["Number of Photons"] == 10
    assert row["Number of Photons (g)"] == 10
    # Duration spans the first to the last photon: 9 µs = 0.009 ms.
    assert row["Duration (ms)"] == pytest.approx(9e-3)
    # 10 photons in 9 µs = 1111.1 kHz, the unit the column header states.
    assert row["Count Rate (KHz)"] == pytest.approx(10 / 9e-3)
    assert row["G Count Rate (KHz)"] == pytest.approx(10 / 9e-3)
    assert row["S all g (kHz) | 0-4096"] == pytest.approx(10 / 9e-3)


def test_burst_dataframe_may_end_on_the_last_photon(burst_stream: _FakeTTTR) -> None:
    """A burst reaching the end of the stream is kept, not silently dropped."""
    df = generate_burst_dataframe(
        start_stop=[(0, len(burst_stream) - 1)],
        filename="synthetic.spc",
        tttr=burst_stream,
        windows={},
        detectors={},
        include_interleaved_zeros=False,
    )

    assert row_count(df) == 1
    assert rows_from_table(df)[0]["Number of Photons"] == len(burst_stream)
