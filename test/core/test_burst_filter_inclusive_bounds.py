"""SDK burst intervals include their last photon; background excludes all of them."""

from pathlib import Path

import numpy as np
import pytest
import tttrlib

from chisurf.core.fluorescence.burst.burst import burst_filter
from chisurf.core.fluorescence.burst.utils import create_array_with_ones


@pytest.mark.parametrize(
    "pairs,length,selected",
    [
        ([[1, 3]], 5, [1, 2, 3]),
        ([[3, 3]], 5, [3]),
        ([[2, 4]], 5, [2, 3, 4]),
        ([[0, 4]], 5, [0, 1, 2, 3, 4]),
        ([[0, 2], [2, 4]], 6, [0, 1, 2, 3, 4]),
        ([[0, 1], [4, 5]], 7, [0, 1, 4, 5]),
        ([], 5, []),
    ],
)
def test_filter_translates_inclusive_intervals_only_at_sdk_boundary(pairs, length, selected):
    """Last photons survive unions, gaps and the terminal array boundary."""

    class SearchResult:
        """Represent the SDK's declared inclusive interval response."""

        def __len__(self):
            return length

        def burst_search(self, min_ph, ph_window, time_window):
            assert (min_ph, ph_window, time_window) == (2, 2, 1e-6)
            return np.asarray(pairs, dtype=np.int64).ravel()

    mask = burst_filter(SearchResult(), 2, 2, 1e-6)
    assert mask.dtype == np.dtype(bool)
    assert mask.shape == (length,)
    np.testing.assert_array_equal(np.flatnonzero(mask), selected)
    np.testing.assert_array_equal(np.flatnonzero(~mask), np.setdiff1d(np.arange(length), selected))


def test_generic_interval_helper_remains_half_open():
    """Other utility callers keep the documented exclusive-stop convention."""
    np.testing.assert_array_equal(
        create_array_with_ones(np.array([[1, 3], [4, 4]]), 5),
        [False, True, True, False, False],
    )


def _stream(times):
    """Create an actual native photon stream with one-microsecond ticks."""
    result = tttrlib.TTTR()
    result.append_events(
        np.asarray(times, dtype=np.uint64),
        np.zeros(len(times), np.uint16),
        np.zeros(len(times), np.int8),
        np.zeros(len(times), np.int8),
        False,
        0,
    )
    result.header.set_macro_time_resolution(1e-6)
    return result


@pytest.mark.parametrize(
    "times,pairs", [([0, 1, 2, 100, 200, 201, 202], [[0, 2], [4, 6]]), (list(range(6)), [[0, 5]])]
)
def test_compiled_sdk_search_and_terminal_mask_agree(times, pairs):
    """The native provider itself exposes inclusive counts and terminal stops."""
    stream = _stream(times)
    actual = np.asarray(stream.burst_search(2, 2, 1.5e-6)).reshape(-1, 2)
    np.testing.assert_array_equal(actual, pairs)
    expected = np.zeros(len(stream), dtype=bool)
    for first, last in pairs:
        expected[first : last + 1] = True
    np.testing.assert_array_equal(burst_filter(stream, 2, 2, 1.5e-6), expected)


def test_real_bh_nonburst_mask_excludes_every_native_burst_endpoint():
    """The measured photon complement contains no inclusive burst photon."""
    path = (
        Path(__file__).resolve().parents[2]
        / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/m000.spc"
    )
    stream = tttrlib.TTTR(str(path), "SPC-130")
    options = (60, 10, 1e-3)
    pairs = np.asarray(stream.burst_search(*options), dtype=np.int64).reshape(-1, 2)
    assert pairs.shape == (91, 2)
    expected = np.zeros(len(stream), dtype=bool)
    for first, last in pairs:
        expected[first : last + 1] = True
    before = tuple(
        np.asarray(getattr(stream, field)).copy()
        for field in ("macro_times", "micro_times", "routing_channels")
    )
    mask = burst_filter(stream, *options)
    np.testing.assert_array_equal(mask, expected)
    assert np.count_nonzero(~mask) == 156950
    assert not np.any((~mask)[pairs[:, 1]])
    for field, original in zip(("macro_times", "micro_times", "routing_channels"), before):
        np.testing.assert_array_equal(getattr(stream, field), original)
