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
    output_dir: str | Path,
) -> tuple[int, str]:
    """Load a TTTR file, compute BIDs, and save as ``.bst``.

    Parameters
    ----------
    path : str or Path
        Input TTTR file.
    time_window_s : float
        Time window duration in seconds.
    output_dir : str or Path
        Output directory for the ``.bst`` file.

    Returns
    -------
    n_windows : int
        Number of time windows produced.
    output_path : str
        Path to the written ``.bst`` file.

    Raises
    ------
    RuntimeError
        If no data or computation fails.
    """
    import tttrlib

    tttr = tttrlib.TTTR(str(path))
    bids = compute_bids_from_tttr(tttr, time_window_s)
    if bids.size == 0:
        raise RuntimeError(f"No windows produced for {path}")
    out = Path(output_dir) / f"{Path(path).stem}.bst"
    save_bst(bids, out)
    return int(len(bids)), str(out.resolve())
