"""Deterministic synthetic bursts with a declared lifetime and physical clock."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

SEED = 20261008
BURST_COUNT = 16
BURST_PHOTONS = 1000
SIGNAL_LIFETIME_NS = 2.0
MICRO_RESOLUTION_S = 32e-12
CHANNELS = 1024
MACRO_RESOLUTION_S = MICRO_RESOLUTION_S * CHANNELS
SETUP = {
    "detectors": {
        "synthetic": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0, "l1": 0.0, "l2": 0.0}
    },
    "windows": {},
    "tttr_reading": {
        "file_type": "PTU",
        "micro_time_resolution": 32.0,
        "macro_time_resolution": 32.768,
        "micro_time_binning": 1,
        "override_timing": False,
    },
    "apply_lut": False,
    "channel_luts": {},
    "channel_shifts": {},
}


def demo_folder() -> Path:
    """Keep generated data in the settings cache, separate from measurement files."""
    settings = os.environ.get("CHISURF_SETTINGS_DIR") or str(Path.home() / ".chisurf")
    return Path(settings) / "cache" / "burst_mle_demo_v1"


def make_demo(folder: str | Path) -> Path:
    """Write real synthetic PTU photons and declared burst summaries without overwriting inputs.

    Parameters
    ----------
    folder : str or pathlib.Path
        Dedicated demonstration directory. Repeated calls reuse its completed manifest.

    Returns
    -------
    pathlib.Path
        The generated BUR table, read by the normal analysis-folder loader.
    """
    import tttrlib

    from chisurf.plugins.burst.burst_selection.api.io import write_bur
    from chisurf.plugins.burst.burst_selection.api.selection import summarize_bursts

    folder = Path(folder)
    raw = folder / "synthetic_mle.ptu"
    bur = folder / "analysis" / "bur4" / "synthetic_mle.bur"
    manifest = folder / "demo.json"
    if manifest.is_file():
        metadata = json.loads(manifest.read_text())
        if metadata.get("seed") != SEED or not raw.is_file() or not bur.is_file():
            raise ValueError(
                "The generated demonstration is incomplete or belongs to another version."
            )
        return bur
    if raw.exists() or bur.exists():
        raise FileExistsError("An incomplete demonstration already occupies this cache directory.")
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    reference = np.clip(np.rint(rng.normal(20.0, 2.0, 4096)), 0, CHANNELS - 1)
    background = rng.integers(0, CHANNELS, 1024)
    decay = rng.exponential(
        SIGNAL_LIFETIME_NS / (MICRO_RESOLUTION_S * 1e9), BURST_COUNT * BURST_PHOTONS
    )
    prompt = rng.normal(20.0, 2.0, len(decay))
    signal = np.clip(np.rint(prompt + decay), 0, CHANNELS - 1)
    micro = np.concatenate((reference, background, signal)).astype(np.uint16)
    routing: np.ndarray = (np.arange(len(micro)) % 2).astype(np.int8)
    macro = np.arange(len(micro), dtype=np.uint64) * np.uint64(100)
    stream = tttrlib.TTTR(macro, micro, routing, np.zeros(len(micro), dtype=np.int8))
    stream.header.set_macro_time_resolution(MACRO_RESOLUTION_S)
    stream.header.set_micro_time_resolution(MICRO_RESOLUTION_S)
    stream.header.set_number_of_micro_time_channels(CHANNELS)
    if not stream.write(str(raw), "PTU"):
        raise OSError("Could not write synthetic Burst MLE photons.")
    first = len(reference) + len(background)
    starts: np.ndarray = first + np.arange(BURST_COUNT) * BURST_PHOTONS
    intervals = np.column_stack((starts, starts + BURST_PHOTONS - 1))
    table = summarize_bursts(intervals, raw.name, stream, detectors=SETUP["detectors"])
    write_bur(table, bur)
    info = bur.parent.parent / "Info" / "photon_selection_parameters.json"
    info.parent.mkdir(exist_ok=True)
    info.write_text(json.dumps({"setup_info": SETUP}, indent=2) + "\n")
    manifest.write_text(
        json.dumps(
            {
                "seed": SEED,
                "signal_lifetime_ns": SIGNAL_LIFETIME_NS,
                "burst_count": BURST_COUNT,
                "photons_per_burst": BURST_PHOTONS,
                "micro_resolution_s": MICRO_RESOLUTION_S,
                "qualification": "Synthetic input ground truth; fitted estimates are not exact or acquisition calibration.",
            },
            indent=2,
        )
        + "\n"
    )
    return bur
