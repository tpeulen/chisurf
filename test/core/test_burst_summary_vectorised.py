"""The burst summary is computed for all bursts at once; it must equal the per-burst definition."""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.datastore import column_names
from chisurf.core.fio.fluorescence.burst import DETECTOR_SENTINEL, generate_burst_dataframe


class _Header:
    macro_time_resolution = 1e-8
    micro_time_resolution = 4e-11
    number_of_micro_time_channels = 4096


class _Tttr:
    def __init__(self, n, seed=3):
        rng = np.random.default_rng(seed)
        self.macro_times = np.cumsum(rng.integers(1, 400, n)).astype(np.uint64)
        self.micro_times = rng.integers(0, 4096, n).astype(np.uint16)
        self.routing_channel = rng.integers(0, 4, n).astype(np.int8)
        self.header = _Header()

    def __len__(self):
        return self.macro_times.size


def _reference(t, start, stop, chs, gate):
    """One burst's span quantities, straight from the definition."""
    sl = np.arange(start, stop + 1)
    keep = np.isin(t.routing_channel[sl], chs)
    if gate is not None:
        keep &= (t.micro_times[sl] >= gate[0]) & (t.micro_times[sl] < gate[1])
    idx = sl[keep]
    if idx.size == 0:
        return {"n": 0, "first": -1, "last": -1}
    return {"n": idx.size, "first": int(idx[0]), "last": int(idx[-1]),
            "mean_micro": float(np.mean(t.micro_times[idx]))}


@pytest.mark.parametrize("interleaved", [True, False])
def test_every_burst_equals_its_per_burst_definition(interleaved):
    t = _Tttr(20000)
    bursts = [(i, i + int(5 + i % 37)) for i in range(0, 19800, 157)]
    bursts += [(7, 7), (30, 2), (19998, 20010)]  # skipped: empty, reversed, past the end
    detectors = {"green": {"chs": [0, 1], "micro_time_ranges": [[0, 2048]]},
                 "red": {"chs": [3], "micro_time_ranges": []}}
    store = generate_burst_dataframe(bursts, "m.ptu", t, {}, detectors,
                                     include_interleaved_zeros=interleaved)
    names = column_names(store)
    kept = [(a, b) for a, b in bursts if a < b < len(t) and a >= 0]
    rows = np.arange(1, 2 * len(kept), 2) if interleaved else np.arange(len(kept))
    n_col = next(c for c in names if "Number of Photons" in c and "green" in c.lower())
    first_col = next(c for c in names if "First Photon" in c and "green" in c.lower())
    got_n = np.asarray(store[n_col])[rows]
    got_first = np.asarray(store[first_col])[rows]
    for k, (a, b) in enumerate(kept):
        ref = _reference(t, a, b, [0, 1], (0, 2048))
        assert got_n[k] == ref["n"] and got_first[k] == ref["first"]
    if interleaved:
        assert np.all(np.asarray(store[n_col])[0::2] == 0)


def test_no_bursts_gives_the_declared_columns_and_no_rows():
    t = _Tttr(100)
    store = generate_burst_dataframe([], "m.ptu", t, {}, {"green": {"chs": [0], "micro_time_ranges": []}})
    assert column_names(store) and all(len(np.asarray(store[c])) == 0 for c in column_names(store))
    assert DETECTOR_SENTINEL is not None
