"""Burst results, written into the measurement's own container.

Every burst analysis has the same shape: it takes a burst table, computes
something per burst (or per dwell, or per fused burst), and has to put the
answer somewhere that can be joined back. The legacy answer was a `…4`
directory merged by *counting rows*, which is why six writers grew six copies of
the same interleave and why anything not one-row-per-burst had to live outside
the format entirely.

This is the one place that shape is implemented. A writer says what its rows
*are* and what they came from; the join is a declared key, so a result that is
finer or coarser than the bursts is ordinary rather than impossible. See
[the profile](/specs/pto-mfdb.md).
"""

from __future__ import annotations

import numpy as np

from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "BURST_COLUMN_UNITS",
    "container_for",
    "deinterleave_bursts",
    "open_measurement",
    "units_for",
    "write_burst_artifact",
]

#: Units for burst columns whose **name does not already carry one**.
#:
#: Deliberately short. Most burst columns say their unit in the label —
#: ``Duration (ms)``, ``Count Rate (KHz)`` — and :func:`units_for` reads those
#: through :func:`chisurf.core.units.split_label`, so listing them here as well
#: would be the duplication this exists to remove. What is left is the columns
#: the convention never covered, which are the ones that mattered: a lifetime,
#: and the ratios that have no unit at all.
#:
#: A column named in neither place gets no unit, which means the unit is
#: *unknown* — not dimensionless. Those are different claims and only one is
#: safe to make by default.
BURST_COLUMN_UNITS: dict[str, str] = {
    "Tau": "nanoseconds",
    "Tau (green)": "nanoseconds",
    "Tau (red)": "nanoseconds",
    "Tau (yellow)": "nanoseconds",
    "Lifetime": "nanoseconds",
    "Number of Photons": "photons",
    "Fused Gap Photons": "photons",
    "Fused Bursts": "counts",
    "Fusion Group Size": "counts",
    "Proximity Ratio Mean": "dimensionless",
    "Proximity Ratio Std": "dimensionless",
    "Confidence (sigma)": "dimensionless",
}


def _from_frame(table):
    """Return *table* as a store, converting a frame at the boundary.

    Column by column, so each keeps its own dtype — which is the whole reason
    the store exists — and so no pandas import happens for a caller that
    already handed over a store.
    """
    if not (hasattr(table, "columns") and hasattr(table, "iloc")):
        return table
    from chisurf.core.datastore import store_from_arrays

    return store_from_arrays(
        {str(name): table[name].to_numpy() for name in table.columns}
    )


def units_for(df, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the units of the columns a table actually has.

    Read from the label first — ``Duration (ms)`` and ``Tau | ns`` both say
    their unit, and the vocabulary that resolves those spellings is the
    dictionary's, not a second table kept in step by hand. Only the columns the
    convention never covered are looked up in :data:`BURST_COLUMN_UNITS`.

    Parameters
    ----------
    df : tttrlib.DataStore, pandas.DataFrame or mapping of str to array
    extra : mapping, optional
        Units for columns this analysis names itself, which win over both.

    Returns
    -------
    dict
        ``{column: unit}`` for the columns that have one.
    """
    from chisurf.core.datastore import column_names
    from chisurf.core.units import split_label

    out: dict[str, str] = {}
    for name in column_names(df):
        _, code = split_label(name)
        if not code:
            code = BURST_COLUMN_UNITS.get(name, "")
        if extra and name in extra:
            code = extra[name]
        if code:
            out[name] = code
    return out


def deinterleave_bursts(df):
    """Return the real rows from a table carrying the ``.bur`` interleave.

    The legacy format writes ``2N+1`` physical rows — a zero row, a burst, a
    zero row, … — because it is merged with its companions **by position** and
    needs a fixed grid to count against. That is a property of the file, and it
    has leaked into the in-memory tables the analyses pass around: the blank
    trailing column exists only to produce the trailing tab the header needs.

    Neither belongs in a container, where relations are declared keys rather
    than row positions, so a skipped row is an absent row and a placeholder
    would only destroy the information that it was skipped.

    The layout is documented rather than guessed at — data on odd indices, an
    odd total — and a table that does not look interleaved comes back unchanged,
    so this is safe to call on anything.

    Parameters
    ----------
    df : tttrlib.DataStore, pandas.DataFrame or mapping of str to array
        A results table, interleaved or not.

    Returns
    -------
    tttrlib.DataStore
        One row per result, with any unnamed column dropped.
    """
    from chisurf.core.datastore import (
        column_names,
        numeric_column,
        row_count,
        take_columns,
        take_rows,
    )

    # A frame is converted here rather than deeper down. `as_store` deliberately
    # has no pandas fallback -- the tree is moving off frames and a caller
    # holding one is expected to have moved already -- but this function's
    # contract is to accept whatever an analysis hands it, and several analyses
    # still hand it a frame.
    out = _from_frame(df)
    n = row_count(out)

    if n >= 3 and n % 2 == 1:
        even = np.arange(0, n, 2)
        numeric = [numeric_column(out, name) for name in column_names(out)]
        numeric = [v for v in numeric if np.isfinite(v).any()]
        if numeric and all(np.all(v[even] == 0) for v in numeric):
            out = take_rows(out, np.arange(1, n, 2))

    # Always through take_columns, even when nothing is dropped: it is what
    # converts a caller's frame, and returning the argument unchanged would make
    # the return type depend on whether the table happened to have a blank
    # column.
    return take_columns(out, [c for c in column_names(out) if str(c).strip()])


def container_for(source: str | Path, out_dir: str | Path | None = None) -> Path:
    """Return the container path for an instrument file.

    Parameters
    ----------
    source : str or Path
        The instrument file, or a container path (returned unchanged).
    out_dir : str or Path, optional
        Directory the container lives in. Defaults to beside *source*.

    Returns
    -------
    Path
    """
    src = Path(source)
    if src.suffix == ".pto":
        return src
    return (Path(out_dir) if out_dir is not None else src.parent) / (src.stem + ".pto")


def open_measurement(source: str | Path, out_dir: str | Path | None = None) -> Any:
    """Open the container for *source*, creating it from the instrument file.

    Parameters
    ----------
    source : str or Path
        Instrument file, or an existing container.
    out_dir : str or Path, optional

    Returns
    -------
    chisurf.core.fio.pto.Measurement
        Open for writing. Use as a context manager so it commits.
    """
    from chisurf.core.fio.pto import Measurement, is_measurement

    target = container_for(source, out_dir)
    if is_measurement(target):
        return Measurement.open(target, writable=True)
    return Measurement.create(source, out_dir=out_dir)


def write_burst_artifact(
    source: str | Path,
    df,
    *,
    name: str,
    artifact_kind: str,
    operation_type: str,
    row_grain: str = "burst",
    parameters: Mapping[str, Any] | None = None,
    derived_from: str | Sequence[str] = "bursts",
    source_row_column: str = "",
    target_row_column: str = "",
    units: Mapping[str, str] | None = None,
    out_dir: str | Path | None = None,
) -> str:
    """Write one analysis result into the measurement's container.

    Replaces an earlier run of the same analysis with the same settings rather
    than adding beside it, so a container does not accumulate one object per
    re-run.

    Parameters
    ----------
    source : str or Path
        The instrument file the bursts came from, or the container itself.
    df : tttrlib.DataStore, pandas.DataFrame or mapping of str to array
        The result. Passed through :func:`deinterleave_bursts`, so a table that
        still carries the legacy padding is accepted and the padding is not
        written.
    name : str
        Label for the object.
    artifact_kind : str
        An ``_mmfdb_artifact.artifact_kind`` term.
    operation_type : str
        An ``_mmfdb_operation.operation_type`` term.
    row_grain : str, optional
        An ``_mmfdb_artifact.row_grain`` term — what one row *is*. Defaults to
        ``"burst"``; an analysis producing dwells or fused bursts must say so,
        because that is what makes the join resolvable.
    parameters : mapping, optional
        Settings. Their hash is the identity of the run.
    derived_from : str or sequence of str, optional
        Names of the objects this was computed from. Missing names are skipped,
        so an analysis run against a container that has no burst table yet still
        records what it can. Several is normal: a fused burst has more than one
        parent.
    source_row_column, target_row_column : str, optional
        The columns the parent and this table join on. Supply them whenever the
        grains differ.
    units : mapping, optional
        Units for columns beyond the shared table, merged over
        :data:`BURST_COLUMN_UNITS`. A column with no entry gets no unit, which
        means *unknown* rather than dimensionless.
    out_dir : str or Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    wanted = [derived_from] if isinstance(derived_from, str) else list(derived_from)
    table = deinterleave_bursts(df)
    with open_measurement(source, out_dir) as m:
        parents = []
        for label in wanted:
            uid = m._f.find(label)
            if uid:
                parents.append(uid)
        m.put_table(
            name,
            table,
            artifact_kind=artifact_kind,
            operation_type=operation_type,
            row_grain=row_grain,
            parameters=parameters,
            derived_from=parents or m.instrument_uid,
            source_row_column=source_row_column,
            target_row_column=target_row_column,
            units=units_for(table, units),
        )
        return str(m.path)


def write_per_source(
    df,
    *,
    source_column: str = "First File",
    **kwargs: Any,
) -> list[str]:
    """Split a result by its source file and write each into its own container.

    A burst analysis run over a folder produces one table covering several
    measurements, and one measurement is one container — so the table is split
    on the column naming the file each row came from.

    Parameters
    ----------
    df : tttrlib.DataStore, pandas.DataFrame or mapping of str to array
        The result, carrying *source_column*.
    source_column : str, optional
        Column holding the instrument-file path per row.
    **kwargs
        Forwarded to :func:`write_burst_artifact`.

    Returns
    -------
    list of str
        The containers written, in the order encountered.

    Raises
    ------
    KeyError
        If *source_column* is not in *df*; without it there is no way to know
        which measurement a row belongs to, and guessing would put results in
        the wrong file.
    """
    from chisurf.core.datastore import column_names, take_columns, take_where

    names = column_names(df)
    if source_column not in names:
        raise KeyError(
            f"{source_column!r} is not in the table, so the rows cannot be "
            "attributed to a measurement"
        )
    sources = np.asarray(df[source_column])
    keep = [c for c in names if c != source_column]
    written: list[str] = []
    # dict.fromkeys, not a sort: the groups come back in the order the
    # measurements were read, which is the order a progress bar counts in.
    for path in dict.fromkeys(sources.tolist()):
        group = take_columns(take_where(df, sources == path), keep)
        written.append(write_burst_artifact(str(path), group, **kwargs))
    return written
