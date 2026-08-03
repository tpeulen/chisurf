"""Tests for the shared burst-to-photons seam.

``Last Photon`` in a ``.bur`` table is the burst's last photon **inclusive** —
that is what the writer stores (``Number of Photons == last - first + 1``) and
what every photon-by-photon analysis inherits through
:func:`chisurf.core.fluorescence.burst.photons.extract_burst_photons`. These
tests pin that convention on both sides of the seam, so an exclusive slice
cannot creep back in and quietly shorten every burst by one photon.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from chisurf.core.fio.fluorescence.burst import generate_burst_dataframe
from chisurf.core.fluorescence.burst.photons import (
    StreamDef,
    default_streams,
    extract_burst_photons,
)

N_PHOTONS = 400
CHANNELS = (0, 1, 8, 9)


class FakeHeader:
    """Minimal stand-in for ``tttrlib.TTTR.header``."""

    macro_time_resolution = 1e-8


class FakeTTTR:
    """Minimal stand-in for ``tttrlib.TTTR``.

    Carries only the three per-photon arrays the burst seam reads, plus the
    spellings (``routing_channel``, ``header``, ``__len__``) the ``.bur`` writer
    additionally needs.
    """

    def __init__(self, n: int = N_PHOTONS) -> None:
        self.macro_times = np.arange(n, dtype=np.int64) * 10
        self.routing_channels = np.asarray(
            [CHANNELS[i % len(CHANNELS)] for i in range(n)], dtype=np.int8
        )
        self.micro_times = (np.arange(n, dtype=np.uint16) * 7) % 1024
        self.header = FakeHeader()

    @property
    def routing_channel(self) -> np.ndarray:
        """Alias used by the ``.bur`` writer."""
        return self.routing_channels

    def __len__(self) -> int:
        """Return the number of photons in the stream."""
        return len(self.macro_times)


def burst_table(pairs) -> pd.DataFrame:
    """Build a minimal burst table from ``(first, last)`` photon-index pairs."""
    return pd.DataFrame(
        {
            "First File": ["m.ptu"] * len(pairs),
            "First Photon": [int(a) for a, _ in pairs],
            "Last Photon": [int(b) for _, b in pairs],
        }
    )


@pytest.fixture
def tttrs():
    return {"m.ptu": FakeTTTR()}


def test_last_photon_is_inclusive(tttrs):
    """A burst declared ``100..109`` must come back with ten photons."""
    df = burst_table([(100, 109)])
    times, streams, micro, chan, index = extract_burst_photons(
        df, tttrs, default_streams(), min_photons=1, with_meta=True
    )
    assert len(times) == 1
    assert times[0].size == 10
    assert streams[0].size == 10
    assert micro[0].size == chan[0].size == 10
    np.testing.assert_array_equal(index[0], np.arange(100, 110))


def test_single_photon_burst_is_kept(tttrs):
    """``First Photon == Last Photon`` is one photon, not an empty burst."""
    df = burst_table([(300, 300)])
    times, _, _, _, index = extract_burst_photons(
        df, tttrs, default_streams(), min_photons=1, with_meta=True
    )
    assert len(times) == 1
    assert times[0].size == 1
    np.testing.assert_array_equal(index[0], np.asarray([300]))


def test_inverted_row_is_dropped(tttrs):
    """A row whose last photon precedes its first is not a burst."""
    df = burst_table([(50, 49)])
    times, _ = extract_burst_photons(df, tttrs, default_streams(), min_photons=1)
    assert times == []


def test_matches_the_writers_photon_count(tttrs):
    """Round trip: the extracted count equals the table's ``Number of Photons``.

    The table is produced by the real ``.bur`` writer, so this pins the two
    sides of the convention against each other rather than against a literal.
    """
    tttr = tttrs["m.ptu"]
    start_stop = [(10, 19), (100, 100 + 3), (250, 297)]
    df = generate_burst_dataframe(
        start_stop,
        "m.ptu",
        tttr,
        windows={},
        detectors={
            "green": {"chs": [0, 8], "micro_time_ranges": [(0, 1024)]},
            "red": {"chs": [1, 9], "micro_time_ranges": [(0, 1024)]},
        },
    )
    # Every routing channel belongs to a stream, so nothing is filtered out and
    # the extracted length is the burst length.
    streams = [StreamDef("all", list(CHANNELS), [])]
    times, _, rows = extract_burst_photons(df, tttrs, streams, min_photons=1, with_rows=True)

    declared = df["Number of Photons"].to_numpy()[rows]
    assert len(times) == len(start_stop)
    np.testing.assert_array_equal([t.size for t in times], declared)


def test_interleaved_sentinel_rows_are_not_bursts(tttrs):
    """The writer's zero rows carry no known file and must never be extracted."""
    tttr = tttrs["m.ptu"]
    df = generate_burst_dataframe(
        [(10, 19)],
        "m.ptu",
        tttr,
        windows={},
        detectors={"green": {"chs": [0, 8], "micro_time_ranges": [(0, 1024)]}},
    )
    assert len(df) > 1  # interleaved zero rows are present
    times, _ = extract_burst_photons(df, tttrs, default_streams(), min_photons=1)
    assert len(times) == 1
