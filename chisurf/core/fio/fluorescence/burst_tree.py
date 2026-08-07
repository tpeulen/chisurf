"""Burst-shaped names for the general container-path scheme.

The scheme itself — a `.pto` addressed like a folder, one run per subtree — is
not about bursts and lives in :mod:`chisurf.core.fio.analysis_path`. This module
is the two burst-specific facts on top of it: what the burst table is called,
and that "the runs" a burst tool wants listed are the burst searches rather than
every analysis in the file.

Everything else is re-exported so the burst callers read naturally.
"""

from __future__ import annotations

from chisurf.core.fio.analysis_path import (
    SEPARATOR,
    SUFFIX,
    artifact_name,
    is_container_path,
    read_tables,
    split_artifact_name,
    split_container_path,
)
from chisurf.core.fio.analysis_path import list_runs as _list_runs

__all__ = [
    "SEPARATOR",
    "SUFFIX",
    "TABLE",
    "OPERATION",
    "is_container_path",
    "split_container_path",
    "split_artifact_name",
    "run_artifact_name",
    "read_tables",
    "list_runs",
]

#: What the burst table is called inside a run.
TABLE = "bursts"

#: The operation that produces it, as opposed to the per-burst results computed
#: from it (a BVA, a 2CDE), which are also at burst grain.
OPERATION = "burst_selection"


def run_artifact_name(run: str, table: str = TABLE) -> str:
    """Return the artifact name a run's burst table is stored under.

    Parameters
    ----------
    run : str
        The run's name — the same string the folder layout uses for its
        directory.
    table : str
        Which table of the run; defaults to the burst table itself.

    Returns
    -------
    str

    Examples
    --------
    >>> run_artifact_name("countrate_All 0.2000#60")
    'countrate_All 0.2000#60/bursts'
    """
    return artifact_name(run, table)


def list_runs(container) -> list[str]:
    """Return the *burst searches* in a container, oldest first.

    Parameters
    ----------
    container : str or pathlib.Path
        A container, or a run inside one (the run is ignored).

    Returns
    -------
    list of str
    """
    return _list_runs(container, operation=OPERATION)
