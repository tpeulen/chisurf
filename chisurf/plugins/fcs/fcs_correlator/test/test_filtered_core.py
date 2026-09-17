"""Headless tests for the lifetime-filtered correlation entrypoint (Qt-free)."""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.fcs.filtered import calc_ffcs_filters
from chisurf.plugins.fcs.fcs_correlator.core import filtered_correlation_datasets


def _setup(n=15000, n_bins=64, seed=1):
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 20, n_bins)
    pats = [p / p.sum() for p in (np.exp(-t / 1.0), np.exp(-t / 4.0))]
    species = rng.integers(0, 2, n)
    micro = np.empty(n, dtype=np.int64)
    for s in (0, 1):
        m = species == s
        micro[m] = rng.choice(n_bins, size=int(m.sum()), p=pats[s])
    total = np.column_stack(pats) @ np.array([0.5, 0.5])
    filters, _, _ = calc_ffcs_filters(total, pats)
    macro = np.cumsum(rng.integers(1, 40, n).astype(np.uint64))
    routing = rng.integers(0, 2, n)
    return macro, micro, routing, filters


def test_filtered_datasets_shape_and_names():
    """The entrypoint emits one dataset per species pair (auto first) with names."""
    macro, micro, _, filters = _setup()
    datasets = filtered_correlation_datasets(
        macro, micro, filters, 1e-8, n_bins=8, n_casc=16, labels=["fast", "slow"]
    )
    assert len(datasets) == 3  # 2 auto + 1 cross
    assert [d["species_a"] == d["species_b"] for d in datasets][:2] == [True, True]
    assert datasets[-1]["species_a"] == 0 and datasets[-1]["species_b"] == 1
    for d in datasets:
        assert len(d["x"]) == len(d["y"])
        assert np.all(np.isfinite(d["y"]))
        assert "×" in d["name"]


def test_channel_aware_filter_table_from_mfd():
    """A {channel: filters} table drives channel-aware correlation without error."""
    macro, micro, routing, filters = _setup()
    table = {0: filters, 1: filters}  # e.g. par/perp mapped to the same filters
    datasets = filtered_correlation_datasets(
        macro, micro, table, 1e-8, routing_channels=routing, n_bins=8, n_casc=16
    )
    assert len(datasets) == 3
    assert all(np.all(np.isfinite(d["y"])) for d in datasets)


def test_filter_result_channel_map():
    """FilterResultMFD.to_channel_filters maps par/perp detectors to their filters."""
    from chisurf.plugins.fcs.fcs_filter_calculator.api import FilterResultMFD

    fpar = np.arange(6.0).reshape(2, 3)
    fperp = np.arange(6.0, 12.0).reshape(2, 3)
    res = FilterResultMFD(
        filters_par=fpar,
        filters_perp=fperp,
        reconstruction_par=np.zeros(3),
        reconstruction_perp=np.zeros(3),
        weighted_residuals_par=np.zeros(3),
        weighted_residuals_perp=np.zeros(3),
        total_decay_par=np.ones(3),
        total_decay_perp=np.ones(3),
        species_decays_par=[np.ones(3)],
        species_decays_perp=[np.ones(3)],
        metadata={},
    )
    table = res.to_channel_filters(par_channels=[0, 2], perp_channels=[1, 3])
    assert set(table) == {0, 1, 2, 3}
    assert np.array_equal(table[0], fpar) and np.array_equal(table[3], fperp)
