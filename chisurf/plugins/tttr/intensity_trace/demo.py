"""A deterministic two-state photon stream the intensity-trace tool can generate itself (its guide and tests use it).

``make_demo(folder)`` writes ``intensity_trace_demo.spc`` (Becker & Hickl SPC-130): one molecule switching between a
low-FRET and a high-FRET state with exponential dwell times (means :data:`DWELL_MS`), its photons split between a donor
(routing channel 0) and an acceptor (channel 1) by the state's FRET efficiency (:data:`FRET`), on a weak background.
Binned at 2 ms, a two-state HMM recovers the states with the simulated occupancy (20 % / 80 %); the first detector's
share of the sum (the tool's "FRET": donor over sum, ``1 - E`` here) separates at 0.69 / 0.31; the single-exponential
dwell fits come out near 26 and 105 ms, longer than the simulated 20 / 80 ms because an excursion shorter than a few
bins is not resolved and merges two dwells.
Nothing here is a measurement.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

SEED = 20261005
DURATION_S = 20.0
RATE_HZ = 20000.0  # photons per second while the molecule emits
BACKGROUND_HZ = 500.0
DWELL_MS = (20.0, 80.0)  # mean dwell of state 0 and state 1
FRET = (0.3, 0.7)  # acceptor share in state 0 and state 1
MACRO_RES = 13.5e-9
MICRO_RES = 3.2958984375e-12
N_MICRO = 4096
STREAM_NAME = "intensity_trace_demo.spc"


def segments(seed: int = SEED):
    """``(start_s, end_s, state)`` of the switching molecule."""
    rng = np.random.default_rng(seed)
    t, state, out = 0.0, 0, []
    while t < DURATION_S:
        dwell = rng.exponential(DWELL_MS[state] / 1000.0)
        out.append((t, min(t + dwell, DURATION_S), state))
        t += dwell
        state = 1 - state
    return out


def photon_stream(seed: int = SEED):
    rng = np.random.default_rng(seed + 1)
    times, channels = [], []
    for start, end, state in segments(seed):
        n = rng.poisson(RATE_HZ * (end - start))
        times.append(rng.uniform(start, end, n))
        channels.append(np.where(rng.random(n) < FRET[state], 1, 0))
    nb = rng.poisson(BACKGROUND_HZ * DURATION_S)
    times.append(rng.uniform(0.0, DURATION_S, nb))
    channels.append(rng.integers(0, 2, nb))
    t, ch = np.concatenate(times), np.concatenate(channels)
    order = np.argsort(t)
    macro = np.round(t[order] / MACRO_RES).astype(np.uint64)
    micro = np.clip(rng.exponential(4e-9 / MICRO_RES, len(macro)), 0, N_MICRO - 1).astype(np.uint16)
    return macro, micro, ch[order].astype(np.int8)


def make_demo(folder, seed: int = SEED) -> Path:
    """Write the demonstration stream into *folder* once (an existing file is reused); return its path."""
    import tttrlib

    folder = Path(folder)
    path = folder / STREAM_NAME
    if path.is_file():
        return path
    folder.mkdir(parents=True, exist_ok=True)
    macro, micro, routing = photon_stream(seed)
    stream = tttrlib.TTTR()
    stream.append_events(macro, micro, routing, np.zeros(len(macro), dtype=np.int8))
    header = stream.header
    header.set_macro_time_resolution(MACRO_RES)
    header.set_micro_time_resolution(MICRO_RES)
    if not stream.write(str(path), "SPC-130", header):
        raise OSError(f"could not write {path}")
    return path


def demo_folder() -> Path:
    """The settings cache (never the user's data folders)."""
    import os

    root = os.environ.get("CHISURF_SETTINGS_DIR") or str(Path.home() / ".chisurf")
    return Path(root) / "cache" / "intensity_trace_demo"
