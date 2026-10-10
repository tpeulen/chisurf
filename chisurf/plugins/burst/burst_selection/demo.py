"""A photon stream with a known number of bursts, so Burst Selection can teach itself.

``make_demo(folder)`` writes ``bs_demo.spc`` (Becker & Hickl SPC-130): a weak background on the
green (routing channel 0) and red (channel 8) detectors with :data:`N_BURSTS` bright, evenly
spaced bursts. Every burst carries :data:`PHOTONS_PER_BURST` photons spread over about a
millisecond, of which :data:`RED_FRACTION` land on the red detector. The answer is therefore
known: the search must report exactly ``N_BURSTS`` bursts, each with about
``PHOTONS_PER_BURST`` photons and a proximity ratio near ``RED_FRACTION``. Nothing here is a
measurement.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

STEM = "bs_demo"
N_BURSTS = 12
PHOTONS_PER_BURST = 200
RED_FRACTION = 0.6
#: The detector definition the example loads: green on channel 0, red on channel 8.
SETUP: dict[str, Any] = {
    "detectors": {
        "green": {"chs": [0], "micro_time_ranges": []},
        "red": {"chs": [8], "micro_time_ranges": []},
    },
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130"},
}
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": 20261010,
    "duration_s": 6.0,
    "background_hz": 1000.0,
    "burst_sigma_ms": 0.25,
    "n_bursts": N_BURSTS,
    "photons_per_burst": PHOTONS_PER_BURST,
    "red_fraction": RED_FRACTION,
    "macro_resolution_s": 13.5e-9,
    "micro_resolution_s": 3.2958984375e-12,
    "n_micro": 4096,
    "lifetime_s": 2e-9,
    "green_channel": 0,
    "red_channel": 8,
    "file_type": "SPC-130",
}


def burst_centres_s() -> np.ndarray:
    """Return the centre time (s) of every planted burst."""
    step = DEMO["duration_s"] / (DEMO["n_bursts"] + 1)
    return step * np.arange(1, DEMO["n_bursts"] + 1)


def photon_stream(seed: int = DEMO["seed"]):
    """Return time-ordered arrival times (s), micro times and routing channels."""
    cfg = DEMO
    rng = np.random.default_rng(seed)
    parts = [rng.uniform(0.0, cfg["duration_s"], rng.poisson(cfg["background_hz"] * cfg["duration_s"]))]
    chans = [np.where(rng.random(parts[0].size) < 0.5, cfg["green_channel"], cfg["red_channel"])]
    for centre in burst_centres_s():
        t = rng.normal(centre, cfg["burst_sigma_ms"] * 1e-3, cfg["photons_per_burst"])
        parts.append(t)
        chans.append(np.where(rng.random(t.size) < cfg["red_fraction"], cfg["red_channel"], cfg["green_channel"]))
    t = np.concatenate(parts)
    c = np.concatenate(chans).astype(np.int8)
    order = np.argsort(t, kind="stable")
    t, c = t[order], c[order]
    micro = np.clip(
        rng.exponential(cfg["lifetime_s"] / cfg["micro_resolution_s"], t.size), 0, cfg["n_micro"] - 1
    ).astype(np.uint16)
    return t, micro, c


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "burst_selection"


def _digest(path: Path) -> str:
    """Return the checksum of the stream file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cache_is_good(path: Path) -> bool:
    """Require matching parameters and an intact stream."""
    try:
        side = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        return side == {"demo": DEMO, "sha256": _digest(path)}
    except (OSError, ValueError):
        return False


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the demo stream.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the stored parameters and checksum match.

    Returns
    -------
    pathlib.Path
        The SPC-130 file; its JSON sidecar holds the settings and a checksum.
    """
    import tttrlib

    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.spc"
    if not overwrite and path.is_file() and _cache_is_good(path):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    t, micro, routing = photon_stream()
    macro = np.round(t / DEMO["macro_resolution_s"]).astype(np.uint64)
    stream = tttrlib.TTTR()
    stream.append_events(macro, micro, routing, np.zeros(macro.size, dtype=np.int8))
    header = stream.header
    header.set_macro_time_resolution(DEMO["macro_resolution_s"])
    header.set_micro_time_resolution(DEMO["micro_resolution_s"])
    if not stream.write(str(path), DEMO["file_type"], header):
        raise OSError(f"could not write {path}")
    path.with_suffix(".json").write_text(
        json.dumps({"demo": DEMO, "sha256": _digest(path)}, sort_keys=True, indent=2), encoding="utf-8"
    )
    return path
