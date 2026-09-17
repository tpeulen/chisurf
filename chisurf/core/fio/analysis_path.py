"""A `.pto` is addressed like a folder, by anything that takes a folder.

Every analysis in ChiSurf has the same shape on disk: a *directory* whose name
encodes the parameters (``countrate_All 0.2000#60``), holding the result tables
as tab-separated text. Re-run with a different setting and you get another
directory beside it, and a downstream tool takes a path to the one you want.

A container holds the same thing without the directories, and holds *several of
them* — re-running with a changed setting adds an object rather than replacing
one. That is the point of the format, and it left every reader with the same
problem: no way to say *which* analysis it meant.

So this module is the one place that knows how a container is addressed, and it
is deliberately **not** about bursts. A path is a path::

    m000.pto                                 the most recent analysis in it
    m000.pto/countrate_All 0.2000#60         that one
    m000.pto/countrate_All 0.2000#60/bi4_bur   the same (a folder-ism, ignored)
    /data/countrate_All 0.2000#60            an ordinary folder, unchanged

A caller asks :func:`read_tables` for what is at a path and gets tables back,
whichever of the two it was; :func:`write_tables` puts them at a path, into the
container or as text, the same way. Nothing above this has to sniff for a
suffix, and an analysis that has never heard of `.pto` gets container support by
going through here.

Inside the container the tables are stored as **binary columns** — that is what
makes opening one cheap, and what a growing file of many analyses needs.
:func:`export_tree` writes them back out as text, because text is for leaving:
unpacking a container gives the instrument files *and* the analysis folders a
session working in folders would have had.
"""

from __future__ import annotations

import pathlib
from typing import Any

__all__ = [
    "SUFFIX",
    "is_container_path",
    "split_container_path",
    "artifact_name",
    "bur_artifact_name",
    "BUR_DIR",
    "split_artifact_name",
    "list_runs",
    "read_tables",
    "write_tables",
    "export_tree",
]

#: ChiSurf's measurement container.
SUFFIX = ".pto"

#: Separates a run's name from the table inside it, in an artifact's name.
#:
#: A forward slash, because the whole point is that the name reads as a path;
#: the container itself imposes nothing on a name.
SEPARATOR = "/"

#: Path components that exist only because the folder layout needs a directory
#: to put files in. A path copied from a folder analysis still resolves.
_FOLDER_ISMS = frozenset({"bi4_bur", "bur"})


def is_container_path(path) -> bool:
    """Return whether *path* names a container, or something inside one.

    Cheap: a walk up the path's components looking for the suffix, never a
    parse and never a stat — a run inside a container is not a file on disk, so
    asking the filesystem answers about the wrong thing.

    Parameters
    ----------
    path : str or pathlib.Path

    Returns
    -------
    bool

    Examples
    --------
    >>> is_container_path("m000.pto")
    True
    >>> is_container_path("m000.pto/countrate_All 0.2000#60")
    True
    >>> is_container_path("countrate_All 0.2000#60")
    False
    """
    return split_container_path(path)[0] is not None


def split_container_path(path) -> tuple[pathlib.Path | None, str]:
    """Split a path into ``(container, run)``.

    Parameters
    ----------
    path : str or pathlib.Path
        A container, a run inside one, or an ordinary filesystem path.

    Returns
    -------
    container : pathlib.Path or None
        The `.pto` file, or ``None`` when *path* does not name one. The file is
        **not** required to exist — resolving a name is not opening it.
    run : str
        The part below the container, or ``""`` for the container itself.

    Examples
    --------
    >>> split_container_path("a/m000.pto")[1]
    ''
    >>> split_container_path("a/m000.pto/run one")[1]
    'run one'
    >>> split_container_path("a/m000.pto/run one/bi4_bur")[1]
    'run one'
    >>> split_container_path("a/folder")[0] is None
    True
    """
    path = pathlib.Path(path)
    parts = list(path.parts)
    for index, part in enumerate(parts):
        if part.lower().endswith(SUFFIX):
            container = pathlib.Path(*parts[: index + 1])
            below = [p for p in parts[index + 1 :] if p not in _FOLDER_ISMS]
            return container, SEPARATOR.join(below)
    return None, ""


def artifact_name(run: str, table: str) -> str:
    """Return the name a run's table is stored under inside a container.

    Parameters
    ----------
    run : str
        The run's name — the same string the folder layout uses for its
        directory. Empty stores the table at the top level, which is what a
        container written before runs were named looks like.
    table : str
        Which table of the run (``"bursts"``, ``"bva"``, ``"2cde"``), so a
        container reads like the folder it replaces.

    Returns
    -------
    str

    Examples
    --------
    >>> artifact_name("countrate_All 0.2000#60", "bursts")
    'countrate_All 0.2000#60/bursts'
    >>> artifact_name("", "bva")
    'bva'
    """
    return f"{run}{SEPARATOR}{table}" if run else table


#: The directory a burst table lives in, inside a run. Kept because the
#: container mirrors the folder tree 1:1 -- an artifact is named exactly as the
#: file would be, so unpacking reproduces the layout and a reader that globs
#: `bi4_bur/*.bur` finds the same thing either side.
BUR_DIR = "bi4_bur"


def bur_artifact_name(run: str, stem: str) -> str:
    """Return the name a measurement's `.bur` is stored under inside a container.

    Parameters
    ----------
    run : str
        The analysis's name — the folder layout's directory name.
    stem : str
        The measurement's stem, as the `.bur` file is named after it.

    Returns
    -------
    str

    Examples
    --------
    >>> bur_artifact_name("countrate_All 0.2000#60", "m000")
    'countrate_All 0.2000#60/bi4_bur/m000.bur'
    >>> bur_artifact_name("", "m000")
    'bi4_bur/m000.bur'
    """
    return artifact_name(run, f"{BUR_DIR}{SEPARATOR}{stem}.bur")


def split_artifact_name(name: str) -> tuple[str, str]:
    """Split an artifact name into ``(run, table)`` — the inverse of the above.

    Parameters
    ----------
    name : str

    Returns
    -------
    tuple of str
        ``("", name)`` for a name with no run in it.

    Examples
    --------
    >>> split_artifact_name("countrate_All 0.2000#60/bursts")
    ('countrate_All 0.2000#60', 'bursts')
    >>> split_artifact_name("bursts")
    ('', 'bursts')
    """
    text = str(name)
    # `<run>/bi4_bur/<stem>.bur` is one table in one run, not a run called
    # `<run>/bi4_bur`: the directory is part of the table's name because the
    # container mirrors the folder tree.
    marker = f"{SEPARATOR}{BUR_DIR}{SEPARATOR}"
    if marker in text:
        run, _, table = text.partition(marker)
        return run, f"{BUR_DIR}{SEPARATOR}{table}"
    if text.startswith(f"{BUR_DIR}{SEPARATOR}"):
        return "", text
    run, separator, table = text.rpartition(SEPARATOR)
    return (run, table) if separator else ("", text)


def list_runs(path, *, operation: str = "") -> list[str]:
    """Return the analyses in a container, oldest first.

    The container's answer to listing a directory: what is in here that a
    downstream step could be pointed at.

    Parameters
    ----------
    path : str or pathlib.Path
        A container, or a run inside one (the run is ignored) — so a caller can
        pass whatever path it has.
    operation : str, optional
        Restrict to one ``_mmfdb_operation.operation_type``, for a caller that
        wants "the burst searches" rather than everything. Empty lists them all,
        which is what a general reader wants.

    Returns
    -------
    list of str
        Run names in write order. ``""`` appears for a table stored without one
        — a container written before runs were named — so that it stays
        addressable rather than becoming invisible.
    """
    from chisurf.core.fio.pto import Measurement

    container, _ = split_container_path(path)
    if container is None or not container.exists():
        return []
    runs: list[str] = []
    with Measurement.open(container, writable=False) as measurement:
        for obj in measurement.artifacts():
            if (
                operation
                and measurement.tag(obj.uid, "_mmfdb_operation.operation_type") != operation
            ):
                continue
            if not measurement.tag(obj.uid, "_mmfdb_operation.operation_type"):
                continue
            run, _table = split_artifact_name(obj.name)
            if run not in runs:
                runs.append(run)
    return runs


def read_tables(path, *, operation: str = "") -> dict[str, Any]:
    """Return the tables at *path*, keyed by table name.

    The general read. A container path resolves to one run's tables; an
    ordinary folder path is not this module's business and raises, because a
    caller that has a folder already has a reader for it — this exists so that
    a *container* needs no new one.

    Parameters
    ----------
    path : str or pathlib.Path
        A container, or one run inside it. Without a run the most recent
        analysis is taken, which is what "open this measurement" should mean.
    operation : str, optional
        Restrict to one operation type when choosing the most recent run.

    Returns
    -------
    dict of str to tttrlib.DataStore
        ``{table name: table}``. Empty only if the run holds nothing.

    Raises
    ------
    FileNotFoundError
        If *path* names no container, or the container holds no analysis, or
        none under the named run — with the available names in the message,
        because "not found" without a listing is the unhelpful half of an error.
    """
    from chisurf.core.fio.pto import Measurement

    container, wanted = split_container_path(path)
    if container is None:
        raise FileNotFoundError(f"{path} does not name a {SUFFIX} container")

    tables: dict[str, Any] = {}
    with Measurement.open(container, writable=False) as measurement:
        candidates = []
        for obj in measurement.artifacts():
            kind = measurement.tag(obj.uid, "_mmfdb_operation.operation_type")
            if not kind or (operation and kind != operation):
                continue
            run, table = split_artifact_name(obj.name)
            candidates.append((run, table, obj))
        if not candidates:
            raise FileNotFoundError(
                f"{container.name} holds no analysis (no burst table, no "
                "results of any kind): run one first, or point this at an "
                "analysis folder if one was written."
            )
        if wanted:
            selected = [c for c in candidates if c[0] == wanted]
            if not selected:
                available = list_runs(container, operation=operation) or ["(none)"]
                raise FileNotFoundError(
                    f"{container.name} holds no analysis named {wanted!r}; "
                    "it holds: " + ", ".join(available)
                )
        else:
            # The most recent, which is the one a panel showing this
            # measurement is showing.
            selected = [c for c in candidates if c[0] == candidates[-1][0]]
        for _run, table, obj in selected:
            try:
                tables[table] = measurement.get_store(obj.uid)
            except Exception:  # noqa: BLE001 - one unreadable table is not all of them
                continue
    return tables


def write_tables(
    path,
    tables: dict[str, Any],
    *,
    source=None,
    parameters: dict | None = None,
    artifact_kind: str = "burst_table",
    operation_type: str = "burst_selection",
    row_grain: str = "burst",
) -> str:
    """Write *tables* to *path*, into a container or as text.

    The general write, and the mirror of :func:`read_tables`: a container path
    stores binary columns beside the photons, an ordinary folder path writes the
    tab-separated files external tools read. A caller states where, not how.

    Parameters
    ----------
    path : str or pathlib.Path
        A container (optionally with a run), or a folder.
    tables : dict of str to table
        ``{table name: table}``.
    source : str or pathlib.Path, optional
        The measurement these came from, when *path* is a folder and the
        container has to be found from the data instead.
    parameters : dict, optional
        The settings behind the run; their hash is its identity.
    artifact_kind, operation_type, row_grain : str
        The mmCIF terms the tables are described with, so an analysis that is
        not a burst search says what it is.

    Returns
    -------
    str
        Where it went.
    """
    from chisurf.core.fio.fluorescence.burst_container import write_burst_artifact

    container, run = split_container_path(path)
    if container is None:
        from chisurf.core.datastore import write_csv_table

        folder = pathlib.Path(path)
        folder.mkdir(parents=True, exist_ok=True)
        for name, table in tables.items():
            write_csv_table(folder / f"{name}.csv", table)
        return str(folder)

    target = str(container)
    for name, table in tables.items():
        target = write_burst_artifact(
            source if source is not None else container,
            table,
            name=artifact_name(run, name),
            artifact_kind=artifact_kind,
            operation_type=operation_type,
            row_grain=row_grain,
            parameters=parameters,
            derived_from=(),
        )
    return target


def export_tree(container, out_dir=None) -> list[pathlib.Path]:
    """Write every analysis in *container* out as a folder of text files.

    What unpacking a container means for its *results*, beside what
    :meth:`~chisurf.core.fio.pto.Measurement.disassemble` does for its
    instrument files. One folder per run, named as the run is named inside —
    which is the name the folder layout would have used, so the two layouts are
    the same thing seen from either side.

    Parameters
    ----------
    container : str or pathlib.Path
    out_dir : str or pathlib.Path, optional
        Defaults to beside the container.

    Returns
    -------
    list of pathlib.Path
        The files written, in run order. Empty when the container holds no
        analysis — the ordinary state of a freshly converted measurement, not a
        problem.
    """
    from chisurf.core.datastore import write_csv_table

    path, _ = split_container_path(container)
    if path is None:
        return []
    target = pathlib.Path(out_dir) if out_dir is not None else path.parent
    written: list[pathlib.Path] = []
    for run in list_runs(path):
        try:
            tables = read_tables(f"{path}/{run}" if run else path)
        except FileNotFoundError:
            continue
        folder = target / (run or path.stem)
        for name, table in tables.items():
            # The name *is* the relative path -- `bi4_bur/m000.bur` comes back
            # out as `bi4_bur/m000.bur`, so unpacking reproduces the folder the
            # container replaced rather than an approximation of it. A table
            # stored under a bare name gets `.csv`, because it had no file.
            relative = pathlib.PurePosixPath(name)
            out = folder / pathlib.Path(*relative.parts)
            if not out.suffix:
                out = out.with_suffix(".csv")
            out.parent.mkdir(parents=True, exist_ok=True)
            write_csv_table(out, table)
            written.append(out)
    return written
