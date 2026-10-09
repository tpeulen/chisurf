"""A photon stream with known bursts and its BID selection, so the converter can teach itself.

``make_demo(folder)`` writes ``bid_demo.spc`` (Becker & Hickl SPC-130) and ``bid_demo.bid`` beside
it: a weak background on two detectors with :data:`N_BURSTS` bright, evenly spaced bursts of
:data:`BURST_MS`. The BID file lists, per burst, the index of the first and the last photon inside
the burst window (inclusive, the .bur "First Photon"/"Last Photon" convention). Converting it must
therefore give exactly ``N_BURSTS`` rows whose photon numbers are ``last - first + 1`` — the
answer is in the BID file itself. Nothing here is a measurement.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

STEM = "bid_demo"
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": 20261010,
    "duration_s": 3.0,
    "background_hz": 2000.0,
    "burst_rate_hz": 100000.0,
    "n_bursts": 6,
    "burst_ms": 4.0,
    "macro_resolution_s": 13.5e-9,
    "micro_resolution_s": 3.2958984375e-12,
    "n_micro": 4096,
    "lifetime_s": 4e-9,
    "file_type": "SPC-130",
}
N_BURSTS = DEMO["n_bursts"]
BURST_MS = DEMO["burst_ms"]


def burst_windows() -> list[tuple[float, float]]:
    """Return the ``(start_s, end_s)`` window of every simulated burst."""
    step = DEMO["duration_s"] / (DEMO["n_bursts"] + 1)
    width = DEMO["burst_ms"] / 1000.0
    return [(step * (i + 1), step * (i + 1) + width) for i in range(DEMO["n_bursts"])]


def photon_stream(seed: int = DEMO["seed"]):
    """Return time-ordered arrival times (s), micro times and routing channels."""
    rng = np.random.default_rng(seed)
    times = [rng.uniform(0.0, DEMO["duration_s"], rng.poisson(DEMO["background_hz"] * DEMO["duration_s"]))]
    for start, end in burst_windows():
        times.append(rng.uniform(start, end, rng.poisson(DEMO["burst_rate_hz"] * (end - start))))
    t = np.sort(np.concatenate(times))
    micro = np.clip(
        rng.exponential(DEMO["lifetime_s"] / DEMO["micro_resolution_s"], len(t)), 0, DEMO["n_micro"] - 1
    ).astype(np.uint16)
    routing = rng.integers(0, 2, len(t)).astype(np.int8)
    return t, micro, routing


def selection(t: np.ndarray) -> np.ndarray:
    """Return ``(first, last)`` photon indices, inclusive, of each burst window."""
    rows = []
    for start, end in burst_windows():
        inside = np.flatnonzero((t >= start) & (t < end))
        rows.append((int(inside[0]), int(inside[-1])))
    return np.asarray(rows, dtype=np.int64)


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "bid_to_analysis"


def _cache_is_good(path: Path) -> bool:
    """Require matching parameters and both recorded files intact."""
    try:
        parameters = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        recorded = path.with_suffix(".sha256").read_text(encoding="ascii").split()
        data = path.with_suffix(".spc").read_bytes() + path.read_bytes()
        return parameters == DEMO and recorded == [str(len(data)), hashlib.sha256(data).hexdigest()]
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the demo stream and its BID selection.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The BID file; the SPC stream it selects from has the same stem.
    """
    import tttrlib

    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.bid"
    if not overwrite and _cache_is_good(path):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    t, micro, routing = photon_stream()
    macro = np.round(t / DEMO["macro_resolution_s"]).astype(np.uint64)
    stream = tttrlib.TTTR()
    stream.append_events(macro, micro, routing, np.zeros(len(macro), dtype=np.int8))
    header = stream.header
    header.set_macro_time_resolution(DEMO["macro_resolution_s"])
    header.set_micro_time_resolution(DEMO["micro_resolution_s"])
    spc = path.with_suffix(".spc")
    if not stream.write(str(spc), DEMO["file_type"], header):
        raise OSError(f"could not write {spc}")
    np.savetxt(path, selection(t), fmt="%d")
    path.with_suffix(".json").write_text(json.dumps(DEMO, sort_keys=True, indent=2), encoding="utf-8")
    data = spc.read_bytes() + path.read_bytes()
    path.with_suffix(".sha256").write_text(
        f"{len(data)} {hashlib.sha256(data).hexdigest()}\n", encoding="ascii"
    )
    return path
