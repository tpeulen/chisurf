"""Physical, explicitly synthetic PTU demonstration with exactly known VV/VH counts."""

from __future__ import annotations

import os
from pathlib import Path

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


def demo_folder() -> Path:
    """Use the application settings cache, separate from measurement data and saved setups."""
    settings = os.environ.get("CHISURF_SETTINGS_DIR") or str(Path.home() / ".chisurf")
    return Path(settings) / "cache" / "microtime_histogram_demo_v1"


def make_demo(folder: str | Path) -> Path:
    """Write deterministic synthetic photons once without overwriting an existing file.

    Parameters
    ----------
    folder : str or pathlib.Path
        Dedicated cache directory. The writer uses tttrlib's existing PTU header/export API.

    Returns
    -------
    pathlib.Path
        The real PTU input. Routes 0 and 1 contain 3000 and 1500 photons, respectively.
    """
    import tttrlib

    path = Path(folder) / "synthetic_microtime_demo.ptu"
    if path.exists():
        if not path.is_file():
            raise OSError(f"Demo target is not a file: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    bins: NDArray[np.uint16] = np.arange(
        FIRST_CHANNEL, FIRST_CHANNEL + len(VV_COUNTS), dtype=np.uint16
    )
    vv: NDArray[np.uint16] = np.repeat(bins, VV_COUNTS)
    vh: NDArray[np.uint16] = np.repeat(bins, np.asarray(VV_COUNTS) // 2)
    micro = np.concatenate([vv, vh])
    routing = np.concatenate([np.zeros(len(vv), dtype=np.int8), np.ones(len(vh), dtype=np.int8)])
    order = np.random.default_rng(SEED).permutation(len(micro))
    macro = np.arange(len(micro), dtype=np.uint64) * np.uint64(100)
    stream = tttrlib.TTTR(macro, micro[order], routing[order], np.zeros(len(micro), dtype=np.int8))
    stream.header.set_macro_time_resolution(MACRO_RESOLUTION_S)
    stream.header.set_micro_time_resolution(MICRO_RESOLUTION_S)
    stream.header.set_number_of_micro_time_channels(256)
    if not stream.write(str(path), "PTU"):
        raise OSError(f"Could not write synthetic demonstration: {path}")
    return path
