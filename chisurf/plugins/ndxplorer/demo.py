"""A small burst table with a *known* answer, so the tour can be walked without your own data.

Five populations are simulated: a low-, a mid- and a high-FRET species at stoichiometry near 0.5, a
donor-only and an acceptor-only population at the stoichiometry extremes. The donor lifetime follows
``tau = 4 ns * (1 - E)``, so on the lifetime-vs-FRET map ndX opens by default the populations lie along the
static FRET line; the simulated parameters are in :data:`POPULATIONS`.
"""

from __future__ import annotations

from pathlib import Path

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


def make_demo(folder, seed: int = 7) -> Path:
    """Write the demo burst table into *folder* and return its path.

    Parameters
    ----------
    folder : str or pathlib.Path
        Existing folder to write into.
    seed : int, optional
        Seed of the simulation, so the table is the same every time.

    Returns
    -------
    pathlib.Path
        The CSV file, one row per burst.
    """
    rng = np.random.default_rng(seed)
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
    path = Path(folder) / DEMO_NAME
    header = "FRET Efficiency,Stoichiometry,Number of Photons,Duration (ms),Tau (green)"
    np.savetxt(path, table, delimiter=",", header=header, comments="", fmt="%.6g")
    return path
