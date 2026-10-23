"""The one explicit export of a measurement container to the legacy burst folder.

A burst analysis lives in the measurement's ``.pto``: one run per analysis, every
result a table joined to the bursts by declared parentage. Older tools -- ndX's
folder reader, the Seidel/Margarita software -- read something else: a folder
holding ``bi4_bur/<stem>.bur`` and, beside it, one ``<ending>4/<stem>.<ending>``
**companion** per analysis, merged onto the burst table *by position*.

This module is the only place that turns the first into the second. No burst
plugin writes a companion any more; they write runs, and this is what "export for
the old software" means. It is deliberately a single, explicit action
(``pto_inspector``'s *Export legacy* button, or ``export-legacy`` on the CLI),
because a companion is a lossy, positional rendering of a result that is
otherwise stated by key.

Alignment is the whole job. The merge is positional and nothing validates it at
read time, so a companion that is one row short does not fail: it shifts every
later burst. Hence:

* every burst of the measurement gets **a row**, including the ones the analysis
  skipped -- a skipped burst is a sentinel row (zeros, as
  :func:`~chisurf.core.fio.fluorescence.burst_companion.write_companion` writes
  non-finite values), never a missing one;
* a table that is not one-row-per-burst (H2MM keeps only the bursts it fitted,
  the burst-FCS correlator only those with a result) is placed by the key its
  artifact declares -- ``source_row_column`` -- or refused with
  :class:`~chisurf.core.fio.fluorescence.burst_companion.CompanionError`;
* an operation with no registered companion ending is never guessed at.
"""

from __future__ import annotations

import logging
import pathlib
import re
from collections.abc import Iterable, Mapping
from typing import Any

import numpy as np

from chisurf.core.fio.fluorescence.burst_companion import CompanionError, write_companion

__all__ = [
    "COMPANIONS",
    "COMPANION_ENDINGS",
    "export_legacy",
    "plan_legacy",
]

logger = logging.getLogger(__name__)

#: ``operation_type`` of a run -> the companion directory/extension its per-burst
#: tables are exported as. A mapping is keyed by the detector in the artifact's
#: name (``mle green`` -> ``bg4``). Every ending ends in ``4``: that is how a
#: folder reader discovers it.
COMPANIONS: dict[str, str | dict[str, str]] = {
    "kde_cde": "2c4",
    "burst_2cde": "2c4",
    "burst_variance_analysis": "bv4",
    "burst_lifetime_fitting": {"green": "bg4", "red": "br4", "yellow": "by4"},
    "photon_hmm": "bh4",
    "burst_correlation": "td4",
    "time_delay": "td4",
    "burst_fusion": "bf4",
}

#: Every ending the export can write.
COMPANION_ENDINGS: tuple[str, ...] = tuple(
    sorted(
        {
            ending
            for value in COMPANIONS.values()
            for ending in (value.values() if isinstance(value, Mapping) else (value,))
        }
    )
)

#: Runs that are burst tables themselves (the ``.bur`` of an analysis), not
#: results computed from one.
_BURST_TABLE_NAMES = frozenset({"bursts", "fused bursts"})

#: Operations that produce the burst table (or something that is not a per-burst
#: result at all) and therefore have no companion.
_NOT_COMPANIONS = frozenset({"burst_selection", "import", "calibration", "background_correction"})

_OPERATION = "_mmfdb_operation.operation_type"
_GRAIN = "_mmfdb_artifact.row_grain"
_SOURCE_KEY = "_mmfdb_edge.source_row_column"


def _is_burst_table(name: str, operation: str) -> bool:
    """Whether the artifact *name* is a burst table rather than a result."""
    from chisurf.core.fio.analysis_path import split_artifact_name

    _run, table = split_artifact_name(name)
    return operation == "burst_selection" or table.endswith(".bur") or table in _BURST_TABLE_NAMES


def _ending_for(operation: str, name: str) -> str:
    """Return the companion ending for an artifact, or raise.

    Raises
    ------
    CompanionError
        For an operation that has no registered ending, or a per-detector
        operation whose detector the name does not give.
    """
    if operation not in COMPANIONS:
        raise CompanionError(
            f"operation {operation!r} has no registered legacy companion "
            f"(known: {', '.join(sorted(COMPANIONS))}); it is not guessed"
        )
    entry = COMPANIONS[operation]
    if isinstance(entry, str):
        return entry
    for detector, ending in entry.items():
        if re.search(rf"\b{re.escape(detector)}\b", name, flags=re.IGNORECASE):
            return ending
    raise CompanionError(
        f"cannot tell which detector {name!r} belongs to (expected one of "
        f"{', '.join(entry)}) so its {operation} companion ending is ambiguous"
    )


def _numeric_columns(table, skip: Iterable[str] = ()) -> dict[str, np.ndarray]:
    """Return the table's numeric columns by name, leaving out *skip* and text."""
    from chisurf.core.datastore import column_names, numeric_column

    skipped = set(skip)
    out: dict[str, np.ndarray] = {}
    for name in column_names(table):
        if name in skipped:
            continue
        try:
            values = np.asarray(numeric_column(table, name), dtype=float)
        except (TypeError, ValueError):
            logger.info("legacy export: column %r is not numeric and is left out", name)
            continue
        out[name] = values
    return out


def _on_grid(
    columns: dict[str, np.ndarray], n_bursts: int, key: np.ndarray | None, label: str
) -> np.ndarray:
    """Return the columns as an ``(n_bursts, n_columns)`` array on the burst grid.

    Parameters
    ----------
    columns : dict of str to numpy.ndarray
        The result's columns, all of one length.
    n_bursts : int
        Rows of the grid: the bursts of the measurement.
    key : numpy.ndarray or None
        For each result row, the burst it belongs to. ``None`` means the rows are
        the bursts, in order.
    label : str
        What to call the artifact in an error.

    Raises
    ------
    CompanionError
        If the rows are neither the whole grid nor placed by a key that lies
        inside it.
    """
    matrix = np.column_stack(list(columns.values())) if columns else np.zeros((0, 0))
    n_rows = matrix.shape[0]
    if key is None:
        if n_rows != n_bursts:
            raise CompanionError(
                f"{label} has {n_rows} rows for {n_bursts} bursts and declares no "
                "row key to place them by: exporting it would shift every burst "
                "after the first mismatch"
            )
        return matrix
    index = np.asarray(key, dtype=float)
    if not np.isfinite(index).all() or (index != np.floor(index)).any():
        raise CompanionError(f"{label}: the row key holds values that are not burst numbers")
    index = index.astype(np.int64)
    if index.size and (index.min() < 0 or index.max() >= n_bursts):
        raise CompanionError(
            f"{label}: row key {int(index.min())}..{int(index.max())} lies outside "
            f"the {n_bursts} bursts of the measurement"
        )
    out = np.zeros((n_bursts, matrix.shape[1]), dtype=float)  # the sentinel row
    out[index] = matrix
    return out


def plan_legacy(container) -> list[dict]:
    """One row per run of *container*: what :func:`export_legacy` writes for it.

    The preview of the export, decided by the same rules the writer applies, so
    it cannot drift: a burst-table run becomes ``bi4_bur/<stem>.bur`` (ending
    ``bur``), a per-burst analysis becomes its registered companion ending
    (detector-keyed operations give every detector's ending joined by ``/``),
    and anything else is skipped (ending ``""``) -- never guessed at.

    Returns
    -------
    list of dict
        ``run`` (display name), ``operation``, ``ending`` (``""`` = skipped).
    """
    from chisurf.core.fio.analysis_path import split_artifact_name, split_container_path
    from chisurf.core.fio.pto import Measurement, is_measurement

    path, _ = split_container_path(container)
    if path is None or not pathlib.Path(path).exists() or not is_measurement(path):
        return []
    rows: list[dict] = []
    with Measurement.open(path, writable=False) as m:
        for obj in m.artifacts():
            operation = str(m.tag(obj.uid, _OPERATION) or "")
            if not operation:
                continue
            name = split_artifact_name(obj.name)[1] or str(obj.name)
            if _is_burst_table(name, operation):
                ending = "bur"
            elif operation in _NOT_COMPANIONS or operation not in COMPANIONS:
                ending = ""
            else:
                mapped = COMPANIONS[operation]
                ending = "/".join(
                    sorted(set(mapped.values())) if isinstance(mapped, Mapping) else (mapped,)
                )
            rows.append({"run": name, "operation": operation, "ending": ending})
    rows.sort(key=lambda r: (r["ending"] == "", r["run"]))
    return rows


def export_legacy(
    container,
    out_dir=None,
    *,
    operations: Iterable[str] | None = None,
) -> list[pathlib.Path]:
    """Write a container out as the Seidel/Margarita burst folder.

    The folder holds, per burst run, ``bi4_bur/<stem>.bur`` (every table in the
    container unpacked by
    :func:`~chisurf.core.fio.analysis_path.export_tree`) and, beside it, one
    companion per analysis ending (``bv4/``, ``2c4/``, ``bg4/``, ``bh4/``, ...)
    with **one row per burst of the measurement, skipped bursts included**.

    Parameters
    ----------
    container : str or pathlib.Path
        The ``.pto``.
    out_dir : str or pathlib.Path, optional
        Where the folder goes; beside the container by default.
    operations : iterable of str, optional
        Export only the per-burst results of these operations, and refuse any
        that has no registered ending. By default every registered operation is
        exported and a per-burst result of an unregistered one is skipped with a
        log line -- it is never guessed at.

    Returns
    -------
    list of pathlib.Path
        The files written: the ``.bur`` tree first, then the companions.

    Raises
    ------
    CompanionError
        On an operation with no registered ending (when named in *operations*),
        or a result whose rows cannot be placed on the burst grid.
    FileNotFoundError
        If *container* is not a ``.pto``.

    Notes
    -----
    When two runs of one analysis write the same column, the **most recent** one
    wins -- the legacy folder holds the current state, and a duplicate column
    name would otherwise be dropped silently by the reader that merges them.
    A zero in a companion is the export sentinel for "skipped"; the container
    still holds the real NaN.
    """
    from chisurf.core.fio.analysis_path import (
        export_tree,
        split_artifact_name,
        split_container_path,
    )
    from chisurf.core.fio.fluorescence.burst_container import deinterleave_bursts
    from chisurf.core.fio.pto import Measurement

    path, _run = split_container_path(container)
    if path is None or not path.exists():
        raise FileNotFoundError(f"{container} is not a .pto container")
    target = pathlib.Path(out_dir) if out_dir is not None else path.parent
    wanted = None if operations is None else list(operations)
    if wanted is not None:
        unknown = [op for op in wanted if op not in COMPANIONS]
        if unknown:
            raise CompanionError(
                f"operation(s) {unknown} have no registered legacy companion "
                f"(known: {', '.join(sorted(COMPANIONS))}); they are not guessed"
            )
    written = list(export_tree(path, target))

    # -- read the catalogue once -----------------------------------------------
    bursts: list[dict[str, Any]] = []  # burst tables, oldest first
    results: list[dict[str, Any]] = []
    with Measurement.open(path, writable=False) as m:
        for obj in m.artifacts():
            operation = str(m.tag(obj.uid, _OPERATION))
            if not operation:
                continue
            name = str(obj.name)
            run, table = split_artifact_name(name)
            entry = {
                "uid": obj.uid,
                "name": name,
                "run": run,
                "table": table,
                "operation": operation,
                "grain": str(m.tag(obj.uid, _GRAIN)),
                "key": str(m.tag(obj.uid, _SOURCE_KEY)),
                "parents": list(m.parents(obj.uid)),
            }
            if _is_burst_table(name, operation):
                entry["store"] = deinterleave_bursts(m.get_store(obj.uid))
                bursts.append(entry)
            elif entry["grain"] == "burst" and operation not in _NOT_COMPANIONS:
                if wanted is not None and operation not in wanted:
                    continue
                if operation not in COMPANIONS:
                    logger.warning(
                        "legacy export: %r (operation %r) has no companion ending; skipped",
                        name,
                        operation,
                    )
                    continue
                entry["store"] = m.get_store(obj.uid)
                results.append(entry)

    # -- place every result on its burst grid ------------------------------------
    from chisurf.core.datastore import row_count

    #: (directory, ending, stem) -> {column: values}; later runs overwrite earlier.
    grouped: dict[tuple[str, str, str], dict[str, np.ndarray]] = {}
    sizes: dict[tuple[str, str, str], int] = {}
    for entry in results:
        ending = _ending_for(entry["operation"], entry["name"])
        store = entry["store"]
        n_rows = row_count(store)
        key_name = entry["key"]
        columns = _numeric_columns(store, skip=[key_name] if key_name else ())
        if not columns:
            continue
        key = None
        if key_name:
            if key_name not in _numeric_columns(store):
                raise CompanionError(
                    f"{entry['name']!r} declares row key {key_name!r}, which its table lacks"
                )
            key = _numeric_columns(store)[key_name]

        # Which burst table is the grid? The parent, then one in the same run,
        # then the latest -- and a run with no burst table of its own (fusion's
        # fused bursts) owns its grid.
        parent_uids = set(entry["parents"])
        same_run = [b for b in bursts if b["run"] == entry["run"]]
        # A result with a burst table among its parents (MLE, H2MM, FCS: runs of their
        # own, derived from the search they read) uses that table as its grid.
        if entry["run"] and not same_run and not any(b["uid"] in parent_uids for b in bursts):
            grid = None
            owns_grid = True
        else:
            owns_grid = False
            ordered = (
                [b for b in bursts if b["uid"] in parent_uids]
                + [b for b in same_run if b["uid"] not in parent_uids]
                + [b for b in reversed(bursts) if b["uid"] not in parent_uids]
            )
            grid = next(
                (b for b in ordered if key is not None or row_count(b["store"]) == n_rows),
                None,
            )
            if grid is None and bursts:
                raise CompanionError(
                    f"{entry['name']!r} has {n_rows} rows but no burst table in the "
                    "container has that many, and it declares no row key to place "
                    "them by"
                )
        if owns_grid:
            n_bursts, out_run, stem = n_rows, entry["run"], path.stem
            matrix = _on_grid(columns, n_bursts, None, entry["name"])
        elif grid is not None:
            n_bursts = row_count(grid["store"])
            out_run = grid["run"] or path.stem
            bur = grid["table"].endswith(".bur")
            stem = pathlib.PurePosixPath(grid["table"]).stem if bur else path.stem
            matrix = _on_grid(columns, n_bursts, key, entry["name"])
        else:
            if key is not None:
                raise CompanionError(
                    f"{entry['name']!r} is placed by {key_name!r} but the container has "
                    "no burst table to say how many bursts there are"
                )
            n_bursts, out_run, stem = n_rows, path.stem, path.stem
            matrix = _on_grid(columns, n_bursts, None, entry["name"])
        slot = (out_run, ending, stem)
        if slot in sizes and sizes[slot] != n_bursts:
            raise CompanionError(
                f"two results exported as {ending}/{stem} disagree on the number of bursts "
                f"({sizes[slot]} vs {n_bursts})"
            )
        sizes[slot] = n_bursts
        merged = grouped.setdefault(slot, {})
        for j, column in enumerate(columns):
            merged[column] = matrix[:, j]

    for (out_run, ending, stem), merged in grouped.items():
        names = list(merged)
        rows = np.column_stack([merged[c] for c in names])
        written.append(write_companion(target / out_run, ending, stem, names, rows))
    return written
