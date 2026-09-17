"""Tests for the channel-aware species-filtered correlation core."""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.fcs.filtered import (
    calc_ffcs_filters,
    species_filtered_correlation,
    species_weight_streams,
)


def _patterns(n_bins=64, lifetimes=(1.0, 4.0)):
    t = np.linspace(0, 20, n_bins)
    pats = [np.exp(-t / tau) for tau in lifetimes]
    return [p / p.sum() for p in pats]


def _simulate_photons(n=40000, n_bins=64, seed=0):
    """Photons whose micro-time reflects a per-photon species identity."""
    rng = np.random.default_rng(seed)
    pats = _patterns(n_bins)
    species = rng.integers(0, 2, n)
    micro = np.empty(n, dtype=np.int64)
    for s in (0, 1):
        mask = species == s
        micro[mask] = rng.choice(n_bins, size=int(mask.sum()), p=pats[s])
    total = np.column_stack(pats) @ np.array([0.5, 0.5])
    filters, _, _ = calc_ffcs_filters(total, pats)
    return species, micro, filters, rng


def test_weight_streams_separate_species():
    """Filter s applied to the photons gives mean weight ~1 on species s, ~0 elsewhere."""
    species, micro, filters, _ = _simulate_photons()
    streams = species_weight_streams(filters, micro)
    for s in (0, 1):
        on = streams[s][species == s].mean()
        off = streams[s][species != s].mean()
        assert abs(on - 1.0) < 0.05, (s, on)
        assert abs(off - 0.0) < 0.05, (s, off)


def test_channel_aware_equals_single_axis_when_filters_shared():
    """Identical per-channel filters reproduce the channel-agnostic weights exactly."""
    species, micro, filters, rng = _simulate_photons()
    routing = rng.integers(0, 3, micro.size)  # 3 detectors, same filter each
    single = species_weight_streams(filters, micro)
    per_channel = species_weight_streams({0: filters, 1: filters, 2: filters}, micro, routing)
    for a, b in zip(single, per_channel):
        assert np.allclose(a, b)


def test_channel_aware_zero_filter_channel_drops_photons():
    """A channel with a zeroed filter contributes zero weight for its photons."""
    species, micro, filters, rng = _simulate_photons()
    routing = rng.integers(0, 2, micro.size)
    dead = np.zeros_like(filters)
    streams = species_weight_streams({0: filters, 1: dead}, micro, routing)
    for s in (0, 1):
        assert np.all(streams[s][routing == 1] == 0.0)
        assert np.any(streams[s][routing == 0] != 0.0)


def test_species_filtered_correlation_runs():
    """The full species auto/cross correlation returns finite, well-shaped curves."""
    species, micro, filters, rng = _simulate_photons(n=20000)
    # Ascending macro-times (Poisson arrivals).
    intervals = rng.integers(1, 50, micro.size).astype(np.uint64)
    macro = np.cumsum(intervals)
    result = species_filtered_correlation(
        macro, micro, filters, macro_time_resolution_s=1e-8, n_bins=8, n_casc=18
    )
    assert set(result.auto) == {0, 1}
    assert set(result.cross) == {(0, 1)}
    assert result.lag_s.size == result.auto[0].size
    assert np.all(np.isfinite(result.auto[0]))
    assert np.all(np.isfinite(result.cross[(0, 1)]))
    assert len(result.labels) == 2


def test_channel_aware_correlation_matches_single_axis():
    """Correlation with shared per-channel filters equals the single-axis result."""
    species, micro, filters, rng = _simulate_photons(n=15000)
    routing = rng.integers(0, 2, micro.size)
    intervals = rng.integers(1, 50, micro.size).astype(np.uint64)
    macro = np.cumsum(intervals)
    single = species_filtered_correlation(macro, micro, filters, 1e-8, n_bins=8, n_casc=16)
    per_ch = species_filtered_correlation(
        macro, micro, {0: filters, 1: filters}, 1e-8, routing_channels=routing, n_bins=8, n_casc=16
    )
    assert np.allclose(single.auto[0], per_ch.auto[0], rtol=1e-6, atol=1e-9)
    assert np.allclose(single.cross[(0, 1)], per_ch.cross[(0, 1)], rtol=1e-6, atol=1e-9)


def test_the_packed_matrix_lands_on_the_right_species_pairs():
    """The single-pass matrix, unpacked, equals the per-pair correlator loop.

    `species_filtered_correlation` translates tttrlib's packed
    upper-triangular row layout into `auto`/`cross` dicts in exactly one
    place — the index formula `i*n - i*(i-1)//2 + (j-i)`. A transposition
    or off-by-one there yields finite, well-shaped curves assigned to the
    *wrong* species pair, which no shape or finiteness test can see. So the
    reference is the loop the single pass replaced (transcribed from the
    pre-batching implementation): one plain `tttrlib.Correlator` per pair,
    with three deliberately distinguishable species so every misassignment
    moves a number.
    """
    import tttrlib

    rng = np.random.default_rng(3)
    n = 30000
    macro = np.cumsum(rng.integers(1, 40, n)).astype(np.uint64)
    micro = rng.integers(0, 64, n).astype(np.int64)
    # Three species filters over 64 micro-time bins with distinct shapes,
    # so every misassigned row moves a number.
    bins = np.arange(64, dtype=float)
    f = np.vstack(
        [
            np.exp(-bins / 8.0),
            np.exp(-(((bins - 30.0) / 10.0) ** 2)),
            0.02 + 0.015 * bins / 63.0,
        ]
    )
    streams = species_weight_streams(f, micro, None)
    assert len(streams) == 3

    single = species_filtered_correlation(macro, micro, f, 1e-8, n_bins=8, n_casc=12, method="wahl")

    def _pair(wa, wb):
        c = tttrlib.Correlator()
        c.n_bins = 8
        c.n_casc = 12
        c.set_macrotimes(macro, macro)
        c.set_weights(np.ascontiguousarray(wa), np.ascontiguousarray(wb))
        c.run()
        return np.asarray(c.get_corr_normalized(), dtype=float)

    for i in range(3):
        np.testing.assert_allclose(
            single.auto[i],
            _pair(streams[i], streams[i]),
            rtol=1e-10,
            err_msg=f"auto[{i}] landed on the wrong row",
        )
    for i in range(3):
        for j in range(i + 1, 3):
            np.testing.assert_allclose(
                single.cross[(i, j)],
                _pair(streams[i], streams[j]),
                rtol=1e-10,
                err_msg=f"cross[({i},{j})] landed on the wrong row",
            )
