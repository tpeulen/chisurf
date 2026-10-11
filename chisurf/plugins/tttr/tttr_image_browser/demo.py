"""A folder with two small simulated scans the browser tour (and its e2e check) can open.

``make_demo()`` writes ``scan_1.ptu`` and ``scan_2.ptu`` into the settings cache. The scans come from the
flow-map demo's photon simulator, so each is a real PTU with line and frame markers; only the size is
reduced to keep generation near a second. Nothing here is a measurement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: The simulation, in one place so the guide and the tests agree.
DEMO: dict[str, Any] = {
    "n_pixel": 32,
    "n_frames": 6,
    "n_molecules": 300.0,
    #: One PTU per seed: ``scan_1.ptu``, ``scan_2.ptu``.
    "seeds": [7, 11],
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.plugins.demo_cache import cache_folder

    return cache_folder("tttr_image_browser")


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse the two simulated scans.

    Parameters
    ----------
    folder : str or Path, optional
        Cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Simulate again even when the files are cached.

    Returns
    -------
    Path
        *folder*, which Open folder accepts.
    """
    from chisurf.plugins.microscopy.img_flow.demo import make_demo as simulate

    folder = demo_folder() if folder is None else Path(folder)
    cfg = {key: value for key, value in DEMO.items() if key != "seeds"}
    for index, seed in enumerate(DEMO["seeds"], start=1):
        simulate(folder, overwrite=overwrite, filename=f"scan_{index}.ptu", seed=seed, **cfg)
    return folder
