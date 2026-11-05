"""The correlator walks only the selected photons and gives the curve of the weighted stream.

``correlate_masked`` replaced weighting every photon of a stream by its channel mask (two
full-length float arrays, and the correlator walking photons of weight 0). These tests hold it to
that reference bit for bit -- lags and correlation -- including streams whose first and last
photon belong to neither channel (their span is the normalisation's time).
"""

import numpy as np
import pytest


def _weighted_reference(times, mask_a, mask_b, n_bins, n_casc):
    """The old way: every photon, weighted by its mask."""
    import tttrlib

    correlator = tttrlib.Correlator(n_bins=n_bins, n_casc=n_casc, make_fine=False)
    correlator.set_macrotimes(times, times)
    correlator.set_weights(np.asarray(mask_a, dtype=np.float64), np.asarray(mask_b, dtype=np.float64))
    return np.asarray(correlator.x_axis), np.asarray(correlator.correlation, dtype=float)


def _stream(seed, n=60_000, channels=4):
    rng = np.random.default_rng(seed)
    times = np.cumsum(rng.geometric(0.002, size=n)).astype(np.uint64)
    routing = rng.integers(0, channels, size=n).astype(np.int8)
    micro = rng.integers(0, 4096, size=n).astype(np.uint16)
    return times, routing, micro


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("ends_selected", [False, True])
def test_masked_equals_weighted(seed, ends_selected):
    from chisurf.plugins.burst.burst_fcs_correlator.core.algorithms import correlate_masked

    times, routing, micro = _stream(seed)
    if not ends_selected:  # first and last photon in neither channel
        routing[0] = routing[-1] = 3
    mask_a = (routing == 0) & (micro >= 100) & (micro < 3000)
    mask_b = routing == 1
    lags, g = correlate_masked(times, mask_a, mask_b, 8, 22)
    ref_lags, ref_g = _weighted_reference(times, mask_a, mask_b, 8, 22)
    np.testing.assert_array_equal(lags, ref_lags)
    np.testing.assert_array_equal(g, ref_g)


def test_autocorrelation_equals_weighted():
    from chisurf.plugins.burst.burst_fcs_correlator.core.algorithms import correlate_masked

    times, routing, _micro = _stream(7)
    mask = routing == 2
    lags, g = correlate_masked(times, mask, mask, 8, 22)
    ref_lags, ref_g = _weighted_reference(times, mask, mask, 8, 22)
    np.testing.assert_array_equal(lags, ref_lags)
    np.testing.assert_array_equal(g, ref_g)


def test_an_empty_channel_gives_none():
    from chisurf.plugins.burst.burst_fcs_correlator.core.algorithms import correlate_masked

    times, routing, _micro = _stream(3, n=5000)
    assert correlate_masked(times, routing == 9, routing == 0, 8, 22) == (None, None)


def test_single_burst_coarse_equals_weighted():
    """``correlate_single_burst`` (coarse) goes through ``correlate_masked``: the same curve."""
    import tttrlib

    from chisurf.plugins.burst.burst_fcs_correlator.core import correlate_single_burst

    times, routing, micro = _stream(5)
    events = np.zeros(times.size, dtype=np.int8)
    tttr = tttrlib.TTTR(times, micro, routing, events)
    gates = [[100, 3000]]
    tau, g = correlate_single_burst(tttr, [0], [1], gates, gates, 8, 22, False)
    in_gate = (micro >= 100) & (micro < 3000)
    ref_lags, ref_g = _weighted_reference(
        times, (routing == 0) & in_gate, (routing == 1) & in_gate, 8, 22
    )
    np.testing.assert_array_equal(g, ref_g)
    np.testing.assert_array_equal(tau, np.asarray(ref_lags * tttr.header.macro_time_resolution * 1000.0, dtype=float))
