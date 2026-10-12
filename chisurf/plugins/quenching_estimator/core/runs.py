"""Reading back what a run wrote -- the artefacts, not the running work.

**This module was `quest/jobs.py` until 2026-07-28.** "job" meant two things:
these finished directories on disk, and a *running operation* -- which is what
`jobs` means to a host (`chisurf/server/jobs.py`). A ChiSurf caller asking
`quest.jobs.list` for its running tasks would have been handed directories.
Running work is now :mod:`quest.tasks`, and this is `runs`.

Every simulation writes a ``jobs/<uuid>/`` directory
(see okf/architecture/job-artefacts.md). Listing those runs, summarising them
for a picker, reading one back and packaging one for download are domain
operations -- a notebook or a host application has the same need as the browser
that first grew them.

The directory name is a UUID, which is also the validity check: anything else
in ``jobs/`` is not a run and is ignored rather than half-parsed.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "DEFAULT_RUN_LIST_LIMIT",
    "MAX_RUN_LIST_LIMIT",
    "QUEST_RUNS_DIR_ENV",
    "user_runs_directory",
    "runs_directory",
    "is_run_id",
    "run_summary",
    "list_runs",
    "read_run",
    "archive_run",
    "purge_runs",
]

#: Page size for :func:`list_runs`, and the ceiling a caller can ask for. The
#: picker shows a bounded window; without a cap the response grows without limit
#: as runs accumulate (a development tree here holds several hundred).
DEFAULT_RUN_LIST_LIMIT = 50
MAX_RUN_LIST_LIMIT = 500

#: Overrides the default artefact root. Set it in tests and in bulk work so a
#: run cannot reach the real one.
QUEST_RUNS_DIR_ENV = "QUEST_RUNS_DIR"


def user_runs_directory() -> Path:
    """The per-user artefact root, used when no ``project_dir`` is given.

    **Deliberately not the working directory.** ``simulate_project`` used to
    write ``Path.cwd()/jobs/<uuid>``, so every run started from a checkout left
    a directory behind: 2870 of them, 39 GB, by 2026-07-28. A per-user location
    also makes a run list stable — it no longer depends on where uvicorn or the
    notebook kernel happened to be started.
    """

    override = os.environ.get(QUEST_RUNS_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "quest" / "jobs"


def runs_directory(project_dir: Optional[Path | str] = None) -> Path:
    """Return the artefact directory for *project_dir*.

    With a *project_dir* the runs live under ``<project_dir>/jobs``, which is
    what a caller asking for a specific location means. Without one they go to
    :func:`user_runs_directory` rather than the current directory.
    """

    if project_dir is None:
        return user_runs_directory()
    return Path(project_dir) / "jobs"


def is_run_id(value: Any) -> bool:
    """Whether *value* is a job identifier, i.e. a UUID."""

    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


def run_summary(path: Path) -> dict[str, Any]:
    """Summarise one job directory for a run picker.

    Only the fields a picker shows. The project and the full result live in the
    directory and are read on demand by :func:`read_run`; embedding them here
    made the listing grow without bound.
    """

    date_str = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    project_file = path / "project.json"

    if project_file.exists():
        try:
            with project_file.open("r", encoding="utf8") as handle:
                attachment = json.load(handle).get("attachment") or {}
            labeling_site = f"{attachment.get('chain', '')}:{attachment.get('residue', '')}"
        except Exception:
            labeling_site = "Error loading"
    elif (path / "result.json").exists():
        labeling_site = "Unknown"
    else:
        # A directory with neither is a run that was started and never finished.
        labeling_site = "No result yet"
        date_str = ""

    return {"job_id": path.name, "labeling_site": labeling_site, "date": date_str}


def list_runs(
    project_dir: Optional[Path | str] = None,
    limit: int = DEFAULT_RUN_LIST_LIMIT,
    offset: int = 0,
) -> dict[str, Any]:
    """Return job summaries, newest first, as ``{jobs, total, limit, offset}``.

    Out-of-range paging is clamped rather than rejected: a caller asking for
    10 000 runs gets :data:`MAX_RUN_LIST_LIMIT`, not an error.
    """

    directory = runs_directory(project_dir)
    limit = max(1, min(int(limit), MAX_RUN_LIST_LIMIT))
    offset = max(0, int(offset))

    if not directory.exists():
        return {"runs": [], "total": 0, "limit": limit, "offset": offset}

    candidates: list[tuple[float, Path]] = []
    for path in directory.iterdir():
        if not path.is_dir() or not is_run_id(path.name):
            continue
        try:
            candidates.append((path.stat().st_mtime, path))
        except OSError:
            continue

    candidates.sort(key=lambda item: item[0], reverse=True)
    window = candidates[offset : offset + limit]
    return {
        "runs": [run_summary(path) for _mtime, path in window],
        "total": len(candidates),
        "limit": limit,
        "offset": offset,
    }


def read_run(job_id: str, project_dir: Optional[Path | str] = None) -> dict[str, Any]:
    """Return a finished run's ``result.json``.

    Raises
    ------
    ValueError
        If *job_id* is not a UUID.
    FileNotFoundError
        If there is no such run, or it has no result yet.
    """

    if not is_run_id(job_id):
        raise ValueError(f"Invalid job id (must be a UUID): {job_id!r}")
    result_file = runs_directory(project_dir) / str(job_id) / "result.json"
    if not result_file.exists():
        raise FileNotFoundError(f"No result for job {job_id}")
    with result_file.open("r", encoding="utf8") as handle:
        return json.load(handle)


def archive_run(job_id: str, project_dir: Optional[Path | str] = None) -> Path:
    """Zip a run's artefacts and return the archive path.

    The archive is written inside the job directory and excludes any previous
    archive, so repeated calls do not nest.

    Raises
    ------
    ValueError
        If *job_id* is not a UUID.
    FileNotFoundError
        If there is no such run.
    """

    if not is_run_id(job_id):
        raise ValueError(f"Invalid job id (must be a UUID): {job_id!r}")
    job_dir = runs_directory(project_dir) / str(job_id)
    if not job_dir.is_dir():
        raise FileNotFoundError(f"No such job: {job_id}")

    archive_name = f"quest_simulation_{job_id}.zip"
    archive_path = job_dir / archive_name
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in sorted(job_dir.iterdir()):
            if file_path.is_file() and file_path.name != archive_name:
                archive.write(file_path, file_path.name)
    return archive_path


def purge_runs(
    project_dir: Optional[Path | str] = None,
    *,
    older_than_days: Optional[float] = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Delete run directories, reporting what went (or would go).

    A domain function rather than a shell script so the CLI, a pixi task and a
    host application all drive one implementation
    (okf/architecture/surfaces.md).

    ``dry_run`` defaults to **True**: this deletes, and the caller has to say so.
    Only UUID-named directories are considered, which is the same validity check
    :func:`list_runs` uses -- anything else in the directory was not written by a
    run and is left alone.
    """

    root = runs_directory(project_dir)
    removed: list[str] = []
    freed = 0
    if root.is_dir():
        cutoff = None if older_than_days is None else time.time() - older_than_days * 86400.0
        for entry in sorted(root.iterdir()):
            if not entry.is_dir() or not is_run_id(entry.name):
                continue
            if cutoff is not None and entry.stat().st_mtime >= cutoff:
                continue
            freed += sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
            removed.append(entry.name)
            if not dry_run:
                shutil.rmtree(entry, ignore_errors=True)
    return {
        "directory": str(root),
        "removed": removed,
        "count": len(removed),
        "bytes": freed,
        "dry_run": dry_run,
    }
