"""A folder with two small simulated scans the browser tour (and its e2e check) can open."""

from __future__ import annotations

from pathlib import Path


def make_demo(folder: str | Path) -> Path:
    """Simulate two tiny confocal scans into *folder* (``scan_1.ptu``, ``scan_2.ptu``).

    The scans come from the flow-map demo's photon simulator, so each is a real PTU with
    line and frame markers; only the size is reduced to keep generation near a second.

    Parameters
    ----------
    folder : str or Path
        Existing directory to fill.

    Returns
    -------
    Path
        *folder*, which Open folder accepts.
    """
    from chisurf.plugins.microscopy.img_flow.demo import make_demo as simulate

    folder = Path(folder)
    for index, seed in enumerate((7, 11), start=1):
        simulate(folder, filename=f"scan_{index}.ptu", n_pixel=32, n_frames=6,
                 n_molecules=300.0, seed=seed)
    return folder
