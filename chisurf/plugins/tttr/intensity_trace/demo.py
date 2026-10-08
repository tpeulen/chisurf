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

import hashlib
import json
from pathlib import Path
from typing import Any

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
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": SEED,
    "duration_s": DURATION_S,
    "rate_hz": RATE_HZ,
    "background_hz": BACKGROUND_HZ,
    "dwell_ms": list(DWELL_MS),
    "fret": list(FRET),
    "macro_resolution_s": MACRO_RES,
    "micro_resolution_s": MICRO_RES,
    "n_micro": N_MICRO,
    "lifetime_s": 4e-9,
    "filename": STREAM_NAME,
    "file_type": "SPC-130",
}


def segments(seed: int = SEED):
    """``(start_s, end_s, state)`` of the switching molecule."""
    rng = np.random.default_rng(seed)
    t, state, out = 0.0, 0, []
    while t < DEMO["duration_s"]:
        dwell = rng.exponential(DEMO["dwell_ms"][state] / 1000.0)
        out.append((t, min(t + dwell, DEMO["duration_s"]), state))
        t += dwell
        state = 1 - state
    return out


def photon_stream(seed: int = SEED):
    """Return deterministic macro times, micro times and routes for the switching sample."""
    rng = np.random.default_rng(seed + 1)
    times, channels = [], []
    for start, end, state in segments(seed):
        n = rng.poisson(DEMO["rate_hz"] * (end - start))
        times.append(rng.uniform(start, end, n))
        channels.append(np.where(rng.random(n) < DEMO["fret"][state], 1, 0))
    nb = rng.poisson(DEMO["background_hz"] * DEMO["duration_s"])
    times.append(rng.uniform(0.0, DEMO["duration_s"], nb))
    channels.append(rng.integers(0, 2, nb))
    t, ch = np.concatenate(times), np.concatenate(channels)
    order = np.argsort(t)
    macro = np.round(t[order] / DEMO["macro_resolution_s"]).astype(np.uint64)
    micro = np.clip(
        rng.exponential(DEMO["lifetime_s"] / DEMO["micro_resolution_s"], len(macro)),
        0,
        DEMO["n_micro"] - 1,
    ).astype(np.uint16)
    return macro, micro, ch[order].astype(np.int8)


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "intensity_trace"


def _cache_is_good(path: Path) -> bool:
    """Require matching parameters and the complete recorded photon file."""
    try:
        parameters = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        checksum = path.with_suffix(".sha256").read_text(encoding="ascii").split()
        data = path.read_bytes()
        return (
            parameters == DEMO
            and len(checksum) == 2
            and len(data) > 4
            and checksum == [str(len(data)), hashlib.sha256(data).hexdigest()]
        )
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the deterministic switching stream and its parameter sidecar.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and file checksum match.

    Returns
    -------
    pathlib.Path
        Primary SPC input; its JSON sidecar records ``DEMO`` and its checksum
        rejects partial or modified cached data.
    """
    import tttrlib

    folder = demo_folder() if folder is None else Path(folder)
    path = folder / DEMO["filename"]
    if not overwrite and _cache_is_good(path):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    macro, micro, routing = photon_stream(int(DEMO["seed"]))
    stream = tttrlib.TTTR()
    stream.append_events(macro, micro, routing, np.zeros(len(macro), dtype=np.int8))
    header = stream.header
    header.set_macro_time_resolution(DEMO["macro_resolution_s"])
    header.set_micro_time_resolution(DEMO["micro_resolution_s"])
    if not stream.write(str(path), DEMO["file_type"], header):
        raise OSError(f"could not write {path}")
    path.with_suffix(".json").write_text(
        json.dumps(DEMO, sort_keys=True, indent=2), encoding="utf-8"
    )
    data = path.read_bytes()
    path.with_suffix(".sha256").write_text(
        f"{len(data)} {hashlib.sha256(data).hexdigest()}\n", encoding="ascii"
    )
    return path
