"""A small folder of correlation curves the merger tour (and its e2e check) can load.

``make_demo()`` writes four noisy single-diffusion curves as ``demo_NN.json.gz`` into the settings cache,
all on one lag-time grid as the merger requires. Nothing here is a measurement.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

import numpy as np

#: The simulation, in one place so the guide and the tests agree.
DEMO: dict[str, Any] = {
    "version": 1,
    "seed": 7,
    "n_curves": 4,
    "n_lags": 48,
    "lag_ms": [1e-3, 1e2],
    "noise": 0.01,
    "duration_s": 10.0,
    "count_rate_khz": 50.0,
    "counts": 5e5,
}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.plugins.demo_cache import cache_folder

    return cache_folder("fcs_merger")


def _names(n_curves: int) -> list[str]:
    """Return the curve file names."""
    return [f"demo_{index:02d}.json.gz" for index in range(n_curves)]


def make_demo(
    folder: str | Path | None = None, *, overwrite: bool = False, n_curves: int | None = None
) -> Path:
    """Write or reuse the demonstration curves.

    Parameters
    ----------
    folder : str or Path, optional
        Cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Write again even when the stamped parameters and checksums match.
    n_curves : int, optional
        Number of curves instead of ``DEMO["n_curves"]``; every curve shares one lag-time grid.

    Returns
    -------
    Path
        *folder*, which the merger's folder field accepts.
    """
    from chisurf.plugins.demo_cache import is_current, record

    config = {**DEMO, **({} if n_curves is None else {"n_curves": int(n_curves)})}
    folder = demo_folder() if folder is None else Path(folder)
    names = _names(config["n_curves"])
    if not overwrite and all((folder / n).is_file() for n in names) and is_current(folder, names, config):
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(config["seed"])
    lo, hi = config["lag_ms"]
    x = np.logspace(np.log10(lo), np.log10(hi), config["n_lags"])
    for name in names:
        y = 1.0 + 0.5 / (1.0 + x / 0.5) / np.sqrt(1.0 + x / 5.0) + rng.normal(0, config["noise"], x.size)
        curve = {
            "x": x.tolist(),
            "y": y.tolist(),
            "duration": config["duration_s"],
            "count_rate": config["count_rate_khz"],
            "channel_a": {"counts": config["counts"]},
            "channel_b": {"counts": config["counts"]},
        }
        with gzip.open(folder / name, "wt", encoding="utf-8") as stream:
            json.dump(curve, stream)
    record(folder, names, config)
    return folder
