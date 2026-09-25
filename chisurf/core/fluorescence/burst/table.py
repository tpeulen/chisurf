"""Per-burst tables: reading them.

A burst table is one row per burst and one column per measured quantity, and
every program in the field names those columns differently — ndX's
``Green Count Rate (KHz)``, the Seidel-style ``.bur`` headers, the plain
``i_dd``/``i_da``/``i_aa`` of this API. Which column is which channel is
decided once, by ``tttrlib.guess_burst_columns`` (shared with ndXplorer).

Channel roles follow the convention of
``tttrlib.corrected_es``: ``i_dd`` (donor emission under donor
excitation), ``i_da`` (acceptor emission under donor excitation, the FRET
channel), ``i_aa`` (acceptor emission under acceptor excitation) and ``tau_f``
(the fluorescence-averaged donor lifetime in presence of the acceptor).
"""

from __future__ import annotations

import pathlib

import numpy as np
import tttrlib

from chisurf.core.datastore import column_names

__all__ = [
    "read_burst_table",
    "columns_from_data",
    "maps_fret_channels",
]


def read_burst_table(path: str | pathlib.Path) -> dict[str, np.ndarray]:
    """Read a burst table into ``{column: array}``.

    Any delimited text file (``.csv``, ``.tsv``, ``.txt``, ``.bur``) is read with
    an auto-detected separator; ``.npz`` archives are read directly. Non-numeric
    columns are dropped.

    A **container run** is also a burst table. A burst search over a `.pto` keeps
    its results inside the measurement and writes no ``.bur`` at all, so "the
    burst table" is a path like ``m000.pto/sliding_window_All 0.1500#60`` -- not
    a file on disk, and previously an error from every tool that read a table by
    name while the bursts sat in the file it had just been handed.

    Parameters
    ----------
    path : str or pathlib.Path
        The burst table: a delimited file, an ``.npz``, or a `.pto` run.

    Returns
    -------
    dict
        Numeric columns keyed by their header name.

    Raises
    ------
    ValueError
        If the file holds no numeric column.
    """
    path = pathlib.Path(path)
    if _is_container_run(path):
        return _read_container_run(path)
    if path.suffix.lower() == ".npz":
        with np.load(path) as data:
            return {k: np.asarray(data[k], dtype=float).ravel() for k in data.files}

    columns = _read_delimited(path)
    if not columns:
        raise ValueError(f"no numeric columns found in {path}")
    return columns


def _is_container_run(path: pathlib.Path) -> bool:
    """Whether *path* addresses a burst run inside a `.pto` container."""
    from chisurf.core.fio.fluorescence import burst_tree

    return bool(burst_tree.is_container_path(path))


def _read_container_run(path: pathlib.Path) -> dict[str, np.ndarray]:
    """Read the burst table of a `.pto` run into ``{column: array}``."""
    from chisurf.core.datastore import column_names, numeric_column
    from chisurf.core.fio.fluorescence.burst import read_burst_analysis

    table, _ = read_burst_analysis(path, "PTO")
    columns: dict[str, np.ndarray] = {}
    for name in column_names(table):
        try:
            columns[name] = np.asarray(numeric_column(table, name), dtype=float)
        except Exception:
            continue  # a text column (the measurement names) -- not a channel
    if not columns:
        raise ValueError(f"no numeric columns in {path}")
    return columns


def _sniff_delimiter(path: pathlib.Path) -> str | None:
    """Return the separator of a delimited file, or ``None`` if it is not plain.

    A burst table is one of four separators and a header on the first line. This
    answers by counting candidates in the header rather than by sniffing the
    whole file, and answers ``None`` — rather than guessing — for a file with a
    comment preamble or no clear separator, because those are what the general
    reader is for.

    Parameters
    ----------
    path : pathlib.Path
        File to inspect.

    Returns
    -------
    str or None
    """
    try:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            header = handle.readline()
    except OSError:
        return None
    if not header or header.lstrip().startswith("#"):
        return None
    # Precedence, not a count. Burst-table column names contain spaces --
    # "Duration (ms)", "Mean Macro Time (ms)" -- so on a wide header the spaces
    # outnumber the tabs and "most frequent character wins" picks the space,
    # which parses every row as one field. A real separator, if present, is
    # always the separator.
    for candidate in ("\t", ",", ";"):
        if candidate in header:
            return candidate
    return " " if " " in header else None


def _read_delimited(path: pathlib.Path) -> dict[str, np.ndarray]:
    """Read a delimited burst table into ``{column: float array}``.

    The threaded reader, which handles a plain delimited file with its header on
    the first line. Anything else — a comment preamble, a decimal comma,
    whitespace alignment — reads as **no columns**, and the caller raises. There
    is deliberately no second reader behind this one: a fallback that needs an
    optional package is a path that works on a developer's machine and fails on
    everyone else's.

    Parameters
    ----------
    path : pathlib.Path
        File to read.

    Returns
    -------
    dict
        Numeric columns keyed by their header name.
    """
    from chisurf.core.datastore import (
        BOOL_DTYPE,
        STRING_DTYPE,
        column_values,
        read_csv_table,
    )

    delimiter = _sniff_delimiter(path)
    if delimiter is not None:
        store = read_csv_table(path, delimiter=delimiter)
        if store is not None:
            columns = {}
            for index in range(store.n_columns()):
                column = store[index]
                # A burst table carries text columns -- "First File", "Last
                # File" -- and this returns numeric ones. The reader has already
                # typed them, so a text column is skipped by its dtype rather
                # than by trying to cast it and catching the failure.
                if column.dtype in (STRING_DTYPE, BOOL_DTYPE):
                    continue
                # np.array, not np.asarray: the view keeps the WHOLE store
                # alive, text columns and all, and this returns the numeric ones
                # out of a wide burst table. Copying is what lets the rest go.
                # (Until 2026-08-07 it was also a use-after-free: the array did
                # not hold the store at all, and 84 of 154 rows of "First
                # Photon" read back as 3.3e-319.)
                values = np.array(column_values(store, index), dtype=float).ravel()
                if values.size and np.any(np.isfinite(values)):
                    columns[str(column.name())] = values
            if columns:
                return columns

    return {}


def columns_from_data(data) -> dict[str, np.ndarray]:
    """Extract the numeric columns of an in-memory burst table.

    Works with anything column-addressable — a :class:`pandas.DataFrame`, a plain
    mapping of arrays, or the ``data_source.store`` of a live ndX window —
    so an analysis can run on data already loaded elsewhere instead of on a file
    exported in between.

    Parameters
    ----------
    data : mapping or DataFrame
        The table. Columns that cannot be read as floats are skipped.

    Returns
    -------
    dict
        Numeric columns keyed by their name (empty when there are none).
    """
    if data is None:
        return {}
    columns: dict[str, np.ndarray] = {}
    for name in column_names(data):
        try:
            values = np.asarray(data[name], dtype=float).ravel()
        except Exception:
            continue
        if values.size and np.any(np.isfinite(values)):
            columns[str(name)] = values
    return columns


#: Memo for :func:`maps_fret_channels`, keyed by ``(path, mtime, size)``. A run
#: inside a container is not a file of its own, so the container's stat is what
#: changes when a new search is written into it.
_MAPS_CACHE: dict[tuple, bool] = {}


def maps_fret_channels(path, extra_hints: dict | None = None) -> bool:
    """Whether a burst table carries the columns a FRET analysis needs.

    A burst search run **without detector definitions** writes a table with no
    per-detector split at all — nine columns of burst geometry (`First Photon`,
    `Duration (ms)`, `Number of Photons`, …) and nothing to call I_DD. No
    mapping can recover the channels from it, so a tool handed that run can only
    report that the donor column is unmapped, which reads like a mapping bug
    rather than what it is: the wrong run.

    Use it to *choose* a run rather than to validate one — a container commonly
    holds several searches, and only some of them were run with channels.

    Parameters
    ----------
    path : path-like
        A ``.bur``, a burst folder, or a container run
        (``m000.pto/sliding_window_All 0.1500#60``).
    extra_hints : dict, optional
        Passed through to ``tttrlib.guess_burst_columns``.

    Returns
    -------
    bool
        ``True`` when both ``i_dd`` and ``i_da`` map. ``i_aa`` is not required:
        a two-colour measurement legitimately has none.
    """
    import pathlib as _pathlib

    resolved = _pathlib.Path(str(path))
    stat_target = resolved
    while stat_target != stat_target.parent and not stat_target.exists():
        stat_target = stat_target.parent
    try:
        info = stat_target.stat()
        key = (str(resolved), info.st_mtime_ns, info.st_size)
    except OSError:
        key = (str(resolved), 0, 0)
    if extra_hints:
        key = key + (tuple(sorted(map(str, extra_hints))),)
    cached = _MAPS_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        columns = read_burst_table(resolved)
        names = list(columns)
        mapped = tttrlib.guess_burst_columns(names, extra_hints)
        ok = bool(mapped.get("i_dd")) and bool(mapped.get("i_da"))
    except Exception:
        # Unreadable is not "does not map" -- it is unknown, and refusing a run
        # this cannot open would silently drop the only search there is.
        ok = True
    _MAPS_CACHE[key] = ok
    return ok
