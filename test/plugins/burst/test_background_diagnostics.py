"""Tests for the background-estimation diagnostics (inter-photon-time fit)."""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.burst import background as bg


def _dt_ms(rng, bg_rate_khz=2.0, n_bg=20000, n_burst=5000):
    """Inter-photon times (ms): Poisson background + short burst gaps."""
    dark = rng.exponential(1.0 / bg_rate_khz, n_bg)
    burst = rng.exponential(1.0 / 200.0, n_burst)
    return np.concatenate([dark, burst])


def test_diagnostics_rate_matches_estimator():
    rng = np.random.default_rng(0)
    dt = _dt_ms(rng)
    rate = bg.estimate_background_from_interphoton_times(dt, tail_fraction=0.2)
    diag = bg.interphoton_time_diagnostics(dt, tail_fraction=0.2)
    assert abs(diag.rate_khz - rate) < 1e-9        # same fit, no drift
    assert diag.centers.size == diag.counts.size == diag.model.size
    assert diag.tail_mask.sum() > 0
    assert np.all(diag.model >= 0)


def test_recovers_known_background_rate():
    rng = np.random.default_rng(1)
    dt = _dt_ms(rng, bg_rate_khz=3.0)
    diag = bg.interphoton_time_diagnostics(dt, tail_fraction=0.2)
    assert abs(diag.rate_khz - 3.0) / 3.0 < 0.25   # within 25% of the true rate


def test_tail_fit_does_not_fail_on_its_own_bounds():
    """The optimiser must never see ``inf - inf`` while probing its bounds.

    ``L-BFGS-B`` evaluates the objective *on* its bounds when building the
    finite-difference gradient, and the negative log-likelihood is ``+inf`` at zero
    amplitude or zero rate. With the bounds closed at zero that produced a NaN
    gradient, an early stop reported as failure, and a silent fall back to the
    inverse mean tail interval — a different and biased estimator arriving with no
    error at all. On a real single-molecule measurement it moved the background rate
    by ~20%.
    """
    import warnings

    rng = np.random.default_rng(7)
    dt = _dt_ms(rng, bg_rate_khz=2.0)
    hist = bg._histogram_interphoton(dt, 0.1)
    assert hist is not None
    centers, counts, max_dt = hist

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        amplitude, rate, _, success = bg._fit_exponential_tail(
            centers, counts, max_dt, 0.2, 1
        )
    assert not [w for w in caught if "invalid value" in str(w.message)]
    assert success, "the tail fit fell back to the biased estimator"
    assert amplitude > 0.0 and rate > 0.0
    assert abs(rate - 2.0) / 2.0 < 0.25


def test_empty_input_is_graceful():
    diag = bg.interphoton_time_diagnostics(np.empty(0))
    assert diag.rate_khz == 0.0 and diag.centers.size == 0


def test_diagnostics_from_bursts_per_detector():
    import tttrlib

    rng = np.random.default_rng(2)
    n = 60000
    macro = np.sort(rng.integers(0, 10_000_000, n)).astype(np.uint64)
    route = rng.integers(0, 2, n).astype(np.int8)
    d = tttrlib.TTTR()
    d.append_events(macro, np.zeros(n, np.uint16), route, np.zeros(n, np.int8), False, 0)
    d.header.set_macro_time_resolution(1e-7)       # 100 ns/tick

    detectors = {"green": {"chs": [0]}, "red": {"chs": [1]}}
    diags = bg.background_diagnostics_from_bursts(d, detectors)
    assert set(diags) == {"green", "red"}
    for name, diag in diags.items():
        assert isinstance(diag, bg.BackgroundDiagnostics)
        assert diag.centers.size > 0
