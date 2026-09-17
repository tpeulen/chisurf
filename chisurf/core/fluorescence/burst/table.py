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
import re

import numpy as np

from chisurf.core.datastore import column_names

__all__ = [
    "COLUMN_HINTS",
    "DETECTOR_ROLE_WORDS",
    "gated_stream_columns",
    "guess_columns",
    "read_burst_table",
    "columns_from_data",
    "maps_fret_channels",
]

#: Column-name fragments (lower case) identifying each channel role. Matched in
#: order, exact match first, so a more specific name wins over a substring.
COLUMN_HINTS: dict[str, tuple[str, ...]] = {
    "i_dd": (
        "i_dd",
        "i11",
        "green count rate",
        "f_dexc_dem",
        "sg",
        "number of photons (green)",
        "ngreen",
        "n green",
        "donor donor",
    ),
    "i_da": (
        "i_da",
        "i12",
        "red count rate",
        "f_dexc_aem",
        "sr",
        "number of photons (red)",
        "nred",
        "n red",
        "donor acceptor",
    ),
    "i_aa": (
        "i_aa",
        "i22",
        "delayed yellow",
        "yellow count rate",
        "f_aexc_aem",
        "sy",
        "number of photons (yellow)",
        "nyellow",
        "n yellow",
        "acceptor acceptor",
    ),
    "tau_f": (
        "tau_f",
        "tau (green)",
        "taud(a)",
        "lifetime green",
        "green lifetime",
        "donor lifetime",
        "tau green",
    ),
}


#: Name fragments (lower case) that identify a detector or an excitation window
#: as donor-side or acceptor-side. Used to read the *gated* stream columns of a
#: PIE/ALEX table, where the role is carried by the window and detector names
#: rather than by the column header's own vocabulary.
DETECTOR_ROLE_WORDS: dict[str, tuple[str, ...]] = {
    "donor": ("green", "donor", "prompt", "d"),
    "acceptor": ("red", "acceptor", "delay", "delayed", "yellow", "a"),
}

#: A window x detector column of a burst table, as
#: ``chisurf/core/fio/fluorescence/burst_features.yaml`` declares it:
#: ``S {window} {detector} (photons|kHz) | {r0}-{r1}``.
_GATED_COLUMN = re.compile(
    r"^s\s+(?P<middle>.+?)\s+\((?P<unit>khz|photons)\)\s*\|\s*\d+\s*-\s*\d+$"
)

#: ``Number of Photons ({detector})`` — how the detector names are recovered.
_DETECTOR_COLUMN = re.compile(r"^number of photons \((?P<detector>.+)\)$")


def _role_of(name: str) -> str:
    """Return ``"donor"``, ``"acceptor"`` or ``""`` for a window/detector name."""
    low = str(name).strip().lower()
    for role, words in DETECTOR_ROLE_WORDS.items():
        # Longest word first: "delayed" must win over the bare "d" of the donor
        # list, which any name containing a d would otherwise match.
        for word in sorted(words, key=len, reverse=True):
            if low == word or word in low.split():
                return role
    return ""


def gated_stream_columns(names) -> dict[str, str]:
    """Map the channel roles onto a PIE/ALEX table's *gated* stream columns.

    A burst table from a two-window setup carries both the whole-detector counts
    (``Green Count Rate (KHz)``) and the four window x detector streams
    (``S green green (kHz) | 296-1704``, ...). Only the second set is the ALEX
    channels: ``Green Count Rate`` sums the donor detector over *both*
    excitation periods, so using it as ``I_DD`` folds the acceptor-excitation
    donor signal into the FRET efficiency — an error that shifts E without
    making any histogram look broken.

    Returns
    -------
    dict
        ``{"i_dd": name, "i_da": name, "i_aa": name}`` for the roles that could
        be resolved; empty when the table has no gated columns (a single-window
        measurement, or a foreign table).
    """
    originals = [str(n) for n in names]
    detectors = []
    for name in originals:
        match = _DETECTOR_COLUMN.match(name.strip().lower())
        if match:
            detectors.append(match.group("detector").strip())
    if not detectors:
        return {}

    # Photon counts win over the rate beside them: E and S are ratios of counts,
    # and each rate divides by *its own* stream's span, so the four rates of one
    # burst have four different denominators and their ratios are not the count
    # ratios. A table written before the count columns existed still resolves,
    # on the rates -- see okf/references/known-issues.md.
    gated: dict[tuple[str, str], str] = {}
    rates: dict[tuple[str, str], str] = {}
    for name in originals:
        match = _GATED_COLUMN.match(name.strip().lower())
        if not match:
            continue
        middle = match.group("middle")
        target = gated if match.group("unit") == "photons" else rates
        for detector in detectors:
            if middle == detector or middle.endswith(" " + detector):
                window = middle[: len(middle) - len(detector)].strip()
                if window:
                    target[(window, detector)] = name
                break
    for key, name in rates.items():
        gated.setdefault(key, name)
    if not gated:
        return {}

    def pick(role: str, candidates) -> str:
        for candidate in candidates:
            if _role_of(candidate) == role:
                return candidate
        return ""

    windows = list(dict.fromkeys(window for window, _ in gated))
    w_donor = pick("donor", windows)
    w_acceptor = pick("acceptor", windows)
    d_donor = pick("donor", detectors)
    acceptors = [d for d in detectors if _role_of(d) == "acceptor"]
    d_da = acceptors[0] if acceptors else ""
    # The acceptor-excitation channel prefers a *second* acceptor detector when
    # the setup lists one. That is the Seidel convention -- ``red`` and
    # ``yellow`` are the same physical detector entered twice, once per
    # excitation window -- and each entry carries only its own window's photons.
    # So the cross product still writes an ``S delayed red`` column and it is
    # all zeros; reading I_AA from it puts every burst at S = 1 without any
    # column being missing.
    d_aa = next((d for d in acceptors[1:]), d_da)

    out: dict[str, str] = {}
    for role, key in (
        ("i_dd", (w_donor, d_donor)),
        ("i_da", (w_donor, d_da)),
        ("i_aa", (w_acceptor, d_aa)),
    ):
        if all(key) and key in gated:
            out[role] = gated[key]
    # All or nothing on the FRET pair: half a gated mapping mixed with half an
    # ungated one would put I_DD and I_DA on different photon selections, which
    # is worse than using neither.
    if "i_dd" not in out or "i_da" not in out:
        return {}
    return out


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
    names = list(names)
    # The gated streams win when the table has them: they are the ALEX channels,
    # while the whole-detector columns beside them sum over both excitation
    # periods (see :func:`gated_stream_columns`).
    out: dict[str, str] = gated_stream_columns(names)
    lowered = [(str(n), str(n).strip().lower()) for n in names]
    for role, hints in COLUMN_HINTS.items():
        if role in out:
            continue
        hints = tuple((extra_hints or {}).get(role, ())) + tuple(hints)
        for hint in hints:
            match = next(
                (original for original, low in lowered if low == hint or hint in low), None
            )
            if match is not None and match not in out.values():
                out[role] = match
                break
    return out


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
        Passed through to :func:`guess_columns`.

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
        mapped = guess_columns(names, extra_hints=extra_hints)
        ok = bool(mapped.get("i_dd")) and bool(mapped.get("i_da"))
    except Exception:
        # Unreadable is not "does not map" -- it is unknown, and refusing a run
        # this cannot open would silently drop the only search there is.
        ok = True
    _MAPS_CACHE[key] = ok
    return ok
