"""A photon measurement with a known background, for the tool's tests and captures.

``<root>/m000.spc`` (SPC-130, 12.5 ns ticks): Poisson background of 2 kHz on the green
routing channel 0 and 1 kHz on the red channel 1 for 20 s, plus 200 bursts of 1 ms at
100 kHz split 60 : 40 green : red. A background estimate should return the two rates.
"""

from __future__ import annotations

import pathlib

import numpy as np

TICK = 12.5e-9
DURATION_S = 20.0
BACKGROUND_KHZ = {"green": 2.0, "red": 1.0}


def build(root: pathlib.Path, seed: int = 5) -> pathlib.Path:
    """Write the measurement under *root*; return its path."""
    import tttrlib

    rng = np.random.default_rng(seed)
    times, channels = [], []
    for channel, rate_khz in ((0, BACKGROUND_KHZ["green"]), (1, BACKGROUND_KHZ["red"])):
        n = rng.poisson(rate_khz * 1e3 * DURATION_S)
        times.append(rng.uniform(0.0, DURATION_S, n))
        channels.append(np.full(n, channel))
    starts = rng.uniform(0.05, DURATION_S - 0.05, 200)
    for start in starts:
        n = rng.poisson(100.0)                               # 100 kHz for 1 ms
        times.append(start + rng.uniform(0.0, 1e-3, n))
        channels.append((rng.random(n) < 0.4).astype(int))   # 40 % red
    t = np.concatenate(times)
    ch = np.concatenate(channels)
    order = np.argsort(t, kind="stable")
    macro = np.unique(np.round(t[order] / TICK).astype(np.uint64), return_index=True)[1]
    ticks = np.round(t[order] / TICK).astype(np.uint64)[macro]
    data = tttrlib.TTTR()
    data.append_events(ticks, np.zeros(len(ticks), np.uint16), ch[order][macro].astype(np.int8),
                       np.zeros(len(ticks), np.int8), False, 0)
    data.header.set_macro_time_resolution(TICK)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "m000.spc"
    data.write(str(path))
    return path
