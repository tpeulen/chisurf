"""A small .pto container the inspector tour (and its e2e check) can open.

``make_demo()`` writes ``demo.pto`` into the settings cache: a burst table and a (green) lifetime table derived
from it, no instrument file. Nothing here is a measurement.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

FILENAME = "demo.pto"
#: The container, in one place so the guide and the tests agree.
DEMO: dict[str, Any] = {"version": 1, "n_bursts": 32, "title": "Demo container"}


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.plugins.demo_cache import cache_folder

    return cache_folder("pto_inspector")


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Write or reuse ``demo.pto``: a burst table and a lifetime table, no instrument file.

    Parameters
    ----------
    folder : str or Path, optional
        Cache directory; defaults to :func:`demo_folder`.
    overwrite : bool, optional
        Write again even when the stamped parameters and checksum match.

    Returns
    -------
    Path
        The container; the inspector's Open dialog accepts it.
    """
    from chisurf.core.fio.pto import Measurement
    from chisurf.plugins.demo_cache import is_current, record

    folder = demo_folder() if folder is None else Path(folder)
    path = folder / FILENAME
    if not overwrite and path.is_file() and is_current(folder, [FILENAME], DEMO):
        return path
    folder.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    n = int(DEMO["n_bursts"])
    with Measurement.create_empty(path, title=DEMO["title"]) as m:
        bursts = m.put_table(
            "bursts",
            {
                "First Photon": np.arange(n, dtype=np.int64),
                "Number of Photons": np.arange(n, dtype=np.int32) + 60,
                "Duration": np.linspace(0.5, 5.0, n),
            },
            artifact_kind="burst_table",
            operation_type="burst_selection",
            row_grain="burst",
            parameters={"M": 10, "min_photons": 60},
            units={"Duration": "milliseconds"},
        )
        m.put_table(
            # The detector is part of the name: a lifetime result is exported to
            # a per-detector companion (`bg4`/`br4`/`by4`), and the name is how
            # the export knows which one this is.
            "lifetimes green",
            {"First Photon": np.arange(n, dtype=np.int64), "tau": np.linspace(1.0, 4.0, n)},
            artifact_kind="analysis_result",
            operation_type="burst_lifetime_fitting",
            row_grain="burst",
            parameters={"model": "1-exponential"},
            derived_from=bursts,
        )
    record(folder, [FILENAME], DEMO)
    return path
