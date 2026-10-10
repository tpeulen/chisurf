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

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

__all__ = [
    "BURST_COLUMN_UNITS",
    "as_table",
    "container_for",
    "deinterleave_bursts",
    "destination_for",
    "open_measurement",
    "resolve_source",
    "units_for",
    "write_burst_artifact",
    "write_per_source",
]

#: Units for burst columns whose **name does not already carry one**.
#:
#: Deliberately short. Most burst columns say their unit in the label —
#: ``Duration (ms)``, ``Count Rate (KHz)`` — and :func:`units_for` reads those
#: through :func:`chisurf.core.support.units.split_label`, so listing them here as well
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
    # A 2CDE value is a score on a fixed scale (~10 for a static burst), not a
    # measurement in anything -- which is `dimensionless`, and is a different
    # claim from the unit being unknown.
    "FRET 2CDE": "dimensionless",
    "ALEX 2CDE": "dimensionless",
}


def as_table(table):
    """Return *table* as a store, converting a frame at the boundary.

    The frame-to-store boundary for analyses that have not moved yet.
    ``datastore.as_store`` deliberately refuses a frame — the tree is migrating
    off them and a caller holding one is expected to have moved — but an
    analysis that pre-selects columns before handing its result over reaches a
    store-only helper first, and needs somewhere to convert.

    Column by column, so each keeps its own dtype, and with no pandas import at
    all for a caller that already handed over a store.

    Parameters
    ----------
    table : tttrlib.DataStore, pandas.DataFrame or mapping of str to array

    Returns
    -------
    tttrlib.DataStore or the argument unchanged
    """
    if not (hasattr(table, "columns") and hasattr(table, "iloc")):
        return table
    from chisurf.core.datastore import store_from_arrays

    return store_from_arrays({str(name): table[name].to_numpy() for name in table.columns})


#: ``Number of Photons (green)`` -> ``Number of Photons``. Only a *trailing*
#: bracket, and only when what is inside it is not itself a unit — by the time
#: this runs :func:`~chisurf.core.support.units.split_label` has already claimed the
#: labels whose bracket is a unit, so anything left is a detector or a window.
_QUALIFIER = re.compile(r"^(?P<name>.*?)\s*[(\[][^)\]]+[)\]]\s*$")


def _unqualified(name: str) -> str:
    """Return *name* without a trailing parenthesised qualifier."""
    match = _QUALIFIER.match(name)
    return match.group("name").strip() if match else name


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
    from chisurf.core.support.units import split_label

    out: dict[str, str] = {}
    for name in column_names(df):
        _, code = split_label(name)
        if not code:
            code = BURST_COLUMN_UNITS.get(name, "")
        if not code:
            # A per-detector column is the same quantity as the one it
            # qualifies, and the table above keys on the exact name — so
            # `Number of Photons` was photons and `Number of Photons (green)`,
            # in the same row, was unitless. The qualifier is dropped and the
            # table asked again, which is also what stops this table needing one
            # row per detector name it has never heard of.
            code = BURST_COLUMN_UNITS.get(_unqualified(name), "")
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
    import tttrlib

    from chisurf.core.datastore import as_store

    # A frame is converted here rather than deeper down. `as_store` deliberately
    # has no pandas fallback -- the tree is moving off frames and a caller
    # holding one is expected to have moved already -- but this function's
    # contract is to accept whatever an analysis hands it, and several analyses
    # still hand it a frame. The layout test and the cut are tttrlib's, shared
    # with ndX's container reader.
    out = tttrlib.deinterleave_burst_rows(as_store(as_table(df)))
    # Always a table of its own: callers add columns to what comes back.
    return out.copy() if out is df else out


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
    from chisurf.core.fio.analysis_path import split_container_path

    src = Path(source)
    if src.suffix == ".pto":
        return src
    inside, _run = split_container_path(src)  # `m.pto/<run>` addresses the container
    if inside is not None:
        return inside
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


def analysis_run(
    source: str | Path,
    kind: str,
    parameters: Mapping[str, Any] | None = None,
    *,
    out_dir: str | Path | None = None,
) -> tuple[str, str]:
    """Name the run an analysis of a burst table is written as, and find its parent.

    MLE, H2MM and burst-wise FCS each compute from one burst search. Written at the
    container's top level they were indistinguishable to a run picker (one
    ``(top level)`` row) and recorded the photon stream, not the burst run, as
    their parent. A run of their own, derived from the burst table they read,
    keeps ``lineage()`` reaching the photons *through* the selection.

    Parameters
    ----------
    source : str or Path
        The container, a run inside it (``m.pto/<run>`` names the burst search
        read), or the instrument file. Without a run the most recent burst
        search of the container is the source.
    kind : str
        What the analysis is (``"mle"``, ``"h2mm"``, ``"burst fcs"``); the run is
        ``"<kind> <settings hash>"``, so a re-run with the same settings
        replaces it and other settings add a run.
    parameters : mapping, optional
        The settings, hashed exactly as :meth:`Measurement.put_table` hashes them.
    out_dir : str or Path, optional

    Returns
    -------
    run : str
        The run name; table names are ``artifact_name(run, table)``.
    parent : str
        Name of the burst table read, or ``""`` when the container has none yet
        (the writer then falls back to the photon stream).
    """
    from chisurf.core.fio.analysis_path import split_artifact_name, split_container_path
    from chisurf.core.fio.pto import Measurement, _tttrlib, is_measurement

    container, source_run = split_container_path(source)
    target = container if container is not None else container_for(source, out_dir)
    digest = str(_tttrlib().pto_settings_hash(dict(parameters) if parameters else None))[:8]
    run = f"{kind} {digest}"
    parent = ""
    if target.exists() and is_measurement(target):
        with Measurement.open(target, writable=False) as m:
            for obj in m.artifacts():
                if m.tag(obj.uid, "_mmfdb_operation.operation_type") != "burst_selection":
                    continue
                name = str(obj.name)
                if not name.endswith(".bur"):
                    continue
                if source_run and split_artifact_name(name)[0] != source_run:
                    continue
                parent = name  # the most recent burst table of the run
    return run, parent


def write_burst_artifact(
    source: str | Path,
    df,
    *,
    name: str,
    artifact_kind: str,
    operation_type: str,
    row_grain: str = "burst",
    algorithm: str = "",
    parameters: Mapping[str, Any] | None = None,
    derived_from: str | Sequence[str] = "bursts",
    source_row_column: str = "",
    target_row_column: str = "",
    units: Mapping[str, str] | None = None,
    out_dir: str | Path | None = None,
    deinterleave: bool = True,
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
    algorithm : str, optional
        An ``_mmfdb_operation.algorithm`` term — which estimator produced this.
        ``operation_type`` is the coarse join key (every per-burst lifetime is
        ``burst_lifetime_fitting``); this is what tells an MLE lifetime from a
        phasor one, which have different bias and must not be pooled.
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
    # The zero rows are file-format padding and a *result* has no use for them
    # -- unless the object being written is the file itself. A container storing
    # `<run>/bi4_bur/<stem>.bur` holds what that file holds, row for row, so
    # unpacking reproduces it and a reader that has always applied the stride
    # keeps applying it. See `chisurf.core.fio.analysis_path`.
    table = deinterleave_bursts(df) if deinterleave else as_table(df)
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
            algorithm=algorithm,
            parameters=parameters,
            # Every photon stream in the container, not just the first: a
            # measurement split over ten vendor files is read as one stream, so
            # a burst table naming only `m000.spc` as its parent leaves nine
            # sources unreachable from the result computed out of them.
            derived_from=parents or m.instrument_uids or m.instrument_uid,
            source_row_column=source_row_column,
            target_row_column=target_row_column,
            units=units_for(table, units),
        )
        return str(m.path)


def resolve_source(name: str | Path, search_from: str | Path | None = None) -> Path:
    """Return the instrument file a burst table's ``First File`` value names.

    A burst table records the file by the name it was found under, which is
    usually relative (``m000.spc``) to the folder the measurements live in, a
    folder or two above the analysis. The container is placed beside the
    instrument file, so a result written against the *relative* name would land
    in whatever the working directory happens to be.

    Parameters
    ----------
    name : str or Path
        The ``First File`` value.
    search_from : str or Path, optional
        Where to start looking; the folder and every parent are tried.

    Returns
    -------
    Path
        The first existing candidate, else *name* unchanged (a writer then
        creates the container where the name says, rather than guessing).
    """
    candidate = Path(str(name))
    if candidate.is_absolute() or search_from is None:
        return candidate
    base = Path(search_from)
    for parent in (base, *base.parents):
        if (parent / candidate).exists():
            return parent / candidate
    return candidate


def destination_for(analysis_folder: str | Path | None) -> tuple[Path | None, Path | None]:
    """Say where a result computed from *analysis_folder* should be written.

    The analysis steps are handed whatever the bursts were read from -- a
    ``.pto`` (or a run inside one) or a legacy burst folder. This is the one
    place that turns that into :func:`write_per_source` arguments.

    Parameters
    ----------
    analysis_folder : str or Path or None

    Returns
    -------
    container : Path or None
        The container that receives every row, when the bursts came from one.
    search_from : Path or None
        The folder relative ``First File`` names are resolved from, otherwise.
    """
    if analysis_folder is None:
        return None, None
    from chisurf.core.fio.analysis_path import split_container_path

    container, _run = split_container_path(analysis_folder)
    if container is not None:
        return container, None
    return None, Path(str(analysis_folder))


def write_per_source(
    df,
    *,
    source_column: str = "First File",
    container: str | Path | None = None,
    search_from: str | Path | None = None,
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
    container : str or Path, optional
        Write every row into this one container instead of splitting. The right
        call when the analysis *was read from* a container: one container is one
        measurement, whatever the ``First File`` values say.
    search_from : str or Path, optional
        Where relative ``First File`` values are resolved from
        (see :func:`resolve_source`).
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

    # Converted here, at the entry point, rather than in `deinterleave_bursts`
    # further down: the split below reaches for `take_where` first, and the
    # store-only helpers refuse a frame.
    df = as_table(df)
    names = column_names(df)
    if source_column not in names:
        raise KeyError(
            f"{source_column!r} is not in the table, so the rows cannot be "
            "attributed to a measurement"
        )
    keep = [c for c in names if c != source_column]
    if container is not None:
        return [write_burst_artifact(str(container), take_columns(df, keep), **kwargs)]
    sources = np.asarray(df[source_column])
    written: list[str] = []
    # dict.fromkeys, not a sort: the groups come back in the order the
    # measurements were read, which is the order a progress bar counts in.
    for path in dict.fromkeys(sources.tolist()):
        group = take_columns(take_where(df, sources == path), keep)
        target = resolve_source(str(path), search_from)
        written.append(write_burst_artifact(str(target), group, **kwargs))
    return written
