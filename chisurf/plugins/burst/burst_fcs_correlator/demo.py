"""A deterministic demonstration data set the burst-wise FCS correlator can generate itself.

``make_demo(folder)`` writes a small photon stream (``burst_fcs_demo.spc``, a Becker & Hickl SPC-130 file) and its burst table
(``burst_fcs_demo.spc.bst``, one ``first last`` photon-index pair per line), so the tool, its guide and its tests have something
to correlate without the user's own files. The photons are drawn from a seeded generator: eight bursts, each an inhomogeneous
Poisson process whose rate has a Gaussian envelope (a molecule crossing the focus, 1 ms wide) on a weak background, split at
random between two detectors with a 4 ns fluorescence decay. Nothing here is a measurement.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

SEED = 20261002
N_BURSTS = 8
PHOTONS_PER_BURST = 1500
#: Macro-time tick (s) and micro-time channel count of the written file (a 13.5 ns / 3.3 ps SPC-130 header, so the file reads back by itself).
MACRO_RES = 13.5e-9
MICRO_RES = 3.2958984375e-12
N_MICRO = 4096
LIFETIME_S = 4.0e-9
STREAM_NAME = "burst_fcs_demo.spc"
TABLE_NAME = "burst_fcs_demo.spc.bst"


def photon_stream(seed: int = SEED, n_bursts: int = N_BURSTS):
    """The photons and the burst ranges: ``(macro, micro, routing, ranges)`` as numpy arrays and (first, last) index pairs."""
    rng = np.random.default_rng(seed)
    macro, micro, routing, ranges = [], [], [], []
    t0, index = 5_000_000, 0
    for _ in range(n_bursts):
        centre = t0 + 370_000  # a burst 10 ms (370 000 ticks) long, its envelope 1 ms wide
        width = 74_000 * (0.7 + 0.6 * rng.random())
        n = PHOTONS_PER_BURST
        times = np.sort(np.concatenate([rng.normal(centre, width, int(0.8 * n)), rng.uniform(t0, t0 + 740_000, n - int(0.8 * n))]))
        times = np.clip(times, t0, t0 + 740_000).astype(np.uint64)
        macro.append(times)
        micro.append(np.clip(rng.exponential(LIFETIME_S / MICRO_RES, n), 0, N_MICRO - 1).astype(np.uint16))
        routing.append(rng.integers(0, 2, n).astype(np.int8))
        ranges.append((index, index + n - 1))
        index += n
        t0 += 740_000 + 3_700_000  # 50 ms of nothing between bursts
    return (np.concatenate(macro), np.concatenate(micro), np.concatenate(routing), ranges)


def make_demo(folder, seed: int = SEED) -> tuple[Path, Path]:
    """Write the demonstration photon stream and burst table into *folder*; return their paths."""
    import tttrlib

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    macro, micro, routing, ranges = photon_stream(seed)
    stream = tttrlib.TTTR()
    stream.append_events(macro, micro, routing, np.zeros(len(macro), dtype=np.int8))
    spc, table = folder / STREAM_NAME, folder / TABLE_NAME
    header = stream.header
    header.set_macro_time_resolution(MACRO_RES)
    header.set_micro_time_resolution(MICRO_RES)
    if not stream.write(str(spc), "SPC-130", header):
        raise OSError(f"could not write {spc}")
    table.write_text("".join(f"{a} {b}\n" for a, b in ranges))
    return spc, table
