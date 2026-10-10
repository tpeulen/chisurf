"""A small .pto container the inspector tour (and its e2e check) can open."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def make_demo(folder: str | Path) -> Path:
    """Write ``demo.pto`` into *folder*: a burst table and a lifetime table, no instrument file.

    Parameters
    ----------
    folder : str or Path
        Existing directory to fill.

    Returns
    -------
    Path
        The container; the inspector's Open dialog accepts it.
    """
    from chisurf.core.fio.pto import Measurement

    path = Path(folder) / "demo.pto"
    n = 32
    with Measurement.create_empty(path, title="Demo container") as m:
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
            "lifetimes",
            {"First Photon": np.arange(n, dtype=np.int64), "tau": np.linspace(1.0, 4.0, n)},
            artifact_kind="analysis_result",
            operation_type="burst_lifetime_fitting",
            row_grain="burst",
            parameters={"model": "1-exponential"},
            derived_from=bursts,
        )
    return path
