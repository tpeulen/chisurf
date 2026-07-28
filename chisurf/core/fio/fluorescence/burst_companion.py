"""The contract every burst-analysis companion must follow.

A burst-analysis folder is a small database keyed by *burst*: ``bi4_bur/*.bur``
holds one row per burst per measurement, and each analysis writes its results
beside it as a **companion** — ``bv4/m000.bv4`` (BVA), ``2c4/m000.2c4`` (2CDE),
``bg4/m000.bg4`` (burst-wise MLE), ``bh4/m000.bh4`` (H2MM state). A reader opens
the folder by concatenating the ``.bur`` files and merging every companion
**column-wise, by position**, so all of them together read as one table with one
row per burst.

That merge is positional, which is what makes the contract below load-bearing.
Nothing validates it at read time: a companion that gets it wrong does not fail,
it *misaligns*, and burst 900's lifetime is quietly reported against burst 899's
efficiency. Hence one writer, here, rather than each plugin reimplementing the
layout — which is how it stood until this module: six writers, six chances to
drift.

The contract
------------

1. **One file per measurement**, named for the ``.bur`` stem:
   ``<ending>/<stem>.<ending>``. Not one table for the whole folder — a reader
   merges per measurement.
2. **The directory name ends in** ``4``. That is how a folder-level reader
   discovers a companion it has never heard of (ndX's burst reader merges
   any sibling directory whose name ends in ``4``). A companion named anything
   else is written, and silently never read.
3. **One row per burst of that measurement, in burst-table order** — including
   bursts the analysis could not compute. A skipped burst keeps its row with a
   sentinel value; it must never be *omitted*, because that shifts every later
   row against the ``.bur`` grid.
4. **Zero-interleaved rows**: ``2N + 1`` physical rows for ``N`` bursts, data on
   the odd rows. Historical, and load-bearing — readers drop every second row.
5. **Tab-separated, with a trailing tab on the header line.**
6. **Every column numeric**, and named so it does not collide with another
   companion's column: they are merged into one frame, and a duplicate name is
   dropped. Prefix with the analysis (``H2MM State``) or the colour
   (``Tau (green)``).

Use :func:`write_companion` and none of this has to be remembered.
"""

from __future__ import annotations

import pathlib
from collections.abc import Sequence

import numpy as np

__all__ = [
    "CompanionError",
    "companion_path",
    "is_companion_dir",
    "read_companion",
    "write_companion",
]


class CompanionError(ValueError):
    """A companion that would be written wrongly — raised instead of misaligning."""


def is_companion_dir(name: str) -> bool:
    """Whether *name* is discoverable as a companion directory.

    The rule is the reader's: a sibling directory whose name ends in ``4``. The
    burst directories themselves (``bi4_bur``, ``bur``) deliberately do not.

    Parameters
    ----------
    name : str
        Directory name (not a path).

    Returns
    -------
    bool
    """
    return str(name).strip().lower().endswith("4")


def companion_path(analysis_dir, ending: str, stem: str) -> pathlib.Path:
    """Return ``<analysis_dir>/<ending>/<stem>.<ending>``.

    Raises
    ------
    CompanionError
        If *ending* would not be discovered by a folder reader.
    """
    if not is_companion_dir(ending):
        raise CompanionError(
            f"companion directory {ending!r} does not end in '4', so a burst "
            "folder reader will never merge it — see burst_companion's contract"
        )
    return pathlib.Path(analysis_dir) / ending / f"{stem}.{ending}"


def write_companion(
    analysis_dir,
    ending: str,
    stem: str,
    columns: Sequence[str],
    rows,
) -> pathlib.Path:
    """Write one companion file in the layout a burst folder is merged in.

    Parameters
    ----------
    analysis_dir : path-like
        The burst-analysis folder (the one holding ``bi4_bur``).
    ending : str
        Companion directory *and* file extension, e.g. ``"bh4"``. Must end in
        ``4``.
    stem : str
        The measurement stem, matching the ``.bur`` file (``"m000"``).
    columns : sequence of str
        Column names. Must be unique, and should be namespaced so they do not
        collide with another companion's.
    rows : array_like
        Shape ``(n_bursts, len(columns))``, **one row per burst of this
        measurement in burst-table order**, including bursts the analysis
        skipped. Zero-interleaving is applied here — do not pre-interleave.

    Returns
    -------
    pathlib.Path
        The file written.

    Raises
    ------
    CompanionError
        On a non-discoverable *ending*, duplicate column names, or a row/column
        shape mismatch — each of which misaligns silently if written.
    """
    target = companion_path(analysis_dir, ending, stem)
    columns = [str(c) for c in columns]
    if len(set(columns)) != len(columns):
        raise CompanionError(
            f"duplicate column name(s) in {columns} — companions are merged into "
            "one frame and a duplicate is dropped, taking its data with it"
        )
    table = np.asarray(rows, dtype=float)
    if table.ndim != 2 or table.shape[1] != len(columns):
        raise CompanionError(
            f"rows shape {table.shape} does not match {len(columns)} columns"
        )
    if not np.isfinite(table).all():
        # NaN/inf survive the write but poison a positional merge downstream
        # differently per reader; make the sentinel explicit instead.
        table = np.nan_to_num(table, nan=0.0, posinf=0.0, neginf=0.0)

    interleaved = np.zeros((table.shape[0] * 2 + 1, table.shape[1]), dtype=float)
    interleaved[1::2] = table

    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", newline="") as fh:
        fh.write("\t".join(columns) + "\t\n")
        np.savetxt(fh, interleaved, delimiter="\t", fmt="%.6f")
    return target


def read_companion(path):
    """Read a companion back as ``(columns, rows)`` with the padding removed.

    The inverse of :func:`write_companion`, mainly so a test can state the round
    trip rather than re-deriving the layout.

    Parameters
    ----------
    path : path-like

    Returns
    -------
    columns : list of str
    rows : numpy.ndarray
        Shape ``(n_bursts, len(columns))``.
    """
    p = pathlib.Path(path)
    header = p.read_text(encoding="utf-8").splitlines()[0]
    columns = [c for c in header.split("\t") if c.strip()]
    body = np.loadtxt(p, skiprows=1, delimiter="\t", ndmin=2)
    return columns, body[1::2]
