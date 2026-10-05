"""A deterministic FCS data set the correlator can generate itself, so its guide and tests run without the user's files.

``make_demo(folder)`` writes ``fcs_demo.spc`` (a Becker & Hickl SPC-130 file): molecules enter the focus at random
(Poisson, :data:`MOLECULE_RATE` per second) and each emits a Poisson number of photons whose arrival times follow a
Gaussian envelope of width :data:`TRANSIT_S` (a crossing), on a weak uniform background; every photon goes to one of
two detectors at random. Correlated, the curve decays on the transit time (about 0.25 ms) and its amplitude is about
one over the mean number of molecules in the focus. Nothing here is a measurement.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

SEED = 20261005
DURATION_S = 5.0
MOLECULE_RATE = 1000.0  # molecules entering per second
TRANSIT_S = 0.25e-3  # width (sigma) of a crossing
PHOTONS_PER_TRANSIT = 30.0
BACKGROUND_HZ = 1000.0
#: Macro-time tick (s) and micro-time channel count (an SPC-130 header, so the file reads back by itself).
MACRO_RES = 13.5e-9
MICRO_RES = 3.2958984375e-12
N_MICRO = 4096
LIFETIME_S = 4.0e-9
STREAM_NAME = "fcs_demo.spc"


def photon_stream(seed: int = SEED):
    """``(macro, micro, routing)``: the demo photons, sorted by arrival."""
    rng = np.random.default_rng(seed)
    n_mol = rng.poisson(MOLECULE_RATE * DURATION_S)
    centres = rng.uniform(0.0, DURATION_S, n_mol)
    counts = rng.poisson(PHOTONS_PER_TRANSIT, n_mol)
    times = np.repeat(centres, counts) + rng.normal(0.0, TRANSIT_S, int(counts.sum()))
    background = rng.uniform(0.0, DURATION_S, rng.poisson(BACKGROUND_HZ * DURATION_S))
    times = np.sort(np.concatenate([times, background]))
    times = times[(times >= 0.0) & (times < DURATION_S)]
    macro = np.round(times / MACRO_RES).astype(np.uint64)
    micro = np.clip(rng.exponential(LIFETIME_S / MICRO_RES, len(macro)), 0, N_MICRO - 1).astype(np.uint16)
    routing = rng.integers(0, 2, len(macro)).astype(np.int8)
    return macro, micro, routing


def make_demo(folder, seed: int = SEED) -> Path:
    """Write the demonstration photon stream into *folder* (once; an existing file is reused); return its path."""
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
    """Where the demo is written: ChiSurf's settings cache (never the user's data folders)."""
    import os

    root = os.environ.get("CHISURF_SETTINGS_DIR") or str(Path.home() / ".chisurf")
    return Path(root) / "cache" / "fcs_demo"
