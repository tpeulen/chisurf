"""Input/output helpers for the Time Window Bins API."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from .selection import compute_bids_from_tttr

if TYPE_CHECKING:
    import tttrlib


def load_tttr(path: str | Path) -> tttrlib.TTTR:
    """Load a TTTR file using tttrlib.

    Parameters
    ----------
    path : str or Path
        TTTR file path.

    Returns
    -------
    tttrlib.TTTR
        Loaded TTTR object.
    """
    import tttrlib

    return tttrlib.TTTR(str(path))


def save_bst(bids: np.ndarray, path: str | Path) -> None:
    """Save a BID array as a tab-separated ``.bst`` file.

    The legacy exchange format, kept for tools outside ChiSurf that read it;
    ChiSurf's own output is the container (:func:`compute_and_save`).

    Parameters
    ----------
    bids : numpy.ndarray
        Array of shape ``(n_windows, 2)`` with ``[start_idx, stop_idx)``.
    path : str or Path
        Output file path.

    Notes
    -----
    A ``.bst`` row is *first* and *last* photon, both inclusive -- the
    convention every reader (:func:`chisurf.core.fio.fluorescence.burst.generate_burst_dataframe`,
    the .bur "Last Photon" column) assumes. The half-open stop is therefore
    written as ``stop - 1``, and windows holding no photon are dropped because
    an inclusive row cannot express an empty range.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bids = np.asarray(bids, dtype=np.int64).reshape(-1, 2)
    bids = bids[bids[:, 1] > bids[:, 0]]
    rows = np.column_stack([bids[:, 0], bids[:, 1] - 1])
    np.savetxt(str(path), rows, fmt="%d\t%d")


def compute_and_save(
    path: str | Path,
    time_window_s: float,
    output_dir: str | Path | None = None,
) -> tuple[int, str]:
    """Load a TTTR file, compute time-window BIDs, and save them into the ``.pto``.

    The windows are a burst selection of the measurement -- one run in its own
    container, named by the window length, replacing an earlier run with the
    same window on re-computation. Every burst reader in ChiSurf (the burst
    tools, the microtime histogram's burst gates) finds them there; the loose
    ``.bst`` file this used to write is the legacy exchange format
    (:func:`save_bst`), not this tool's output.

    Parameters
    ----------
    path : str or Path
        Input TTTR file (or its container).
    time_window_s : float
        Time window duration in seconds.
    output_dir : str or Path, optional
        Unused for the container (it belongs beside the measurement); kept for
        call compatibility.

    Returns
    -------
    n_windows : int
        Number of time windows produced.
    output_path : str
        Path of the container that now holds the ``time_window`` run.

    Raises
    ------
    RuntimeError
        If no data or computation fails.
    """
    import pandas as pd

    from chisurf.core.fio.analysis_path import bur_artifact_name
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    bids = np.asarray(compute_bids_from_tttr(load_tttr(path), time_window_s))
    if bids.size == 0:
        raise RuntimeError(f"No windows produced for {path}")
    bids = bids.reshape(-1, 2).astype(np.int64)
    nonempty = bids[bids[:, 1] > bids[:, 0]]
    table = pd.DataFrame(
        {
            "first photon": nonempty[:, 0],
            # inclusive last photon, the convention every burst reader assumes
            "last photon": nonempty[:, 1] - 1,
        }
    )
    run = f"time_window {time_window_s * 1000.0:g} ms"
    container = write_burst_artifact(
        path,
        table,
        name=bur_artifact_name(run, Path(path).stem),
        deinterleave=False,
        artifact_kind="burst_table",
        operation_type="burst_selection",
        row_grain="burst",
        algorithm="time_window",
        parameters={"time_window_ms": time_window_s * 1000.0},
        out_dir=output_dir,
    )
    return int(len(nonempty)), str(Path(container).resolve())
