"""Per-burst tables: reading them, and recognizing which column is which channel.

A burst table is one row per burst and one column per measured quantity, and
every program in the field names those columns differently — ndX's
``Green Count Rate (KHz)``, the Seidel-style ``.bur`` headers, the plain
``i_dd``/``i_da``/``i_aa`` of this API. Analyses should not each carry their own
guessing rules, so the conventions live here once and both the file readers and
the live ndX bridge use them.

Channel roles follow the convention of
:mod:`chisurf.core.fluorescence.burst.es`: ``i_dd`` (donor emission under donor
excitation), ``i_da`` (acceptor emission under donor excitation, the FRET
channel), ``i_aa`` (acceptor emission under acceptor excitation) and ``tau_f``
(the fluorescence-averaged donor lifetime in presence of the acceptor).
"""

from __future__ import annotations

import pathlib

import numpy as np

__all__ = ["COLUMN_HINTS", "guess_columns", "read_burst_table", "columns_from_data"]

#: Column-name fragments (lower case) identifying each channel role. Matched in
#: order, exact match first, so a more specific name wins over a substring.
COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "i_dd": ("i_dd", "i11", "green count rate", "f_dexc_dem", "sg", "number of photons (green)",
             "ngreen", "n green", "donor donor"),
    "i_da": ("i_da", "i12", "red count rate", "f_dexc_aem", "sr", "number of photons (red)",
             "nred", "n red", "donor acceptor"),
    "i_aa": ("i_aa", "i22", "delayed yellow", "yellow count rate", "f_aexc_aem", "sy",
             "number of photons (yellow)", "nyellow", "n yellow", "acceptor acceptor"),
    "tau_f": ("tau_f", "tau (green)", "taud(a)", "lifetime green", "green lifetime",
              "donor lifetime", "tau green"),
}


def guess_columns(names, extra_hints: dict | None = None) -> dict[str, str]:
    """Map channel roles onto column names by matching known naming conventions.

    Parameters
    ----------
    names : iterable of str
        Column names of the burst table.
    extra_hints : dict, optional
        ``{role: (fragment, …)}`` tried *before* the built-in conventions —
        typically the detector windows of the selected setup, which is how a
        table with site-specific channel names ("det0_green") still maps itself.

    Returns
    -------
    dict
        ``{"i_dd": name, "i_da": name, "i_aa": name, "tau_f": name}``, with the
        roles that could not be matched left out. A column is never assigned to
        two roles.
    """
    out: dict[str, str] = {}
    lowered = [(str(n), str(n).strip().lower()) for n in names]
    for role, hints in COLUMN_HINTS.items():
        hints = tuple((extra_hints or {}).get(role, ())) + tuple(hints)
        for hint in hints:
            match = next((original for original, low in lowered
                          if low == hint or hint in low), None)
            if match is not None and match not in out.values():
                out[role] = match
                break
    return out


def read_burst_table(path: str | pathlib.Path) -> dict[str, np.ndarray]:
    """Read a burst table into ``{column: array}``.

    Any delimited text file (``.csv``, ``.tsv``, ``.txt``, ``.bur``) is read with
    an auto-detected separator; ``.npz`` archives are read directly. Non-numeric
    columns are dropped.

    Parameters
    ----------
    path : str or pathlib.Path
        The burst table.

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
    if path.suffix.lower() == ".npz":
        with np.load(path) as data:
            return {k: np.asarray(data[k], dtype=float).ravel() for k in data.files}

    columns = _read_delimited(path)
    if not columns:
        raise ValueError(f"no numeric columns found in {path}")
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
                # np.array, not np.asarray: column_values hands back a
                # ZERO-COPY VIEW into the store's buffer, and asarray on an
                # already-float64 array returns that same view. The store is
                # local to this function, so the arrays would outlive the memory
                # they point at -- reading back as denormal garbage, not as an
                # error. 84 of 154 rows of "First Photon" came back wrong.
                values = np.array(column_values(store, index), dtype=float).ravel()
                if values.size and np.any(np.isfinite(values)):
                    columns[str(column.name())] = values
            if columns:
                return columns

    return {}


def columns_from_data(data) -> dict[str, np.ndarray]:
    """Extract the numeric columns of an in-memory burst table.

    Works with anything column-addressable — a :class:`pandas.DataFrame`, a plain
    mapping of arrays, or the ``data_source.data`` of a live ndX window —
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
    names = getattr(data, "columns", None)
    if names is None:
        names = data.keys() if hasattr(data, "keys") else []
    columns: dict[str, np.ndarray] = {}
    for name in list(names):
        try:
            values = np.asarray(data[name], dtype=float).ravel()
        except Exception:
            continue
        if values.size and np.any(np.isfinite(values)):
            columns[str(name)] = values
    return columns
