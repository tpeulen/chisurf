"""Per-photon state labels an H2MM run left in a burst-analysis folder.

H2MM assigns every analysed photon a Viterbi state. Another analysis that wants
to work *within* those states — fitting one decay per state rather than one per
burst — has to line its own photons up with that assignment, and the obvious
keys do not work: the photon table's ``Burst`` counts only the bursts H2MM kept
(a compacted index, not a row in the burst table), and the concatenated photon
order counts nothing outside H2MM at all.

The key that does work is the photon's position in its measurement's raw TTTR
arrays, written as the ``Photon`` column. This module turns that column into the
form a batch worker can use: one flat array per measurement, indexed by photon,
holding the state (or :data:`UNASSIGNED`).
"""

from __future__ import annotations

import json
import pathlib

import numpy as np

__all__ = [
    "UNASSIGNED",
    "h2mm_output_dir",
    "read_photon_table",
    "state_arrays",
]

#: Photon not assigned to any state — outside a burst, or dropped by H2MM's
#: stream definitions (an acceptor-excitation photon in a two-colour fit).
UNASSIGNED = -1


def h2mm_output_dir(analysis_dir) -> pathlib.Path:
    """Where an H2MM run left its tables under *analysis_dir*.

    The CLI, the RPC service and the GUI write into an ``h2mm/`` subfolder; a
    hand-run export may have written into the folder itself. Both are searched,
    subfolder first — "has H2MM been run" is answered by looking rather than by
    assuming a layout.

    Parameters
    ----------
    analysis_dir : path-like

    Returns
    -------
    pathlib.Path
        The directory holding the tables, or *analysis_dir* when neither
        candidate has any (so a caller raises against a sensible path).
    """
    root = pathlib.Path(analysis_dir)
    marks = ("h2mm_photons.h5", "h2mm_photons.csv", "h2mm_result.json")
    for candidate in (root / "h2mm", root):
        if any((candidate / m).is_file() for m in marks):
            return candidate
    return root


def read_photon_table(analysis_dir) -> dict[str, np.ndarray]:
    """Load H2MM's per-photon table as ``{column: array}``.

    HDF5 for preference and CSV otherwise: which exists depends on the formats
    the run was asked for, so both are tried rather than one assumed.

    Columns rather than a frame because that is all this table is ever used as —
    ``Photon``, ``State`` and ``Source`` are read straight into numpy by
    :func:`state_arrays`, its only caller — and because a per-photon table is
    the biggest one this package handles, so building a frame around it is a
    second copy at the moment it is largest.

    Parameters
    ----------
    analysis_dir : path-like
        The burst-analysis folder (the one holding ``bi4_bur``).

    Returns
    -------
    dict
        Column name to array. Empty when the table has no rows.

    Raises
    ------
    FileNotFoundError
        When neither table is present — H2MM has not run, or ran with photon
        writing switched off.
    """
    from chisurf.core.datastore import column_values, read_csv_table, read_table

    def columns_of(store) -> dict[str, np.ndarray]:
        """Copy a store's columns out.

        ``np.array``, not ``np.asarray``: a column's array is a view into the
        store's buffer, and the store dies with this function.
        """
        return {
            str(store[i].name()): np.array(column_values(store, i))
            for i in range(store.n_columns())
        }

    root = h2mm_output_dir(analysis_dir)
    h5, csv = root / "h2mm_photons.h5", root / "h2mm_photons.csv"
    if h5.is_file():
        store = read_table(h5)
        if store is not None:
            return columns_of(store)
        # A file this cannot read is not a run that did not happen, so fall
        # through to the CSV beside it -- it holds the same table -- rather than
        # reporting either outcome as the other.
    if csv.is_file():
        store = read_csv_table(csv, delimiter=",")
        if store is not None:
            return columns_of(store)
    raise FileNotFoundError(
        f"no H2MM photon table in {root} — run H2MM first (with 'write photons' "
        "on); a state-split fit needs the per-photon state assignment"
    )


def state_arrays(analysis_dir, sizes: dict[str, int]) -> tuple[dict[str, np.ndarray], int]:
    """Return ``{measurement stem: per-photon state array}`` and the state count.

    Parameters
    ----------
    analysis_dir : path-like
        The burst-analysis folder.
    sizes : dict
        ``{stem: number of photons in that measurement's TTTR}``. The arrays are
        built at that length, so a worker indexes them exactly as it indexes the
        routing channels.

    Returns
    -------
    states : dict
        One ``int8`` array per stem, :data:`UNASSIGNED` where H2MM assigned no
        state (outside a burst, or a photon its stream definitions dropped).
    n_states : int
        How many states the run resolved (``0`` when the table is empty).

    Raises
    ------
    FileNotFoundError
        Propagated from :func:`read_photon_table`.
    ValueError
        If the photon table predates the ``Photon`` column — the only key that
        joins it back to the raw arrays.
    """
    table = read_photon_table(analysis_dir)
    if "Photon" not in table:
        raise ValueError(
            "the H2MM photon table has no 'Photon' column, so its states cannot "
            "be matched to the measurement's photons — re-run H2MM"
        )
    out: dict[str, np.ndarray] = {
        stem: np.full(int(size), UNASSIGNED, dtype=np.int8) for stem, size in sizes.items()
    }
    # len() of a mapping is its COLUMN count; the row count is a column's.
    if not len(table["Photon"]):
        return out, 0

    photon = np.asarray(table["Photon"], dtype=np.int64)
    state = np.asarray(table["State"], dtype=np.int64)
    n_states = int(state.max()) + 1

    order = _source_order(analysis_dir, list(sizes))
    if "Source" in table:
        source = np.asarray(table["Source"], dtype=np.int64)
    elif len(sizes) == 1:
        # One measurement: every photon is its own, no disambiguation needed.
        source = np.zeros(photon.size, dtype=np.int64)
    else:
        raise ValueError(
            "the H2MM photon table has no 'Source' column and this folder holds "
            f"{len(sizes)} measurements, so a Photon index is ambiguous — re-run H2MM"
        )

    for i, stem in enumerate(order):
        arr = out.get(stem)
        if arr is None:
            continue
        sel = source == i
        if not sel.any():
            continue
        idx = photon[sel]
        keep = (idx >= 0) & (idx < arr.size)
        arr[idx[keep]] = state[sel][keep].astype(np.int8)
    return out, n_states


def _source_order(analysis_dir, stems: list[str]) -> list[str]:
    """Measurement stems in the order the ``Source`` index counts them.

    Recorded by the H2MM run; falls back to the caller's order, which is right
    for a single measurement and a reasonable guess otherwise.
    """
    p = h2mm_output_dir(analysis_dir) / "h2mm_result.json"
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return list(stems)
    recorded = (payload.get("output_paths") or {}).get("sources")
    if isinstance(recorded, str) and recorded:
        return [pathlib.Path(n).stem for n in recorded.split(",")]
    return list(stems)
