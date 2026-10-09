"""The shipped demo converts to exactly the bursts its BID file declares."""

import numpy as np

from .. import convert_bid_file
from ..demo import N_BURSTS, burst_windows, make_demo, photon_stream


def test_demo_conversion_recovers_the_declared_bursts(tmp_path):
    """Burst count, photon numbers and durations follow from the simulated windows."""
    from chisurf.core.datastore import numeric_column, row_count
    from chisurf.core.fio.pto import Measurement

    bid = make_demo(tmp_path)
    selection = np.loadtxt(bid, dtype=np.int64)
    convert_bid_file(bid, output_types={"pto"})
    with Measurement.open(bid.with_suffix(".pto")) as measurement:
        bursts = measurement.get_store("bursts")
        assert row_count(bursts) == N_BURSTS
        photons = numeric_column(bursts, "Number of Photons").astype(np.int64)
    np.testing.assert_array_equal(photons, selection[:, 1] - selection[:, 0] + 1)
    t, _, _ = photon_stream()
    for (first, last), (start, end) in zip(selection, burst_windows()):
        assert start <= t[first] and t[last] < end


def test_demo_cache_is_reused_and_rejects_tampering(tmp_path):
    """A cached demo is returned unchanged; a modified BID is regenerated."""
    bid = make_demo(tmp_path)
    original = bid.read_bytes()
    stamp = bid.stat().st_mtime_ns
    assert make_demo(tmp_path) == bid and bid.stat().st_mtime_ns == stamp
    bid.write_text("0 1\n")
    make_demo(tmp_path)
    assert bid.read_bytes() == original
