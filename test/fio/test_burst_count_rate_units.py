"""Every ``… Count Rate (KHz)`` column of a burst summary is in kHz.

``generate_burst_dataframe`` computes the burst duration in **milliseconds**, so
photons-per-duration is already kilohertz. Scaling that by ``1e-3`` a second time
wrote megahertz under a ``(KHz)`` header while the per-detector rates in the very
same row stayed in kHz — one burst row carrying two rate families 1000× apart
(RF-052 / RF-896). The tests below pin the unit against an exactly known rate and
pin the invariant that ties the two families together: a burst's total rate can
never be below the rate of any single detector inside it.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.datastore import rows_from_table
import pandas as pd
import pytest

from chisurf.core.fio.fluorescence.burst import (
    generate_burst_dataframe,
    write_bur_file_old,
)

MACRO_TIME_RESOLUTION = 1e-6  # 1 µs per macro-time unit

DETECTORS = {
    "green": {"chs": [0], "micro_time_ranges": [(0, 4096)]},
    "red": {"chs": [1], "micro_time_ranges": [(0, 4096)]},
}
WINDOWS = {"prompt": (0, 4096)}


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
def two_photon_burst() -> _FakeTTTR:
    """Two photons exactly 1 ms apart — a burst of exactly 2 kHz."""
    return _FakeTTTR([0, 1000], [100, 100], [0, 0])


@pytest.fixture()
def two_colour_burst() -> _FakeTTTR:
    """Five green and five red photons interleaved over 9 µs."""
    macro = list(range(10))
    micro = [100] * 10
    rout = [0, 1] * 5
    return _FakeTTTR(macro, micro, rout)


def test_the_total_count_rate_is_kilohertz(two_photon_burst: _FakeTTTR) -> None:
    """Two photons 1 ms apart are written as 2.0, not 0.002."""
    df = generate_burst_dataframe(
        start_stop=[(0, 1)],
        filename="synthetic.spc",
        tttr=two_photon_burst,
        windows={},
        detectors={},
        include_interleaved_zeros=False,
    )

    row = rows_from_table(df)[0]
    assert row["Duration (ms)"] == pytest.approx(1.0)
    assert row["Number of Photons"] == 2
    assert row["Count Rate (KHz)"] == pytest.approx(2.0)


def test_the_total_rate_is_at_least_every_detector_rate(
    two_colour_burst: _FakeTTTR,
) -> None:
    """The two ``(KHz)`` column families share one unit, so the total dominates."""
    df = generate_burst_dataframe(
        start_stop=[(0, 9)],
        filename="synthetic.spc",
        tttr=two_colour_burst,
        windows=WINDOWS,
        detectors=DETECTORS,
        include_interleaved_zeros=False,
    )

    row = rows_from_table(df)[0]
    total = row["Count Rate (KHz)"]
    assert total == pytest.approx(10 / 9e-3)
    for det_name in DETECTORS:
        rate = row[f"{det_name.capitalize()} Count Rate (KHz)"]
        assert rate > 0.0
        assert total >= rate


def test_both_writers_agree_on_the_count_rate(two_photon_burst: _FakeTTTR, tmp_path) -> None:
    """The legacy TSV writer and the fast one report the same rate for one burst."""
    bur = tmp_path / "synthetic.bur"
    write_bur_file_old(
        str(bur),
        [(0, 1)],
        "synthetic.spc",
        two_photon_burst,
        WINDOWS,
        DETECTORS,
    )
    legacy = pd.read_csv(bur, sep="\t")
    legacy = legacy[legacy["Number of Photons"] > 0].iloc[0]

    fast = generate_burst_dataframe(
        start_stop=[(0, 1)],
        filename="synthetic.spc",
        tttr=two_photon_burst,
        windows=WINDOWS,
        detectors=DETECTORS,
        include_interleaved_zeros=False,
    )
    fast = rows_from_table(fast)[0]

    assert legacy["Count Rate (KHz)"] == pytest.approx(2.0)
    assert fast["Count Rate (KHz)"] == pytest.approx(legacy["Count Rate (KHz)"])
