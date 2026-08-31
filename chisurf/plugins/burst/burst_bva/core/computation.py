"""BVA computation functions."""

from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Tuple

import numpy as np

from chisurf.core.datastore import (
    column_names,
    concat_stores,
    new_store,
    numeric_column,
    row_count,
    store_from_arrays,
    take_columns,
)

try:
    from chisurf import logging
except ImportError:
    import logging

import tttrlib

# The shot-noise static line has one home: the core burst package. It is
# re-exported here because callers (the GUI tool, the burst-analysis workflow)
# reach for it next to ``compute_bva``.
from chisurf.core.fluorescence.burst.bva import compute_static_bva_line

__all__ = [
    "read_burst_analysis",
    "compute_static_bva_line",
    "compute_bva",
    "write_bv4_analysis",
]


def read_burst_analysis(
        paris_path: pathlib.Path,
        tttr_file_type: str,
        pattern: str = 'b*4*',
        row_stride: int = 2
) -> Tuple[Any, Dict[str, tttrlib.TTTR]]:
    """Read a burst-analysis folder as one table, plus the photon streams it names.

    The burst table and its ``…4`` companions are stacked *row-wise* within a
    directory and put *column-wise* beside each other across directories — the
    positional merge the
    [burst-companion contract](/subsystems/burst-companions.md) describes, which
    is why the row stride matters: a companion carries a zero row between every
    two bursts.

    Parameters
    ----------
    paris_path : pathlib.Path
        The burst-analysis folder holding ``bi4_bur`` and the companions.
    tttr_file_type : str
        Container type for :class:`tttrlib.TTTR`.
    pattern : str
        Which sub-directories to merge.
    row_stride : int
        Take every *n*-th line after the header, dropping the interleaved zero
        rows.

    Returns
    -------
    table : tttrlib.DataStore
        One row per burst.
    tttrs : dict of str to tttrlib.TTTR
        The measurements the ``First File`` column names, opened once each.

    Notes
    -----
    A `.pto` measurement container is read instead of a folder when one is
    passed, through the shared reader. The whole positional merge above — the
    row stride, the column-wise stacking — is bookkeeping for a padded text
    grid, and a container has none of it: the companions are tables joined by
    declared parentage. Without this branch the burst workflow had to write a
    `burst_analysis_handoff/` folder of `.bur` files just so this call had a
    directory, which put the same results in a second place that then went
    stale.
    """
    from chisurf.core.fio.fluorescence.burst_tree import is_container_path

    paris_path = pathlib.Path(paris_path)
    # A run inside a container ('m000.pto/countrate_All 0.2000#60') is a path
    # that does not exist on disk, so `is_file()` answers about the wrong thing.
    if is_container_path(paris_path):
        from chisurf.core.fio.fluorescence.burst import (
            _read_burst_analysis_from_container,
        )

        return _read_burst_analysis_from_container(paris_path)

    data_path = paris_path.parent
    table = new_store()
    for path in sorted(paris_path.glob(pattern)):
        parts = []
        for fn in sorted(path.glob('*')):
            # Skip non-burst sidecars (e.g. a ``bva_settings.json`` written into
            # ``bv4/``) — reading them as a tab table corrupts the merged table.
            if not fn.is_file() or fn.suffix.lower() in {'.json', '.yaml', '.yml'}:
                continue
            parts.append(_read_strided(fn, row_stride))
        if not parts:
            continue
        group = concat_stores(parts)
        if row_count(table) == 0:
            table = group
            continue
        # Column-wise, by position: a companion contributes the columns the
        # burst table does not already have, and a name it shares is the same
        # measurement read twice.
        fresh = [c for c in column_names(group) if c not in column_names(table)]
        table.append_columns(take_columns(group, fresh))

    tttrs: Dict[str, tttrlib.TTTR] = {}
    for ff in np.asarray(table['First File']):
        if ff not in tttrs:
            # ``ff`` is a filename string; coerce defensively so a stray numeric
            # value can't raise ``PosixPath / float`` on the path join.
            tttrs[ff] = tttrlib.TTTR(str(data_path / str(ff)), tttr_file_type)

    return table, tttrs


def _read_strided(path: pathlib.Path, row_stride: int) -> Any:
    """Read one tab-delimited burst file, keeping every *row_stride*-th data row.

    Parameters
    ----------
    path : pathlib.Path
        The file.
    row_stride : int
        Stride over the lines after the header, starting at the first burst row.

    Returns
    -------
    tttrlib.DataStore
        Columns typed from their text: numeric where every entry parses, text
        otherwise.
    """
    lines = path.read_text().splitlines()
    names = lines[0].rstrip('\t').split('\t')
    rows = [line.rstrip('\t').split('\t') for line in lines[2::row_stride]]
    # Padded rather than reshaped: a short line is a truncated file, and a
    # reshape would silently roll its fields into the next burst's row.
    text = np.array(
        [row[:len(names)] + [""] * (len(names) - len(row)) for row in rows], dtype=object
    ).reshape(len(rows), len(names))
    columns = {}
    for i, name in enumerate(names):
        values = text[:, i]
        # Integer first: a photon index is an int64 in the store and stays one,
        # where widening it to float costs the dtype for nothing.
        for dtype in (np.int64, float):
            try:
                columns[name] = values.astype(dtype)
                break
            except (ValueError, OverflowError):
                continue
        else:
            columns[name] = values.astype(str)
    return store_from_arrays(columns)


def _compute_bva_tttrlib(
        table: Any,
        tttrs: Dict[str, tttrlib.TTTR],
        donor_channels,
        donor_micro_time_ranges,
        acceptor_channels,
        acceptor_micro_time_ranges,
        minimum_window_length: float,
        number_of_photons_per_slice: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """Fast path: per-burst proximity-ratio mean/std via the tttrlib C++ BVA
    (parallel over bursts). Returns arrays aligned to ``table`` row order."""
    files = np.asarray(table["First File"])
    firsts = numeric_column(table, "First Photon")
    lasts = numeric_column(table, "Last Photon")

    n = row_count(table)
    means = np.full(n, np.nan)
    stds = np.full(n, np.nan)

    # Group burst rows by their source file, preserving original row indices.
    per_file: Dict[str, Tuple[List[int], List[int]]] = {}
    for i in range(n):
        ff = files[i]
        if ff not in tttrs:
            continue
        rows_idx, bursts = per_file.setdefault(ff, ([], []))
        rows_idx.append(i)
        bursts.append(int(firsts[i]))
        bursts.append(int(lasts[i]))

    to_pairs = lambda rs: [(int(a), int(b)) for a, b in rs]
    for ff, (rows_idx, bursts) in per_file.items():
        bva = tttrlib.BVA(tttrs[ff])
        bva.set_donor(list(donor_channels), to_pairs(donor_micro_time_ranges))
        bva.set_acceptor(list(acceptor_channels), to_pairs(acceptor_micro_time_ranges))
        # tttrlib BVA.compute expects burst boundaries as an (n, 2) [start, stop]
        # array; `bursts` is accumulated as a flat [s0, e0, s1, e1, ...] list.
        burst_pairs = np.asarray(bursts, dtype=np.int64).reshape(-1, 2)
        bva.compute(burst_pairs, int(number_of_photons_per_slice), float(minimum_window_length))
        m = np.asarray(bva.get_proximity_ratio_mean())
        s = np.asarray(bva.get_proximity_ratio_std())
        for k, ri in enumerate(rows_idx):
            means[ri] = m[k]
            stds[ri] = s[k]
    return means, stds


def compute_bva(
        df: Any,
        tttrs: Dict[str, tttrlib.TTTR],
        donor_channels: List[int] = (0, 8),
        donor_micro_time_ranges: List[Tuple[int, int]] = ((0, 4096),),
        acceptor_channels: List[int] = (1, 9),
        acceptor_micro_time_ranges: List[Tuple[int, int]] = ((0, 4096),),
        minimum_window_length: float = 0.01,
        number_of_photons_per_slice: int = -1,
        progress_window=None,
) -> Any:
    """Compute BVA: proximity ratio mean and std per burst.

    Runs on tttrlib's C++ ``BVA`` engine (parallel over bursts). There is no
    second implementation: the in-tree NumPy one was deleted once it was shown
    to agree with this to 3e-16 *after* its off-by-one was corrected -- it
    sliced ``[first:last]`` and so dropped the last photon of every burst.
    """
    if not hasattr(tttrlib, "BVA"):
        raise RuntimeError(
            "BVA needs tttrlib's BVA engine, which this build does not have. "
            "The in-tree NumPy path that used to stand in for it was removed: "
            "it sliced each burst as [first:last], dropping the last photon of "
            "every one, and returned all-zero ratios when the micro-time ranges "
            "were empty. Rebuild tttrlib."
        )
    means, stds = _compute_bva_tttrlib(
        df, tttrs, donor_channels, donor_micro_time_ranges,
        acceptor_channels, acceptor_micro_time_ranges,
        minimum_window_length, number_of_photons_per_slice,
    )
    # Results are addressed by *original* row index: a ``.bur`` table is
    # interleaved (every other row is a sentinel whose ``First File`` names no
    # measurement), so a column shorter than the table would silently shift
    # every result onto the wrong burst.
    df.append_columns(store_from_arrays({
        'Proximity Ratio Mean': means, 'Proximity Ratio Std': stds,
    }))
    if progress_window:
        progress_window.set_value(row_count(df))
    return df


def write_bva_container(
    df: Any,
    *,
    parameters: dict | None = None,
    progress_window=None,
) -> list[str]:
    """Write the BVA result into each measurement's own container.

    One row per burst, joined to the burst table by declared key rather than by
    position, so the `2n+1` grid and the nameless trailing column the `.bv4`
    needed are not reproduced -- they are what the legacy merge counted against,
    and nothing here counts.

    Parameters
    ----------
    df : tttrlib.DataStore
        BVA results, carrying ``First File`` per row.
    parameters : dict, optional
        The analysis settings, which used to be dropped into the companion
        directory as ``bva_settings.json`` and then skipped on purpose by every
        reader of that directory.
    progress_window : optional
        Anything with ``set_value``.

    Returns
    -------
    list of str
        The containers written.
    """
    from chisurf.core.fio.fluorescence.burst_container import as_table, write_per_source

    written = write_per_source(
        take_columns(
            as_table(df),
            ["First File", "Proximity Ratio Mean", "Proximity Ratio Std"],
        ),
        name="bva",
        artifact_kind="burst_table",
        operation_type="burst_variance_analysis",
        row_grain="burst",
        parameters=parameters,
        derived_from="bursts",
    )
    if progress_window:
        progress_window.set_value(len(written))
    logging.info("BVA results written to %d container(s)", len(written))
    return written


def write_bv4_analysis(df: Any, analysis_folder: str = "analysis", progress_window=None):
    """Write BVA results to ``.bv4`` files in a ``bv4/`` subfolder.

    Parameters
    ----------
    df : tttrlib.DataStore
        BVA results, one row per burst, carrying ``First File``.
    analysis_folder : str
        The burst-analysis folder the ``bv4`` directory goes beside.
    progress_window : optional
        Anything with ``set_value``.
    """
    # write_companion owns the layout -- the "…4" directory, the %.6f and the
    # zero interleaving. Building it here, one measurement at a time, is how a
    # companion drifts from the contract that merges it back.
    from chisurf.core.fio.fluorescence.burst_companion import write_companion

    files = np.asarray(df["First File"])
    means = numeric_column(df, "Proximity Ratio Mean")
    stds = numeric_column(df, "Proximity Ratio Std")
    # Name the companion after the .bur stem (``m000.bur`` -> ``m000.bv4``) so
    # per-stem consumers (ndX, the burst browser) join it to the burst table.
    # The historic ``_0`` sub-file suffix broke that stem match.
    for i, tttr_file in enumerate(dict.fromkeys(files), start=1):
        keep = files == tttr_file
        write_companion(
            analysis_folder,
            "bv4",
            pathlib.Path(str(tttr_file)).stem,
            ["Proximity Ratio Mean", "Proximity Ratio Std"],
            np.column_stack([means[keep], stds[keep]]),
        )
        if progress_window:
            progress_window.set_value(i)

    logging.info("BVA results written to %s", pathlib.Path(analysis_folder) / "bv4")
