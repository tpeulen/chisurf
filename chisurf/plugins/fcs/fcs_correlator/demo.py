"""A deterministic FCS data set the correlator can generate itself, so its guide and tests run without the user's files.

``make_demo(folder)`` writes ``fcs_demo.spc`` (a Becker & Hickl SPC-130 file): molecules enter the focus at random
(Poisson, :data:`MOLECULE_RATE` per second) and each emits a Poisson number of photons whose arrival times follow a
Gaussian envelope of width :data:`TRANSIT_S` (a crossing), on a weak uniform background; every photon goes to one of
two detectors at random. Correlated, the curve decays on the transit time (about 0.25 ms) and its amplitude is about
one over the mean number of molecules in the focus. Nothing here is a measurement.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
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


SPC_FILENAME = STREAM_NAME
MEMBERS = (SPC_FILENAME,)
DEMO = {
    "seed": SEED,
    "duration_s": DURATION_S,
    "molecule_rate_hz": MOLECULE_RATE,
    "transit_s": TRANSIT_S,
    "photons_per_transit": PHOTONS_PER_TRANSIT,
    "background_hz": BACKGROUND_HZ,
    "macro_resolution_s": MACRO_RES,
    "micro_resolution_s": MICRO_RES,
    "micro_channels": N_MICRO,
    "lifetime_s": LIFETIME_S,
    "routing_channels": 2,
    "format": "SPC-130",
}


def photon_stream(seed: int = SEED, *, config: dict | None = None):
    """``(macro, micro, routing)``: the demo photons, sorted by arrival."""
    values = dict(DEMO) if config is None else config
    rng = np.random.default_rng(seed)
    n_mol = rng.poisson(values["molecule_rate_hz"] * values["duration_s"])
    centres = rng.uniform(0.0, values["duration_s"], n_mol)
    counts = rng.poisson(values["photons_per_transit"], n_mol)
    times = np.repeat(centres, counts) + rng.normal(0.0, values["transit_s"], int(counts.sum()))
    background = rng.uniform(
        0.0, values["duration_s"], rng.poisson(values["background_hz"] * values["duration_s"])
    )
    times = np.sort(np.concatenate([times, background]))
    times = times[(times >= 0.0) & (times < values["duration_s"])]
    macro = np.round(times / values["macro_resolution_s"]).astype(np.uint64)
    micro = np.clip(
        rng.exponential(values["lifetime_s"] / values["micro_resolution_s"], len(macro)),
        0,
        values["micro_channels"] - 1,
    ).astype(np.uint16)
    routing = rng.integers(0, values["routing_channels"], len(macro)).astype(np.int8)
    return macro, micro, routing


def demo_folder() -> Path:
    """Return this tool's generated-data directory in the settings tree."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "fcs_correlator"


def _cache_is_good(folder: Path, config: dict) -> bool:
    """Reuse only a complete artifact set with matching parameters and byte hashes."""
    try:
        record = json.loads((folder / "demo.json").read_text(encoding="utf-8"))
        return (
            record["parameters"] == config
            and set(record["sha256"]) == set(MEMBERS)
            and all(
                (folder / name).is_file()
                and hashlib.sha256((folder / name).read_bytes()).hexdigest()
                == record["sha256"][name]
                for name in MEMBERS
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Create or reuse the declared synthetic input and its provenance sidecar.

    Parameters
    ----------
    folder : str or pathlib.Path, optional
        Generated-data directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate this demo's declared files even when its cache is valid.

    Returns
    -------
    pathlib.Path
        Generated SPC photon stream; choose Correlate to analyse it.
    """
    import tttrlib

    folder = Path(folder) if folder is not None else demo_folder()
    config = dict(DEMO)
    if not overwrite and _cache_is_good(folder, config):
        return folder / SPC_FILENAME
    folder.mkdir(parents=True, exist_ok=True)
    # Publish only complete newly written files. A failed writer cannot corrupt
    # the previously usable input; no unrelated folder members are removed.
    with tempfile.TemporaryDirectory(prefix=".demo-", dir=folder) as staging:
        staged = Path(staging)
        macro, micro, routing = photon_stream(config["seed"], config=config)
        stream = tttrlib.TTTR()
        stream.append_events(macro, micro, routing, np.zeros(len(macro), dtype=np.int8))
        header = stream.header
        header.set_macro_time_resolution(config["macro_resolution_s"])
        header.set_micro_time_resolution(config["micro_resolution_s"])
        if not stream.write(str(staged / SPC_FILENAME), config["format"], header):
            raise OSError(f"could not write {staged / SPC_FILENAME}")
        record = {
            "parameters": config,
            "sha256": {
                name: hashlib.sha256((staged / name).read_bytes()).hexdigest() for name in MEMBERS
            },
        }
        (staged / "demo.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        for name in (*MEMBERS, "demo.json"):
            os.replace(staged / name, folder / name)
    return folder / SPC_FILENAME
