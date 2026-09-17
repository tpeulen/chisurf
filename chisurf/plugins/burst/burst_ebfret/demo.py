"""A simulated donor/acceptor dataset whose answer is known, for the guided tour.

ebFRET ships a simulated dataset (``simulated-K04-N350``); what a first-time
user needs is the same kind of data at a size the analysis finishes on while
they watch. This module simulates it: molecules hop between four FRET levels
with known dwell times, the donor and acceptor intensities split a constant
total by the FRET efficiency of the current state, and Gaussian noise is added
to both channels -- the model ebFRET fits, so the recovered state means can be
compared with :data:`DEMO`.

The file is written in ebFRET's *stacked* raw format (``File > Load``, filter
*Raw donor-acceptor time series*): rows ``[series, donor, acceptor]``, and --
because ``load_raw`` reads the first row of every series as its label -- a
leading label row per series.
"""

from __future__ import annotations

import pathlib
import tempfile

import numpy as np

__all__ = ["DEMO", "simulate", "write_demo"]

#: The ground truth, in one place so the tour, the docs and the tests agree.
DEMO = {
    "n_series": 40,
    "min_length": 120,
    "max_length": 220,
    "efret": (0.1, 0.35, 0.55, 0.75),
    "dwell": (40.0, 25.0, 30.0, 50.0),
    "total_intensity": 400.0,
    "noise": 25.0,
    "seed": 20140301,
}


def simulate(seed: int | None = None, **overrides) -> tuple[list, list, list]:
    """Simulate donor/acceptor traces of a four-state FRET HMM.

    Parameters
    ----------
    seed : int, optional
        Random seed; :data:`DEMO` ``["seed"]`` by default.
    **overrides
        Any :data:`DEMO` key.

    Returns
    -------
    donors, acceptors, states : list of numpy.ndarray
        Intensities and the true state index (0-based) per frame, per series.
    """
    cfg = dict(DEMO, **overrides)
    rng = np.random.default_rng(cfg["seed"] if seed is None else seed)
    efret = np.asarray(cfg["efret"], dtype=float)
    dwell = np.asarray(cfg["dwell"], dtype=float)
    k = efret.size
    stay = np.exp(-1.0 / dwell)
    transition = (1.0 - stay)[:, None] / (k - 1) * (1.0 - np.eye(k)) + np.diag(stay)
    donors, acceptors, states = [], [], []
    for _ in range(int(cfg["n_series"])):
        length = int(rng.integers(cfg["min_length"], cfg["max_length"] + 1))
        path = np.empty(length, dtype=int)
        path[0] = rng.integers(k)
        for t in range(1, length):
            path[t] = rng.choice(k, p=transition[path[t - 1]])
        acceptor = cfg["total_intensity"] * efret[path] + rng.normal(0.0, cfg["noise"], length)
        donor = cfg["total_intensity"] * (1.0 - efret[path]) + rng.normal(0.0, cfg["noise"], length)
        donors.append(donor)
        acceptors.append(acceptor)
        states.append(path)
    return donors, acceptors, states


def write_demo(path: str | pathlib.Path | None = None, seed: int | None = None) -> pathlib.Path:
    """Write the demo as an ebFRET stacked raw ``.dat`` file.

    Parameters
    ----------
    path : str or pathlib.Path, optional
        Output file; a file in the temporary folder by default. Rewritten only
        when missing, since the content is fixed by the seed.
    seed : int, optional
        Random seed.

    Returns
    -------
    pathlib.Path
        The file written.
    """
    if path is None:
        folder = pathlib.Path(tempfile.gettempdir()) / "chisurf_ebfret_demo"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "simulated-K04-demo-raw-stacked.dat"
    path = pathlib.Path(path)
    if path.exists() and seed is None:
        return path
    donors, acceptors, _states = simulate(seed)
    rows = []
    for n, (donor, acceptor) in enumerate(zip(donors, acceptors), start=1):
        rows.append(np.array([[n, n, 0.0]]))
        rows.append(np.column_stack([np.full(donor.size, n), donor, acceptor]))
    np.savetxt(path, np.vstack(rows), fmt="%15.7e")
    return path
