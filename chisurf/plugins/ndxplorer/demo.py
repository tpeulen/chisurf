"""A small burst table with a *known* answer, so the tour can be walked without your own data.

Five populations are simulated: a low-, a mid- and a high-FRET species at stoichiometry near 0.5, a
donor-only and an acceptor-only population at the stoichiometry extremes. The donor lifetime follows
``tau = 4 ns * (1 - E)``, so on the lifetime-vs-FRET map ndX opens by default the populations lie along the
static FRET line; the simulated parameters are in :data:`POPULATIONS`. Nothing here is a measurement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

#: ``(label, FRET efficiency, stoichiometry, number of bursts)`` of each simulated population.
POPULATIONS = (
    ("low FRET", 0.15, 0.50, 1200),
    ("mid FRET", 0.50, 0.50, 1500),
    ("high FRET", 0.85, 0.50, 1000),
    ("donor only", 0.02, 0.97, 600),
    ("acceptor only", 0.50, 0.03, 500),
)

DEMO_NAME = "ndx_demo_bursts.csv"
#: The simulation, in one place so the guide and the tests agree.
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": 7,
    "populations": [list(p) for p in POPULATIONS],
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.plugins.demo_cache import cache_folder

    return cache_folder("ndxplorer")


def make_demo(
    folder: str | Path | None = None, *, overwrite: bool = False, seed: int | None = None
) -> Path:
    """Write or reuse the demo burst table.

    Parameters
    ----------
    folder : str or pathlib.Path, optional
        Cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Simulate again even when the stamped parameters and checksum match.
    seed : int, optional
        Seed of the simulation instead of ``DEMO["seed"]``, so the table is the same every time.

    Returns
    -------
    pathlib.Path
        The CSV file, one row per burst.
    """
    from chisurf.plugins.demo_cache import is_current, record

    config = {**DEMO, **({} if seed is None else {"seed": int(seed)})}
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / DEMO_NAME
    if not overwrite and path.is_file() and is_current(folder, [DEMO_NAME], config):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(config["seed"])
    rows = []
    for _label, efficiency, stoichiometry, count in POPULATIONS:
        photons = rng.gamma(shape=4.0, scale=35.0, size=count) + 30.0
        e = np.clip(rng.normal(efficiency, 0.06, count), -0.05, 1.05)
        s = np.clip(rng.normal(stoichiometry, 0.05, count), -0.05, 1.05)
        tau = np.clip(4.0 * (1.0 - e) + rng.normal(0.0, 0.2, count), 0.1, 4.5)
        duration = rng.gamma(shape=3.0, scale=0.5, size=count)
        rows.append(np.column_stack([e, s, photons, duration, tau]))
    table = np.vstack(rows)
    table = table[rng.permutation(len(table))]
    header = "FRET Efficiency,Stoichiometry,Number of Photons,Duration (ms),Tau (green)"
    np.savetxt(path, table, delimiter=",", header=header, comments="", fmt="%.6g")
    record(folder, [DEMO_NAME], config)
    return path
