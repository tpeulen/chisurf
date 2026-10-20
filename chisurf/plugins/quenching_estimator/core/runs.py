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
    "RUN_FILE",
    "ANALYSIS_KIND",
    "run_kind",
    "new_run_directory",
    "write_analysis_run",
    "read_analysis_run",
    "read_run_table",
    "parse_table_key",
    "analysis_inputs",
    "analyse",
]

#: The file that marks a run's kind and the inputs it was started with. A simulation run
#: has none (its marker is ``project.json``/``result.json``); every other kind writes one.
RUN_FILE = "run.json"

#: The kind of a quenching-analysis run (``core/inference/stages.py``). Its directory holds
#: the declared tables (``<stage>.<table>.csv``), ``summary.json`` and ``report.md`` as
#: :meth:`AnalysisResult.write` writes them, plus :data:`RUN_FILE`.
ANALYSIS_KIND = "analysis"

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
    kind = run_kind(path)

    if kind == ANALYSIS_KIND:
        info = _read_json(path / RUN_FILE)
        stages = info.get("stages") or []
        return {
            "job_id": path.name,
            "kind": kind,
            "labeling_site": "",
            "stages": stages,
            "preset": info.get("preset"),
            "status": info.get("status", ""),
            "date": date_str,
        }
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

    # A simulation summary carries no ``kind``: its shape predates the other kinds and a
    # picker reads ``labeling_site`` from it.
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
    if run_kind(runs_directory(project_dir) / str(job_id)) == ANALYSIS_KIND:
        return read_analysis_run(job_id, project_dir)
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

    prefix = "quest_analysis" if run_kind(job_dir) == ANALYSIS_KIND else "quest_simulation"
    archive_name = f"{prefix}_{job_id}.zip"
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


# -- analysis runs ------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any]:
    """A JSON file as a dict; an unreadable one as ``{}`` (a picker must not fail on it)."""
    try:
        with Path(path).open("r", encoding="utf8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def run_kind(path: Path | str) -> str:
    """The kind of the run in directory *path*: ``analysis`` or ``simulation``.

    Parameters
    ----------
    path : str or pathlib.Path

    Returns
    -------
    str
    """
    marker = Path(path) / RUN_FILE
    if marker.exists():
        return str(_read_json(marker).get("kind") or "simulation")
    return "simulation"


def new_run_directory(project_dir: Optional[Path | str] = None,
                      run_id: Optional[str] = None) -> tuple[str, Path]:
    """Create (or reuse) the directory of a run.

    Parameters
    ----------
    project_dir : str or pathlib.Path, optional
        As :func:`runs_directory`.
    run_id : str, optional
        A UUID (a job id); a new one by default.

    Returns
    -------
    tuple of (str, pathlib.Path)
        The run id and its directory.
    """
    run_id = str(run_id or uuid.uuid4())
    if not is_run_id(run_id):
        raise ValueError(f"Invalid run id (must be a UUID): {run_id!r}")
    folder = runs_directory(project_dir) / run_id
    folder.mkdir(parents=True, exist_ok=True)
    return run_id, folder


def write_analysis_run(result: Any, folder: Path | str, info: dict[str, Any]) -> list[Path]:
    """Write an analysis result into *folder* as an analysis run.

    The tables, ``summary.json`` and ``report.md`` come from ``result.write`` (the declared
    columns of ``settings/analysis/result_columns.yaml``); this adds :data:`RUN_FILE` with
    the kind, *info* (inputs: stages, preset, data folder, ...) and the table file names.

    Parameters
    ----------
    result : AnalysisResult
    folder : str or pathlib.Path
    info : dict
        JSON-able inputs of the run.

    Returns
    -------
    list of pathlib.Path
        Every file written, :data:`RUN_FILE` last.
    """
    folder = Path(folder)
    written = list(result.write(folder))
    record = dict(info)
    record.update(
        kind=ANALYSIS_KIND,
        status="completed",
        stages=list(result.stages),
        tables=sorted(result.tables()),
        files=[p.name for p in written],
        finished=datetime.datetime.now().isoformat(timespec="seconds"),
    )
    path = folder / RUN_FILE
    path.write_text(json.dumps(record, indent=1, default=str), encoding="utf8")
    written.append(path)
    return written


def read_analysis_run(job_id: str, project_dir: Optional[Path | str] = None) -> dict[str, Any]:
    """A stored analysis run: its ``summary.json`` with the run record under ``run``.

    Parameters
    ----------
    job_id : str
    project_dir : str or pathlib.Path, optional

    Returns
    -------
    dict
        ``AnalysisResult.to_dict()`` as written, plus ``run`` (:data:`RUN_FILE`) and
        ``directory``.

    Raises
    ------
    ValueError
        If *job_id* is not a UUID or the run is not an analysis.
    FileNotFoundError
        If there is no such run, or it has no summary yet.
    """
    if not is_run_id(job_id):
        raise ValueError(f"Invalid job id (must be a UUID): {job_id!r}")
    folder = runs_directory(project_dir) / str(job_id)
    if not folder.is_dir():
        raise FileNotFoundError(f"No such run: {job_id}")
    if run_kind(folder) != ANALYSIS_KIND:
        raise ValueError(f"Run {job_id} is not an analysis run")
    summary = folder / "summary.json"
    if not summary.exists():
        raise FileNotFoundError(f"Run {job_id} has no summary yet")
    out = _read_json(summary)
    out["run"] = _read_json(folder / RUN_FILE)
    out["directory"] = str(folder)
    return out


def read_run_table(job_id: str, table: str, project_dir: Optional[Path | str] = None) -> Path:
    """The CSV file of one declared table of a stored analysis run.

    Parameters
    ----------
    job_id : str
    table : str
        ``"<stage>.<table>"`` (for example ``"A.estimates"``).
    project_dir : str or pathlib.Path, optional

    Returns
    -------
    pathlib.Path

    Raises
    ------
    FileNotFoundError
        If the run has no such table.
    """
    record = read_analysis_run(job_id, project_dir)["run"]
    if table not in record.get("tables", []):
        raise FileNotFoundError(
            f"Run {job_id} has no table {table!r}; it has {', '.join(record.get('tables', []))}")
    return runs_directory(project_dir) / str(job_id) / f"{table}.csv"


# -- running an analysis --------------------------------------------------------------------


def parse_table_key(key: Any) -> tuple[str, int, float]:
    """A stored site-table key ``"STATE:site:linker_length"`` as ``(state, site, length)``.

    Parameters
    ----------
    key : str or sequence
        ``"APO:72:20.12"`` or ``("APO", 72, 20.12)``.

    Returns
    -------
    tuple of (str, int, float)
    """
    parts = str(key).split(":") if isinstance(key, str) else list(key)
    if len(parts) != 3:
        raise ValueError(f"site-table key {key!r}: expected 'STATE:site:linker_length'")
    return str(parts[0]), int(parts[1]), float(parts[2])


def analysis_inputs(
    data: Optional[Path | str] = None,
    structures: Optional[dict[str, str]] = None,
    tables: Optional[dict[Any, str]] = None,
    cache_dir: Optional[Path | str] = None,
):
    """Load the measurements and the site models of an analysis.

    Parameters
    ----------
    data : str or pathlib.Path, optional
        Measurement folder (the three CSV files); the shipped MalE set by default.
    structures : dict, optional
        ``{state: structure path}`` for the site tables (the shipped MalE structures).
    tables : dict, optional
        Stored site tables ``{"STATE:site:linker_length": npz path}`` (for example the MalE
        prototype's cache); replaces building them from *structures*.
    cache_dir : str or pathlib.Path, optional
        Site-table cache folder of the default library.

    Returns
    -------
    stages.AnalysisData
    """
    from .inference import stages

    library = None
    if tables:
        library = stages.TableFiles({parse_table_key(k): v for k, v in tables.items()})
    return stages.load_analysis_data(
        folder=None if data is None else Path(data),
        library=library,
        structures=None if not structures else {str(k): Path(v) for k, v in structures.items()},
        cache_dir=None if cache_dir is None else Path(cache_dir),
    )


def analyse(
    stages: Any = "all",
    *,
    data: Optional[Path | str] = None,
    structures: Optional[dict[str, str]] = None,
    tables: Optional[dict[Any, str]] = None,
    cache_dir: Optional[Path | str] = None,
    preset: Optional[str] = None,
    fit_overrides: Optional[dict[str, Any]] = None,
    workers: Optional[int] = None,
    profile: bool = True,
    output: Optional[Path | str] = None,
    project_dir: Optional[Path | str] = None,
    save_outputs: bool = True,
    run_id: Optional[str] = None,
    progress=None,
    cancel=None,
    analysis_data=None,
    analysis=None,
) -> dict[str, Any]:
    """Run the stages of a quenching analysis and store it as an analysis run.

    The one implementation the API, the RPC job and the CLI call. The engine is
    :class:`~.inference.stages.Analysis`; this adds the inputs from plain data and where the
    results go.

    Parameters
    ----------
    stages : str or list of str, optional
        ``"all"`` (the declared order), one stage, or several (:func:`stages.stage_names`).
    data, structures, tables, cache_dir
        As :func:`analysis_inputs`.
    preset : str, optional
        Fit preset (``"full"``, ``"quick"``).
    fit_overrides : dict, optional
        Declared fit settings to replace (``{"n_starts": 4}``).
    workers : int, optional
        Worker processes (1 = in process; the CPU count by default).
    profile : bool, optional
        Compute the declared profile likelihoods.
    output : str or pathlib.Path, optional
        Write the results into this folder. Without it they go to the run directory
        ``<runs>/<run_id>`` (:func:`runs_directory` of *project_dir*).
    project_dir : str or pathlib.Path, optional
    save_outputs : bool, optional
        False writes nothing (the result is only returned).
    run_id : str, optional
        UUID of the run (the job id of an RPC job); a new one by default.
    progress, cancel : callable, optional
        ``progress(percent, message)``, ``cancel() -> bool`` (:class:`.tasks.JobManager`
        shapes); a cancel raises :class:`.tasks.CancelledError` at the next checkpoint.
    analysis_data : stages.AnalysisData, optional
        Already loaded inputs (in process only); *data*/*structures*/*tables*/*cache_dir*
        are then ignored.
    analysis : stages.Analysis, optional
        Continue this analysis (the ``analysis`` of an earlier return): its solved graphs are
        reused, so stage C after stage A costs nothing. Its inputs and fit settings win over
        the arguments here.

    Returns
    -------
    dict
        ``run_id``, ``directory`` (None when nothing was written), ``files`` (names written),
        ``result`` (the native :class:`stages.AnalysisResult`), ``analysis`` (the
        :class:`stages.Analysis`, to continue).
    """
    from .inference import stages as _stages

    info = dict(
        stages=stages, preset=preset, fit_overrides=dict(fit_overrides or {}),
        workers=workers, profile=bool(profile),
        data=None if data is None else str(data),
        structures=dict(structures or {}) or None,
        tables=None if not tables else {str(k): str(v) for k, v in tables.items()},
        cache_dir=None if cache_dir is None else str(cache_dir),
        started=datetime.datetime.now().isoformat(timespec="seconds"),
    )
    if analysis is None:
        if analysis_data is None:
            analysis_data = analysis_inputs(data, structures, tables, cache_dir)
        analysis = _stages.Analysis(analysis_data, preset=preset, fit_overrides=fit_overrides,
                                    workers=workers, profile=profile)
    else:
        info.update(preset=analysis.preset, continued=True)
    result = analysis.run(stages, progress=progress, cancel=cancel)

    run_id = str(run_id or uuid.uuid4())
    folder: Optional[Path] = None
    files: list[str] = []
    if save_outputs:
        if output is not None:
            folder = Path(output)
            folder.mkdir(parents=True, exist_ok=True)
        else:
            run_id, folder = new_run_directory(project_dir, run_id)
        info["run_id"] = run_id
        files = [p.name for p in write_analysis_run(result, folder, info)]
    return {
        "run_id": run_id,
        "directory": None if folder is None else str(folder),
        "files": files,
        "result": result,
        "analysis": analysis,
    }
