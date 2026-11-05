"""Guard: the CUSUM/SPRT search keeps a transit whole, and the trace shows it whole.

The owner read the zoomed count-rate trace of DNA13bp_3 (CUSUM, L=5, S/B 3.317, >= 30 photons)
as "bursts seem split". Measured, the bursts were not split -- 0 % of the gaps between consecutive
bursts were shorter than one background inter-photon time -- and the picture came from the plot:
the window's 1 ms trace was thinned once to 4000 points (min and max of every 30 ms) and the zoom
showed those, so each burst was a spike from zero. Record: okf/plugins/burst-selection.md.
"""

from __future__ import annotations

import numpy as np
import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.core.fluorescence.burst import tttrlib_search  # noqa: E402
from chisurf.plugins.burst.burst_selection.api.selection import (  # noqa: E402
    drop_short_bursts,
    find_bursts,
)
from chisurf.core.fluorescence.burst.utils import create_array_with_ones  # noqa: E402

RES = 25e-9  # s per macro-time tick
BACKGROUND_CPS = 3300.0
DURATION_S = 20.0
N_TRANSITS = 200


def _transit_stream(seed: int = 3):
    """Poisson background plus Gaussian-profile transits (peak 40 kcps, sigma 1 ms) 100 ms apart."""
    rng = np.random.default_rng(seed)
    times = [rng.uniform(0.0, DURATION_S, rng.poisson(BACKGROUND_CPS * DURATION_S))]
    centres = (np.arange(N_TRANSITS) + 0.5) * (DURATION_S / N_TRANSITS)
    sigma, peak = 1e-3, 40e3
    for c in centres:
        n = rng.poisson(peak * sigma * np.sqrt(2 * np.pi))
        times.append(c + rng.normal(0.0, sigma, n))
    t = np.sort(np.concatenate(times))
    t = t[(t > 0) & (t < DURATION_S)]
    ticks = np.round(t / RES).astype(np.uint64)
    n = ticks.size
    tttr = tttrlib.TTTR(ticks, np.zeros(n, dtype=np.uint16), np.zeros(n, dtype=np.int8),
                        np.zeros(n, dtype=np.int8))
    tttr.header.set_macro_time_resolution(RES)
    return tttr, centres


def _owner_bursts(tttr):
    raw = np.asarray(
        tttrlib_search.search(
            tttr,
            "cusum_sprt",
            dict(min_photons=5, background_cps=BACKGROUND_CPS, signal_to_background_ratio=3.317,
                 alpha=0.05, beta=0.05),
        ),
        dtype=np.int64,
    ).reshape(-1, 2)
    ss = raw.copy()
    ss[:, 1] += 1
    mask = np.asarray(create_array_with_ones(ss, len(tttr)), dtype=bool)
    final = np.asarray(find_bursts(mask, max_gap=3), dtype=np.int64).reshape(-1, 2)
    return raw, drop_short_bursts(final, 30)


def test_cusum_does_not_split_a_transit():
    tttr, centres = _transit_stream()
    raw, final = _owner_bursts(tttr)
    t = np.asarray(tttr.macro_times, dtype=np.int64) * RES
    gaps = t[raw[1:, 0]] - t[raw[:-1, 1]]
    # splitting shows as a pile-up of gaps shorter than a few background inter-photon times
    assert np.mean(gaps < 3.0 / BACKGROUND_CPS) < 0.02
    # one final burst per transit, and no transit holding two
    hit = np.searchsorted(centres, (t[final[:, 0]] + t[final[:, 1]]) / 2.0)
    near = np.abs(centres[np.clip(hit, 0, N_TRANSITS - 1)] - (t[final[:, 0]] + t[final[:, 1]]) / 2.0)
    near = np.minimum(near, np.abs(centres[np.clip(hit - 1, 0, N_TRANSITS - 1)]
                                   - (t[final[:, 0]] + t[final[:, 1]]) / 2.0))
    on_transit = near < 5e-3
    assert on_transit.sum() >= 0.95 * N_TRANSITS
    owners = np.argmin(np.abs(centres[None, :] - ((t[final[:, 0]] + t[final[:, 1]]) / 2.0)[:, None]), axis=1)
    assert np.bincount(owners[on_transit], minlength=N_TRANSITS).max() == 1


def test_trace_is_drawn_from_full_bins_and_burst_photons(monkeypatch, tmp_path):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "s"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "m"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "m.sqlite"))
    (tmp_path / "s").mkdir()
    (tmp_path / "m").mkdir()
    from chisurf.plugins.burst.burst_selection.gui.model import TRACE_PLOT_POINTS, BurstSelectionModel

    tttr, _ = _transit_stream()
    raw, final = _owner_bursts(tttr)
    selected = np.zeros(len(tttr), dtype=bool)
    for s, e in raw:  # the raw search mask, sub-30-photon fragments included
        selected[s:e + 1] = True
    m = BurstSelectionModel()
    m.diagnostic = {"tttr": tttr, "selected": selected, "start_stop": final}
    monkeypatch.setattr(m, "_window_indices", lambda: (0, len(tttr)))
    m.trace_bin_ms = 1.0
    m.show_all_photons = m.show_selected_photons = True

    full = m.trace_curves()
    assert full["all"][0].size > TRACE_PLOT_POINTS  # 20 s of 1 ms bins: kept, not thinned
    # "selected" counts exactly the photons of the table's bursts, not the raw mask
    n_burst_photons = int((final[:, 1] - final[:, 0] + 1).sum())
    assert full["selected"][1].sum() * 1e-3 == pytest.approx(n_burst_photons)
    assert n_burst_photons < selected.sum()

    # zoomed to 2.6 s, every bin is drawn as it is -- no min/max blocks that put zeros in a burst
    zoom = m.visible_trace_curves(10.0, 12.6)
    t, r = zoom["all"]
    assert t.size <= TRACE_PLOT_POINTS and np.all(np.diff(t) > 0)
    np.testing.assert_allclose(np.diff(t), 1e-3, rtol=1e-6)
    starts, stops = m.burst_spans()
    assert starts.size == len(final) and np.all(stops >= starts)
