"""A photon file whose two detectors are offset by a known number of micro-time bins.

``build(root)`` writes ``<root>/offset.spc`` (SPC-130 layout: 12.5 ns macro ticks, 4096
micro-time bins over the same 12.5 ns): routing channel 0 holds a sharp IRF-like peak with a
0.3 ns decay starting at bin ``RISE[0]``, channel 8 the same shape starting at ``RISE[8]``, both
on a flat background. Auto-align with the target bin at ``TARGET`` and a trigger level well
above the background should shift channel c by ``(TARGET - RISE[c]) % N_MT``.
"""

from __future__ import annotations

import pathlib

import numpy as np

TICK = 12.5e-9
N_MT = 4096
RISE = {0: 600, 8: 1000}
TARGET = 409            # the tool's default target bin: 10 % of the bins
N_PEAK = 60_000
N_FLAT = 20_000


def build(root: pathlib.Path, seed: int = 7) -> pathlib.Path:
    """Write the measurement under *root*; return its path."""
    import tttrlib

    rng = np.random.default_rng(seed)
    bin_ns = TICK * 1e9 / N_MT
    times, channels, micro = [], [], []
    for channel, rise in RISE.items():
        peak = rise + np.abs(rng.normal(0.0, 3.0, N_PEAK)) + rng.exponential(0.3 / bin_ns, N_PEAK)
        flat = rng.uniform(0, N_MT, N_FLAT)
        bins = np.concatenate([peak, flat]).astype(int) % N_MT
        micro.append(bins)
        channels.append(np.full(len(bins), channel))
        times.append(rng.uniform(0.0, 5.0, len(bins)))
    t = np.concatenate(times)
    order = np.argsort(t, kind="stable")
    ticks = np.round(t[order] / TICK).astype(np.uint64)
    keep = np.concatenate([[True], np.diff(ticks) > 0])
    data = tttrlib.TTTR()
    data.append_events(ticks[keep], np.concatenate(micro)[order][keep].astype(np.uint16),
                       np.concatenate(channels)[order][keep].astype(np.int8),
                       np.zeros(int(keep.sum()), np.int8), False, 0)
    data.header.set_macro_time_resolution(TICK)
    data.header.set_micro_time_resolution(TICK / N_MT)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "offset.spc"
    data.write(str(path))
    return path
