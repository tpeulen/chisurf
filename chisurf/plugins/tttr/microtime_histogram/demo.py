"""Physical, explicitly synthetic PTU demonstration with exactly known VV/VH counts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

SEED = 20261007
MICRO_RESOLUTION_S = 32e-12
MACRO_RESOLUTION_S = 25e-9
VV_COUNTS = (0, 100, 300, 600, 1000, 600, 300, 100, 0)
FIRST_CHANNEL = 20
SETUP = {
    "polarization_resolved": True,
    "detectors": {"synthetic VV/VH": {"chs": [0, 1], "g_factor": 1.0}},
    "windows": {},
    "tttr_reading": {
        "file_type": "PTU",
        "macro_time_resolution": 25.0,
        "micro_time_resolution": 32.0,
        "override_timing": False,
        "micro_time_binning": 1,
    },
}

DEMO: dict[str, Any] = {
    "version": 1,
    "seed": SEED,
    "vv_counts": list(VV_COUNTS),
    "first_channel": FIRST_CHANNEL,
    "n_micro": 256,
    "macro_resolution_s": MACRO_RESOLUTION_S,
    "micro_resolution_s": MICRO_RESOLUTION_S,
    "macro_step": 100,
    "filename": "synthetic_microtime_demo.ptu",
    "file_type": "PTU",
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "microtime_histogram"


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
    """Write deterministic synthetic photons and their parameter sidecar.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when the parameters and recorded checksum match.

    Returns
    -------
    pathlib.Path
        Primary PTU input. Default routes 0 and 1 contain 3000 and 1500
        photons; the JSON sidecar records ``DEMO`` and a checksum rejects
        partial or modified cached data.
    """
    import tttrlib

    path = (demo_folder() if folder is None else Path(folder)) / DEMO["filename"]
    if not overwrite and _cache_is_good(path):
        return path
    if path.exists() and not path.is_file():
        raise OSError(f"Demo target is not a file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    first, counts = DEMO["first_channel"], DEMO["vv_counts"]
    bins: NDArray[np.uint16] = np.arange(first, first + len(counts), dtype=np.uint16)
    vv: NDArray[np.uint16] = np.repeat(bins, counts)
    vh: NDArray[np.uint16] = np.repeat(bins, np.asarray(counts) // 2)
    micro = np.concatenate([vv, vh])
    routing = np.concatenate([np.zeros(len(vv), dtype=np.int8), np.ones(len(vh), dtype=np.int8)])
    order = np.random.default_rng(DEMO["seed"]).permutation(len(micro))
    macro = np.arange(len(micro), dtype=np.uint64) * np.uint64(DEMO["macro_step"])
    stream = tttrlib.TTTR(macro, micro[order], routing[order], np.zeros(len(micro), dtype=np.int8))
    stream.header.set_macro_time_resolution(DEMO["macro_resolution_s"])
    stream.header.set_micro_time_resolution(DEMO["micro_resolution_s"])
    stream.header.set_number_of_micro_time_channels(DEMO["n_micro"])
    if not stream.write(str(path), DEMO["file_type"]):
        raise OSError(f"Could not write synthetic demonstration: {path}")
    path.with_suffix(".json").write_text(
        json.dumps(DEMO, sort_keys=True, indent=2), encoding="utf-8"
    )
    data = path.read_bytes()
    path.with_suffix(".sha256").write_text(
        f"{len(data)} {hashlib.sha256(data).hexdigest()}\n", encoding="ascii"
    )
    return path
