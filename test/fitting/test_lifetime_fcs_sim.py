"""End-to-end lifetime-FCS (FLCS) simulation → filter → correlation tests.

Closes the loop for :mod:`chisurf.core.fluorescence.fcs.simulate`: simulate
diffusing species with distinct lifetimes (and optional interconversion), build
lifetime filters, and check that the species-filtered correlations recover the
expected physics — separated diffusion times for static species and an exchange
peak in the cross-correlation for interconverting states.

Requires ``tttrlib`` with the ``SimEngine`` simulator (a chisurf dependency).
"""

from __future__ import annotations

import numpy as np
import pytest

_tttrlib = pytest.importorskip("tttrlib")
if not hasattr(_tttrlib, "SimEngine"):
    pytest.skip("tttrlib build lacks SimEngine", allow_module_level=True)

from chisurf.core.fluorescence.fcs.filtered import (  # noqa: E402
    calc_ffcs_filters,
    filter_condition_number,
    species_filtered_correlation,
)
from chisurf.core.fluorescence.fcs.simulate import simulate_lifetime_fcs  # noqa: E402

N_PHOTONS = 250_000


def _amp(g, lag, t_s):
    return float(g[np.argmin(np.abs(lag - t_s))])


def test_simulate_returns_labelled_stream():
    sim = simulate_lifetime_fcs((1.0, 4.0), (8.0, 0.5), n_photons=N_PHOTONS, seed=1)
    assert sim.macro_times.dtype == np.uint64
    assert np.all(np.diff(sim.macro_times) >= 0)  # ascending for the correlator
    assert sim.macro_times.size == sim.micro_times.size == sim.species.size
    # both real species emit; micro-times lie on the configured TAC axis
    assert {0, 1}.issubset(set(np.unique(sim.species)))
    assert sim.micro_times.max() < sim.n_microtime_channels
    assert len(sim.reference_decays) == 2
    assert sim.total_decay.sum() > 0


def test_filters_well_conditioned():
    sim = simulate_lifetime_fcs((1.0, 4.0), (8.0, 0.5), n_photons=N_PHOTONS, seed=1)
    cond = filter_condition_number(sim.total_decay, sim.reference_decays)
    assert cond < 20.0, cond  # separated 1 ns / 4 ns decays give a low condition number
    filters, _, _ = calc_ffcs_filters(sim.total_decay, sim.reference_decays)
    assert filters.shape == (2, sim.n_microtime_channels)


def test_static_species_separate_by_diffusion_time():
    # Fast/short-lifetime + slow/long-lifetime species diffusing independently.
    sim = simulate_lifetime_fcs((1.0, 4.0), (8.0, 0.5), n_photons=N_PHOTONS, seed=1)
    filters, _, _ = calc_ffcs_filters(sim.total_decay, sim.reference_decays)
    res = species_filtered_correlation(
        sim.macro_times, sim.micro_times, filters, sim.macro_time_resolution_s,
        n_bins=8, n_casc=22, labels=["fast", "slow"],
    )
    lag, g_fast, g_slow, g_cross = res.lag_s, res.auto[0], res.auto[1], res.cross[(0, 1)]

    # At 100 us the slow species is still strongly correlated, the fast one much less.
    assert _amp(g_slow, lag, 1e-4) > _amp(g_fast, lag, 1e-4) + 1.0
    # By 500 us the fast species has decayed to (near) baseline; the slow one has not.
    assert _amp(g_fast, lag, 5e-4) < 1.5
    assert _amp(g_slow, lag, 5e-4) > 1.5
    # Static species are independent: the cross-correlation stays far below the
    # slow-species autocorrelation amplitude over the mid-lag band.
    band = (lag > 1e-5) & (lag < 1e-3)
    assert np.nanmax(g_cross[band]) < 0.5 * np.nanmax(g_slow[band])


def test_interconversion_shows_cross_correlation_peak():
    # Two states, identical diffusion, exchanging while they cross the focus.
    sim = simulate_lifetime_fcs(
        (1.0, 4.0), (0.15, 0.15), exchange_rate_ms=5.0, n_photons=N_PHOTONS, seed=2,
    )
    filters, _, _ = calc_ffcs_filters(sim.total_decay, sim.reference_decays)
    res = species_filtered_correlation(
        sim.macro_times, sim.micro_times, filters, sim.macro_time_resolution_s,
        n_bins=8, n_casc=22,
    )
    lag, g_cross = res.lag_s, res.cross[(0, 1)]
    band = (lag > 2e-5) & (lag < 1e-3)
    peak = float(np.nanmax(g_cross[band]))
    short = _amp(g_cross, lag, 2e-6)
    # The exchange builds a clear positive cross-correlation peak that rises well
    # above the short-lag value — the kinetic fingerprint of interconversion.
    assert peak > 2.5, peak
    assert peak > 1.8 * short, (peak, short)
