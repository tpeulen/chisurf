"""A burst summary always carries the mean micro time, per detector, in ns.

``.bur`` was macro-time only. The mean micro time existed nowhere in a burst
folder — the closest thing, a ``bg4`` companion, holds burst-wise *fitted*
lifetimes, which is a biased estimator at the 50–500 photons a burst has. So the
writers now emit ``Mean Microtime (<detector>) (ns)`` for every detector,
alongside the fitted values rather than instead of them, and a burst folder
carries its own lifetime axis (PRD-71).

The column is additive and must stay that way, which is what most of this file
pins:

* it is appended **after every pre-existing column and before the trailing
  blank**, so a reader keying on leading positions is not shifted and ndX's
  trailing-blank strip still finds a blank to strip;
* nanoseconds, not raw channels — a raw-channel value is meaningless without the
  header that produced it, so a file whose header cannot supply a resolution
  writes the sentinel instead of a number in unknown units;
* the sentinel is the ``-1.0`` the neighbouring per-detector columns already use,
  so a reader filtering one filters them all.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from chisurf.core.datastore import (
    column_names,
    numeric_column,
    rows_from_table,
    write_csv_table,
)
from chisurf.core.fio.fluorescence.burst import (
    DETECTOR_SENTINEL,
    generate_burst_dataframe,
    mean_micro_time_ns,
    micro_time_resolution_ns,
)

MACRO_TIME_RESOLUTION = 1e-6  # 1 µs per macro-time unit
MICRO_TIME_RESOLUTION = 1e-11  # 10 ps per micro-time channel

DETECTORS = {
    "green": {"chs": [0], "micro_time_ranges": [(0, 4096)]},
    "red": {"chs": [1], "micro_time_ranges": [(0, 4096)]},
}
WINDOWS = {"prompt": (0, 4096)}


class _Header:
    def __init__(self, macro_time_resolution, micro_time_resolution=None):
        self.macro_time_resolution = macro_time_resolution
        if micro_time_resolution is not None:
            self.micro_time_resolution = micro_time_resolution


class _FakeTTTR:
    def __init__(
        self, macro_times, micro_times, routing_channel, micro_resolution=MICRO_TIME_RESOLUTION
    ):
        self.macro_times = np.asarray(macro_times, dtype=np.int64)
        self.micro_times = np.asarray(micro_times, dtype=np.int64)
        self.routing_channel = np.asarray(routing_channel, dtype=np.int64)
        self.header = _Header(MACRO_TIME_RESOLUTION, micro_resolution)

    def __len__(self) -> int:
        return len(self.macro_times)


#: Four green photons and two red ones, with micro times chosen so both means
#: are exact in floating point: green mean 250 channels, red mean 1500.
GREEN_MICRO = [100, 200, 300, 400]
RED_MICRO = [1000, 2000]


@pytest.fixture()
def two_colour_burst() -> _FakeTTTR:
    macro = [0, 1, 2, 3, 4, 5]
    micro = [
        GREEN_MICRO[0],
        RED_MICRO[0],
        GREEN_MICRO[1],
        GREEN_MICRO[2],
        RED_MICRO[1],
        GREEN_MICRO[3],
    ]
    rout = [0, 1, 0, 0, 1, 0]
    return _FakeTTTR(macro, micro, rout)


@pytest.fixture()
def green_only_burst() -> _FakeTTTR:
    """No red photon at all — the red detector must report the sentinel."""
    return _FakeTTTR([0, 1, 2], GREEN_MICRO[:3], [0, 0, 0])


def _expected_ns(micro_channels) -> float:
    return float(np.mean(micro_channels)) * MICRO_TIME_RESOLUTION * 1e9


def _data_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Drop the interleaved zero rows — data sits on the odd rows."""
    return frame.iloc[1::2]


def _write_bur(out, tttr):
    """Write a real .bur through the one live path (builder + TSV writer)."""
    frame = generate_burst_dataframe([(0, 5)], "m000.ptu", tttr, WINDOWS, DETECTORS)
    write_csv_table(str(out), frame)


def test_helper_converts_channels_to_nanoseconds():
    micro = np.array([100, 200, 300, 400])
    ns = micro_time_resolution_ns(_FakeTTTR([0], [0], [0]))
    assert ns == pytest.approx(MICRO_TIME_RESOLUTION * 1e9)
    assert mean_micro_time_ns(micro, np.arange(4), ns) == pytest.approx(_expected_ns(GREEN_MICRO))


def test_helper_returns_sentinel_without_a_resolution():
    """No resolution in the header means no honest nanosecond value exists."""
    tttr = _FakeTTTR([0], [0], [0], micro_resolution=None)
    assert micro_time_resolution_ns(tttr) == 0.0
    assert mean_micro_time_ns(np.array([100]), np.array([0]), 0.0) == DETECTOR_SENTINEL


def test_helper_returns_sentinel_for_an_empty_selection():
    ns = MICRO_TIME_RESOLUTION * 1e9
    assert (
        mean_micro_time_ns(np.array([100, 200]), np.array([], dtype=int), ns) == DETECTOR_SENTINEL
    )


@pytest.mark.parametrize("detector,micro_channels", [("green", GREEN_MICRO), ("red", RED_MICRO)])
def test_fast_writer_reports_the_mean_micro_time(two_colour_burst, detector, micro_channels):
    frame = generate_burst_dataframe(
        [(0, 5)],
        "m000.ptu",
        two_colour_burst,
        WINDOWS,
        DETECTORS,
        include_interleaved_zeros=False,
    )
    value = numeric_column(frame, f"Mean Microtime ({detector}) (ns)")[0]
    assert value == pytest.approx(_expected_ns(micro_channels))


def test_detector_without_photons_gets_the_shared_sentinel(green_only_burst):
    frame = generate_burst_dataframe(
        [(0, 2)],
        "m000.ptu",
        green_only_burst,
        WINDOWS,
        DETECTORS,
        include_interleaved_zeros=False,
    )
    row = rows_from_table(frame)[0]
    assert row["Mean Microtime (red) (ns)"] == DETECTOR_SENTINEL
    # the same sentinel the neighbouring per-detector columns already use
    assert row["Duration (red) (ms)"] == DETECTOR_SENTINEL
    assert row["Mean Microtime (green) (ns)"] == pytest.approx(_expected_ns(GREEN_MICRO[:3]))


def test_header_without_a_resolution_writes_the_sentinel_not_raw_channels(two_colour_burst):
    """Never write a number whose unit the header cannot justify."""
    two_colour_burst.header = _Header(MACRO_TIME_RESOLUTION, micro_time_resolution=None)
    frame = generate_burst_dataframe(
        [(0, 5)],
        "m000.ptu",
        two_colour_burst,
        WINDOWS,
        DETECTORS,
        include_interleaved_zeros=False,
    )
    for detector in DETECTORS:
        assert numeric_column(frame, f"Mean Microtime ({detector}) (ns)")[0] == DETECTOR_SENTINEL


def test_the_addition_is_positionally_non_breaking(two_colour_burst):
    """Every pre-existing column keeps its index; the new ones precede the blank.

    A reader keying on leading positions rather than on header names must see no
    change at all, and the trailing blank must stay trailing so ndX's strip finds
    it.
    """
    frame = generate_burst_dataframe(
        [(0, 5)],
        "m000.ptu",
        two_colour_burst,
        WINDOWS,
        DETECTORS,
        include_interleaved_zeros=False,
    )
    columns = column_names(frame)

    legacy = [
        "First Photon",
        "Last Photon",
        "Duration (ms)",
        "Mean Macro Time (ms)",
        "Number of Photons",
        "Count Rate (KHz)",
        "Confidence (sigma)",
        "First File",
        "Last File",
    ]
    for d in DETECTORS:
        legacy += [
            f"First Photon ({d})",
            f"Last Photon ({d})",
            f"Duration ({d}) (ms)",
            f"Mean Macrotime ({d}) (ms)",
            f"Number of Photons ({d})",
            f"{d.capitalize()} Count Rate (KHz)",
        ]
    for w, (r0, r1) in WINDOWS.items():
        for d in DETECTORS:
            legacy.append(f"S {w} {d} (kHz) | {r0}-{r1}")
            legacy.append(f"S {w} {d} (photons) | {r0}-{r1}")

    assert columns[: len(legacy)] == legacy
    added = [f"Mean Microtime ({d}) (ns)" for d in DETECTORS]
    assert columns[len(legacy) : len(legacy) + len(added)] == added
    assert columns[-1] == ""
    assert len(columns) == len(legacy) + len(added) + 1


def test_the_reader_picks_the_column_up(tmp_path, two_colour_burst):
    from chisurf.core.fluorescence.burst.table import read_burst_table

    out = tmp_path / "m000.bur"
    _write_bur(out, two_colour_burst)
    columns = read_burst_table(out)
    assert "Mean Microtime (green) (ns)" in columns


def test_the_companion_reader_keeps_it_and_still_strips_the_blank(tmp_path, two_colour_burst):
    """The companion reader drops trailing *empty* columns only — this one survives."""
    ndx_tables = pytest.importorskip("ndxplorer.io.tables")
    import tttrlib

    out = tmp_path / "m000.bur"
    _write_bur(out, two_colour_burst)
    store = ndx_tables.drop_trailing_empty_columns(tttrlib.read_csv(str(out), delimiter="\t"))

    names = list(store.column_names())
    assert "Mean Microtime (green) (ns)" in names
    assert names[-1].strip()
    assert not names[-1].strip().lower().startswith("unnamed")
