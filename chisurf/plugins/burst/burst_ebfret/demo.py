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

import hashlib
import json
import pathlib
import tempfile
from typing import Any

import numpy as np
from numpy.typing import NDArray

__all__ = ["DEMO", "simulate", "demo_folder", "make_demo"]

#: The ground truth, in one place so the tour, the docs and the tests agree.
DEMO: dict[str, Any] = {
    "version": 1,
    "filename": "simulated-K04-demo-raw-stacked.dat",
    "n_series": 40,
    "min_length": 120,
    "max_length": 220,
    "efret": [0.1, 0.35, 0.55, 0.75],
    "dwell": [40.0, 25.0, 30.0, 50.0],
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
        path: NDArray[np.int64] = np.empty(length, dtype=int)
        path[0] = rng.integers(k)
        for t in range(1, length):
            path[t] = rng.choice(k, p=transition[path[t - 1]])
        acceptor = cfg["total_intensity"] * efret[path] + rng.normal(0.0, cfg["noise"], length)
        donor = cfg["total_intensity"] * (1.0 - efret[path]) + rng.normal(0.0, cfg["noise"], length)
        donors.append(donor)
        acceptors.append(acceptor)
        states.append(path)
    return donors, acceptors, states


def demo_folder() -> pathlib.Path:
    """Return the settings-owned directory for the known donor/acceptor dataset."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "burst_ebfret"


def _cache_is_good(path: pathlib.Path, parameters: dict) -> bool:
    """Require the requested configuration and complete recorded data bytes."""
    try:
        cfg = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        checksum = path.with_suffix(".sha256").read_text(encoding="ascii").split()
        data = path.read_bytes()
        return (
            cfg == parameters
            and len(data) > 4
            and checksum == [str(len(data)), hashlib.sha256(data).hexdigest()]
        )
    except (OSError, ValueError):
        return False


def make_demo(
    folder: pathlib.Path | None = None, *, overwrite: bool = False, seed: int | None = None
) -> pathlib.Path:
    """Write or reuse the deterministic stacked donor/acceptor demonstration.

    Parameters
    ----------
    folder : pathlib.Path, optional
        Dedicated cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Regenerate even when parameters and the file checksum match.
    seed : int, optional
        Explicit simulation seed, recorded in the effective parameter sidecar.

    Returns
    -------
    pathlib.Path
        Primary stacked raw ``.dat`` input, accompanied by its JSON parameters
        and recorded byte-size/SHA-256 checksum.
    """
    parameters = dict(DEMO)
    if seed is not None:
        parameters["seed"] = int(seed)
    folder = demo_folder() if folder is None else pathlib.Path(folder)
    path = folder / parameters["filename"]
    if not overwrite and _cache_is_good(path, parameters):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    donors, acceptors, _states = simulate(parameters["seed"])
    rows = []
    for n, (donor, acceptor) in enumerate(zip(donors, acceptors), start=1):
        rows.append(np.array([[n, n, 0.0]]))
        rows.append(np.column_stack([np.full(donor.size, n), donor, acceptor]))
    # A failed writer must leave a previously complete demonstration available.
    with tempfile.TemporaryDirectory(prefix=".ebfret_", dir=folder) as temporary:
        new = pathlib.Path(temporary) / path.name
        np.savetxt(new, np.vstack(rows), fmt="%15.7e")
        cfg = new.with_suffix(".json")
        cfg.write_text(json.dumps(parameters, sort_keys=True, indent=2), encoding="utf-8")
        data = new.read_bytes()
        checksum = new.with_suffix(".sha256")
        checksum.write_text(f"{len(data)} {hashlib.sha256(data).hexdigest()}\n", encoding="ascii")
        new.replace(path)
        cfg.replace(path.with_suffix(".json"))
        checksum.replace(path.with_suffix(".sha256"))
    return path
