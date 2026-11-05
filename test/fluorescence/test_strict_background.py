"""Background photons are a strict selection, not the photons outside the bursts.

Simulated: a flat + scatter background (the buffer), dim molecules below the burst threshold and
bright bursts. The photons outside the bursts hold the dim molecules and the bursts' flanks, so
their histogram is a decay; the strict selection (burst margins, local count rate at the
background's level) gives the buffer's shape and rate.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from chisurf.core.fluorescence.burst.irf_bg import flat_scatter_background, strict_background_mask

N_BINS, DT_NS, RES_S = 250, 0.08, 1e-7


def _irf() -> np.ndarray:
    g = np.exp(-0.5 * ((np.arange(N_BINS) - 40) / 3.0) ** 2)
    return g / g.sum()


def _micro(rng, n, kind):
    irf = _irf()
    if kind == "buffer":  # 80 % flat dark counts / afterpulsing, 20 % scatter
        flat = rng.random(n) < 0.8
        out = np.where(flat, rng.integers(0, N_BINS, n), rng.choice(N_BINS, n, p=irf))
        return out
    prompt = rng.choice(N_BINS, n, p=irf)
    return np.mod(prompt + np.round(rng.exponential(4.0 / DT_NS, n)).astype(int), N_BINS)  # periodic


def _simulate(seed=1, seconds=300.0, bg_khz=1.0, dim_hz=40.0, bright_hz=1.0):
    """Photon times [s], micro-time bins and the bright bursts' photons."""
    rng = np.random.default_rng(seed)
    t_bg = np.sort(rng.random(rng.poisson(bg_khz * 1e3 * seconds)) * seconds)
    parts, kinds, bursts = [t_bg], [np.zeros(t_bg.size, int)], []

    def molecules(rate_hz, khz, duration_s, kind):
        for start in rng.random(rng.poisson(rate_hz * seconds)) * seconds:
            # a Gaussian brightness profile: the flanks are slow, the centre fast
            n = rng.poisson(khz * 1e3 * duration_s * 2.5)
            times = start + rng.normal(0.0, duration_s / 2.0, n)
            times = times[(times > 0) & (times < seconds)]
            parts.append(times)
            kinds.append(np.full(times.size, kind))
            if kind == 2:
                bursts.append((start - duration_s / 2, start + duration_s / 2))

    molecules(dim_hz, 6.0, 1e-3, 1)  # dim: below the burst threshold
    molecules(bright_hz, 80.0, 1e-3, 2)  # bright: the bursts
    t = np.concatenate(parts)
    kind = np.concatenate(kinds)
    order = np.argsort(t, kind="stable")
    t, kind = t[order], kind[order]
    micro = np.empty(t.size, int)
    micro[kind == 0] = _micro(rng, int(np.sum(kind == 0)), "buffer")
    micro[kind > 0] = _micro(rng, int(np.sum(kind > 0)), "molecule")
    in_burst = np.zeros(t.size, bool)
    for lo, hi in bursts:  # what a burst search finds: the bright core
        in_burst[np.searchsorted(t, lo) : np.searchsorted(t, hi)] = True
    tttr = SimpleNamespace(
        macro_times=np.round(t / RES_S).astype(np.int64),
        routing_channel=np.zeros(t.size, dtype=np.int16),
        header=SimpleNamespace(macro_time_resolution=RES_S),
    )
    return tttr, micro, in_burst, kind, seconds


def _fluorescence_share(micro):
    hist = np.bincount(micro, minlength=N_BINS).astype(float)
    counts = np.hstack([hist, hist])
    _, parts = flat_scatter_background(counts, np.hstack([_irf(), _irf()]), DT_NS, (0, N_BINS))
    return parts["fluorescence"][0] / hist.sum()


def test_the_strict_selection_is_the_buffer_where_the_inverted_burst_selection_is_not():
    tttr, micro, in_burst, kind, seconds = _simulate()
    plain = ~in_burst
    strict = strict_background_mask(tttr, in_burst)
    # the photons outside the bursts: the dim molecules and the flanks, a decay
    assert _fluorescence_share(micro[plain]) > 0.3
    plain_khz = plain.sum() / (seconds * (1 - 0.003)) / 1e3
    assert plain_khz > 1.4  # well above the 1 kHz background
    # the strict selection: the buffer's shape and rate
    assert not strict.warning
    assert 0.3 < strict.fraction < 0.98
    assert _fluorescence_share(micro[strict.mask]) < 0.1
    assert np.mean(kind[strict.mask] == 0) > 0.95
    assert strict.rate_khz == pytest.approx(1.0, rel=0.1)


def test_too_little_background_time_is_said():
    """A sample whose molecules never leave the focus has no stretch at the background level."""
    tttr, *_ = _simulate(dim_hz=2000.0, seconds=30.0)
    strict = strict_background_mask(tttr, np.zeros(tttr.macro_times.size, bool), rate_khz=1.0, iterations=1)
    assert strict.warning and strict.fraction < 0.05


def test_interval_lookup_and_window_merge_match_the_plain_versions():
    """The photon-side interval lookup and the one-pass window merge (what made the strict
    selection of a 300 MB measurement take seconds per threshold) give the plain answers."""
    from chisurf.core.fluorescence.burst import irf_bg

    rng = np.random.default_rng(7)
    t = np.sort(rng.uniform(0, 100, 20000))
    t[100:110] = t[100]  # equal times
    lo = np.sort(rng.uniform(-5, 105, 300))
    lo, hi = irf_bg._merged(lo, lo + rng.uniform(0, 0.5, lo.size))
    assert np.array_equal(irf_bg._inside(t, lo, hi), irf_bg._inside(t, lo, hi, t_sorted=False))
    exact = np.r_[t[0], t[5000]]
    assert np.array_equal(irf_bg._inside(t, exact, exact), irf_bg._inside(t, exact, exact, t_sorted=False))
    for m in (2, 10):
        k = np.flatnonzero(rng.random(t.size - m + 1) < 0.3)
        a = irf_bg._merged_windows(t[k], t[k + m - 1])
        b = irf_bg._merged(t[k], t[k + m - 1])
        assert all(np.array_equal(x, y) for x, y in zip(a, b))
