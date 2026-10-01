"""A small burstwise analysis folder on disk, with a known answer.

``<root>/m000.spc`` (SPC-130, 12.5 ns ticks, donor channel 0, acceptor channel 1) and
``<root>/burstwise/bi4_bur/m000.bur`` (zero-interleaved, as the burst reader expects;
photon counts per colour so the view can plot E against 2CDE). Static bursts keep one
acceptor fraction, dynamic ones switch half-way: the static ones read FRET-2CDE near 10,
the dynamic ones well above it.
"""

from __future__ import annotations

import pathlib

import numpy as np

TICK = 12.5e-9


def build(root: pathlib.Path, n_bursts: int = 60, photons: int = 120, seed: int = 3) -> pathlib.Path:
    """Write the measurement and its burst table under *root*; return the analysis folder."""
    import tttrlib

    rng = np.random.default_rng(seed)
    macro, chan, rows = [], [], []
    t = 0
    for b in range(n_bursts):
        start = len(macro)
        dynamic = b % 4 == 3
        low, high = (0.15, 0.8) if b % 2 else (0.8, 0.15)
        for k in range(photons):
            t += int(rng.exponential(800.0)) + 1                  # ~100 kHz in 12.5 ns ticks
            p_acc = (low if k < photons // 2 else high) if dynamic else low
            macro.append(t)
            chan.append(1 if rng.random() < p_acc else 0)
        rows.append((start, len(macro) - 1))
        t += 40_000_000                                           # 0.5 s between bursts
    data = tttrlib.TTTR()
    data.append_events(np.asarray(macro, np.uint64), np.zeros(len(macro), np.uint16),
                       np.asarray(chan, np.int8), np.zeros(len(macro), np.int8), False, 0)
    data.header.set_macro_time_resolution(TICK)
    root.mkdir(parents=True, exist_ok=True)
    data.write(str(root / "m000.spc"))

    folder = root / "burstwise"
    (folder / "bi4_bur").mkdir(parents=True, exist_ok=True)
    chan = np.asarray(chan)
    lines = ["First Photon\tLast Photon\tNumber of Photons (green)\tNumber of Photons (red)\tFirst File"]
    for first, last in rows:
        red = int(np.sum(chan[first:last + 1] == 1))
        lines += ["0\t0\t0\t0\t", f"{first}\t{last}\t{last - first + 1 - red}\t{red}\tm000.spc"]
    (folder / "bi4_bur" / "m000.bur").write_text("\n".join(lines))
    return folder
