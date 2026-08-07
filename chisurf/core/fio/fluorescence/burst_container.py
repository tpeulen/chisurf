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

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

__all__ = [
    "container_for",
    "deinterleave_bursts",
    "open_measurement",
    "write_burst_artifact",
]


def deinterleave_bursts(df: pd.DataFrame) -> pd.DataFrame:
    """Return the real rows from a frame carrying the ``.bur`` interleave.

    The legacy format writes ``2N+1`` physical rows — a zero row, a burst, a
    zero row, … — because it is merged with its companions **by position** and
    needs a fixed grid to count against. That is a property of the file, and it
    has leaked into the in-memory frames the analyses pass around: the blank
    trailing column exists only to produce the trailing tab the header needs.

    Neither belongs in a container, where relations are declared keys rather
    than row positions, so a skipped row is an absent row and a placeholder
    would only destroy the information that it was skipped.

    The layout is documented rather than guessed at — data on odd indices, an
    odd total — and a frame that does not look interleaved comes back unchanged,
    so this is safe to call on anything.

    Parameters
    ----------
    df : pandas.DataFrame
        A results table, interleaved or not.

    Returns
    -------
    pandas.DataFrame
        One row per result, with any unnamed column dropped and the index reset.
    """
    out = df
    if len(out) >= 3 and len(out) % 2 == 1:
        numeric = out.select_dtypes(include="number")
        if not numeric.empty and (numeric.iloc[0::2] == 0).all().all():
            out = out.iloc[1::2]
    blank = [c for c in out.columns if not str(c).strip()]
    if blank:
        out = out.drop(columns=blank)
    return out.reset_index(drop=True)


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
    df: pd.DataFrame,
    *,
    name: str,
    artifact_kind: str,
    operation_type: str,
    row_grain: str = "burst",
    parameters: Mapping[str, Any] | None = None,
    derived_from: str | Sequence[str] = "bursts",
    source_row_column: str = "",
    target_row_column: str = "",
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
    df : pandas.DataFrame
        The result. Passed through :func:`deinterleave_bursts`, so a frame that
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
    out_dir : str or Path, optional

    Returns
    -------
    str
        Path of the container written.
    """
    wanted = [derived_from] if isinstance(derived_from, str) else list(derived_from)
    with open_measurement(source, out_dir) as m:
        parents = []
        for label in wanted:
            uid = m._f.find(label)
            if uid:
                parents.append(uid)
        m.put_table(
            name,
            deinterleave_bursts(df),
            artifact_kind=artifact_kind,
            operation_type=operation_type,
            row_grain=row_grain,
            parameters=parameters,
            derived_from=parents or m.instrument_uid,
            source_row_column=source_row_column,
            target_row_column=target_row_column,
        )
        return str(m.path)


def write_per_source(
    df: pd.DataFrame,
    *,
    source_column: str = "First File",
    **kwargs: Any,
) -> list[str]:
    """Split a result by its source file and write each into its own container.

    A burst analysis run over a folder produces one frame covering several
    measurements, and one measurement is one container — so the frame is split
    on the column naming the file each row came from.

    Parameters
    ----------
    df : pandas.DataFrame
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
    if source_column not in df.columns:
        raise KeyError(
            f"{source_column!r} is not in the frame, so the rows cannot be "
            "attributed to a measurement"
        )
    written: list[str] = []
    for path, group in df.groupby(source_column, sort=False):
        written.append(
            write_burst_artifact(str(path), group.drop(columns=[source_column]), **kwargs)
        )
    return written
