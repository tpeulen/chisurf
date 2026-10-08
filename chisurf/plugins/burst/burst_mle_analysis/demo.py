"""Deterministic synthetic bursts with a declared lifetime and physical clock."""

from __future__ import annotations

import hashlib
import json
import tempfile
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


DEMO = {
    "seed": SEED,
    "burst_count": BURST_COUNT,
    "photons_per_burst": BURST_PHOTONS,
    "signal_lifetime_ns": SIGNAL_LIFETIME_NS,
    "micro_resolution_s": MICRO_RESOLUTION_S,
    "channels": CHANNELS,
    "macro_resolution_s": MACRO_RESOLUTION_S,
    "reference_photons": 4096,
    "background_photons": 1024,
    "prompt_mean_channels": 20.0,
    "prompt_sigma_channels": 2.0,
    "macro_ticks_per_photon": 100,
    "setup": SETUP,
}


def demo_folder() -> Path:
    """Keep generated data in the settings cache, separate from measurement files."""
    from chisurf.core.settings.path_utils import get_path

    return get_path("settings") / "demos" / "burst_mle_analysis"


def make_demo(
    folder: str | Path | None = None, *, overwrite: bool = False, seed: int = SEED
) -> Path:
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

    folder = Path(folder) if folder is not None else demo_folder()
    raw = folder / "synthetic_mle.ptu"
    bur = folder / "analysis" / "bur4" / "synthetic_mle.bur"
    manifest = folder / "demo.json"
    settings = {**DEMO, "seed": seed}
    artifacts = (
        Path("synthetic_mle.ptu"),
        Path("analysis/bur4/synthetic_mle.bur"),
        Path("analysis/Info/photon_selection_parameters.json"),
    )
    if not overwrite and manifest.is_file():
        try:
            metadata = json.loads(manifest.read_text())
            hashes = {
                str(name): hashlib.sha256((folder / name).read_bytes()).hexdigest()
                for name in artifacts
            }
            if metadata.get("settings") == settings and metadata.get("files") == hashes:
                return bur
        except (OSError, ValueError):
            pass
    folder.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix=".mle-demo-", dir=folder)
    try:
        generated_folder = Path(temporary.name)
        generated_raw = generated_folder / raw.name
        generated_bur = generated_folder / "analysis" / "bur4" / bur.name
        rng = np.random.default_rng(seed)
        reference = np.clip(
            np.rint(
                rng.normal(
                    settings["prompt_mean_channels"],
                    settings["prompt_sigma_channels"],
                    settings["reference_photons"],
                )
            ),
            0,
            settings["channels"] - 1,
        )
        background = rng.integers(0, settings["channels"], settings["background_photons"])
        decay = rng.exponential(
            settings["signal_lifetime_ns"] / (settings["micro_resolution_s"] * 1e9),
            settings["burst_count"] * settings["photons_per_burst"],
        )
        prompt = rng.normal(
            settings["prompt_mean_channels"], settings["prompt_sigma_channels"], len(decay)
        )
        signal = np.clip(np.rint(prompt + decay), 0, settings["channels"] - 1)
        micro = np.concatenate((reference, background, signal)).astype(np.uint16)
        routing: np.ndarray = (np.arange(len(micro)) % 2).astype(np.int8)
        macro = np.arange(len(micro), dtype=np.uint64) * np.uint64(
            settings["macro_ticks_per_photon"]
        )
        stream = tttrlib.TTTR(macro, micro, routing, np.zeros(len(micro), dtype=np.int8))
        stream.header.set_macro_time_resolution(settings["macro_resolution_s"])
        stream.header.set_micro_time_resolution(settings["micro_resolution_s"])
        stream.header.set_number_of_micro_time_channels(settings["channels"])
        if not stream.write(str(generated_raw), "PTU"):
            raise OSError("Could not write synthetic Burst MLE photons.")
        first = len(reference) + len(background)
        starts: np.ndarray = (
            first + np.arange(settings["burst_count"]) * settings["photons_per_burst"]
        )
        intervals = np.column_stack((starts, starts + settings["photons_per_burst"] - 1))
        table = summarize_bursts(
            intervals, raw.name, stream, detectors=settings["setup"]["detectors"]
        )
        write_bur(table, generated_bur)
        info = generated_bur.parent.parent / "Info" / "photon_selection_parameters.json"
        info.parent.mkdir(exist_ok=True)
        info.write_text(json.dumps({"setup_info": settings["setup"]}, indent=2) + "\n")
        metadata = {
            "settings": settings,
            "files": {
                str(name): hashlib.sha256((generated_folder / name).read_bytes()).hexdigest()
                for name in artifacts
            },
            "truth": {
                "signal_lifetime_ns": settings["signal_lifetime_ns"],
                "burst_count": settings["burst_count"],
                "photons_per_burst": settings["photons_per_burst"],
                "qualification": "Synthetic input ground truth; fitted estimates are not exact or acquisition calibration.",
            },
        }
        generated_manifest = generated_folder / manifest.name
        generated_manifest.write_text(json.dumps(metadata, indent=2) + "\n")
        for name in artifacts:
            destination = folder / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            (generated_folder / name).replace(destination)
        generated_manifest.replace(manifest)
    finally:
        temporary.cleanup()
    return bur
