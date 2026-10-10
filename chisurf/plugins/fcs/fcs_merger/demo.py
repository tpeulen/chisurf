"""A small folder of correlation curves the merger tour (and its e2e check) can load."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np


def make_demo(folder: str | Path, n_curves: int = 4) -> Path:
    """Write ``n_curves`` noisy single-diffusion curves as ``*.json.gz`` into *folder*.

    Parameters
    ----------
    folder : str or Path
        Existing directory to fill.
    n_curves : int
        Number of curves; every curve shares one lag-time grid, as the merger requires.

    Returns
    -------
    Path
        *folder*, which the merger's folder field accepts.
    """
    folder = Path(folder)
    rng = np.random.default_rng(7)
    x = np.logspace(-3, 2, 48)
    for index in range(n_curves):
        y = 1.0 + 0.5 / (1.0 + x / 0.5) / np.sqrt(1.0 + x / 5.0) + rng.normal(0, 0.01, x.size)
        curve = {
            "x": x.tolist(),
            "y": y.tolist(),
            "duration": 10.0,
            "count_rate": 50.0,
            "channel_a": {"counts": 5e5},
            "channel_b": {"counts": 5e5},
        }
        with gzip.open(folder / f"demo_{index:02d}.json.gz", "wt", encoding="utf-8") as stream:
            json.dump(curve, stream)
    return folder
