"""The photon columns as read-only views: the getters' values, no copy, safe to hold."""

import gc

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fio.photon_views import COLUMNS, photon_column  # noqa: E402


def _stream(n=50_000, seed=0):
    rng = np.random.default_rng(seed)
    macro = np.cumsum(rng.integers(1, 50, n)).astype(np.uint64)
    micro = rng.integers(0, 4096, n).astype(np.uint16)
    routing = rng.integers(0, 4, n).astype(np.int8)
    events = np.zeros(n, dtype=np.int8)
    return tttrlib.TTTR(macro, micro, routing, events)


@pytest.mark.parametrize("name", sorted(COLUMNS))
def test_view_equals_the_getter_and_is_read_only(name):
    tttr = _stream()
    view = photon_column(tttr, name)
    copy = np.asarray(getattr(tttr, name))
    assert view.dtype == copy.dtype
    np.testing.assert_array_equal(view, copy)
    assert not view.flags.writeable
    with pytest.raises(ValueError):
        view[0] = 1
    np.testing.assert_array_equal(np.asarray(getattr(tttr, name)), copy)  # the stream unchanged


def test_the_view_outlives_the_name_of_its_stream():
    tttr = _stream(seed=3)
    expected = np.asarray(tttr.macro_times).copy()
    view = photon_column(tttr, "macro_times")
    del tttr
    gc.collect()
    _other = [_stream(seed=s) for s in range(3)]  # reuse the freed memory, if it was freed
    np.testing.assert_array_equal(view, expected)


def test_a_slice_and_a_stand_in():
    tttr = _stream(seed=5)[100:900]
    np.testing.assert_array_equal(photon_column(tttr, "micro_times"), tttr.micro_times)

    class StandIn:
        macro_times = np.arange(5, dtype=np.uint64)
        routing_channel = np.zeros(5, dtype=np.int8)  # tttrlib's other spelling

    np.testing.assert_array_equal(photon_column(StandIn(), "routing_channels"), np.zeros(5))
    with pytest.raises(ValueError):
        photon_column(StandIn(), "nonsense")


def test_shifted_or_compressed_macro_times_come_from_the_getter():
    tttr = _stream(seed=7)
    if hasattr(tttr, "macro_time_offset"):
        tttr.macro_time_offset = 10
        np.testing.assert_array_equal(photon_column(tttr, "macro_times"), tttr.macro_times)
        tttr.macro_time_offset = 0
    if hasattr(tttr, "enable_macro_time_compression"):
        tttr.enable_macro_time_compression()
        np.testing.assert_array_equal(photon_column(tttr, "macro_times"), tttr.macro_times)
