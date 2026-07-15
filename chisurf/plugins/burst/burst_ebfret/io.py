"""Loaders for binned single-molecule FRET traces (ebFRET-compatible formats)."""

from __future__ import annotations

import numpy as np

__all__ = ["load_stacked_dat", "fret_efficiency"]


def fret_efficiency(donor: np.ndarray, acceptor: np.ndarray) -> np.ndarray:
    """Uncorrected proximity ratio ``E = acceptor / (donor + acceptor)``.

    Parameters
    ----------
    donor, acceptor : numpy.ndarray
        Per-frame donor and acceptor intensities.

    Returns
    -------
    numpy.ndarray
        FRET efficiency per frame; frames with zero total intensity yield 0.
    """
    donor = np.asarray(donor, dtype=float)
    acceptor = np.asarray(acceptor, dtype=float)
    total = donor + acceptor
    out = np.zeros_like(total)
    nonzero = total != 0
    out[nonzero] = acceptor[nonzero] / total[nonzero]
    return out


def load_stacked_dat(path: str) -> list[np.ndarray]:
    """Load an ebFRET "stacked" ``.dat`` file into per-molecule FRET traces.

    The stacked layout is a whitespace-delimited ASCII table with three
    columns ``[trace_id, donor, acceptor]`` in which all traces are
    concatenated vertically and grouped by ``trace_id`` (as produced by
    ebFRET's ``load_raw`` for three-column input).

    Parameters
    ----------
    path : str
        Path to the ``.dat`` file.

    Returns
    -------
    list of numpy.ndarray
        One FRET-efficiency trace per unique ``trace_id``, in ascending id
        order.
    """
    raw = np.loadtxt(path)
    if raw.ndim != 2 or raw.shape[1] < 3:
        raise ValueError(f"expected a stacked [id, donor, acceptor] table, got shape {raw.shape}")
    ids = raw[:, 0].astype(int)
    donor = raw[:, 1]
    acceptor = raw[:, 2]
    traces: list[np.ndarray] = []
    for trace_id in np.unique(ids):
        mask = ids == trace_id
        traces.append(fret_efficiency(donor[mask], acceptor[mask]))
    return traces
