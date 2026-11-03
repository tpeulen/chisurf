"""Each photon dataset's analysis container: its burst runs and every table computed from them.

A burst search of a photon dataset writes into a **measurement container that belongs to the
project** -- never into a file beside the vendor data. While the session runs it is a working file
(:func:`container_dir`); the project carries it embedded as ``project.cs.pto/<name>.pto``
(:func:`project_files`), written by the same writer as any measurement container and so in exactly
the format ndX reads (``ndxplorer.io.pto_reader``): the run's burst table, and each companion (BVA,
2CDE, lifetimes, ...) a table of that run joined to it by its declared parent.

The workspace shows a container's runs as children of their photon dataset. They are derived from
the container (:func:`derived_datasets`) on every restore, never stored as datasets of their own:
the container is the record, and a run row is only a view of it.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

__all__ = [
    "EXTRA_KEY",
    "container_changed",
    "container_dir",
    "on_container_changed",
    "containers",
    "derived_datasets",
    "is_derived",
    "project_files",
    "remove_run",
    "restore",
    "run_dependents",
    "session_dir",
]

#: Where the project records which embedded container belongs to which photon dataset.
EXTRA_KEY = "analysis_containers"

_SESSION: Path | None = None


def session_dir() -> Path:
    """The working folder of this session's analysis containers (private, created once)."""
    global _SESSION
    if _SESSION is None or not _SESSION.is_dir():
        root = (
            Path(os.environ.get("CHISURF_ANALYSIS_DIR") or tempfile.gettempdir())
            / "chisurf-analysis"
        )
        root.mkdir(parents=True, exist_ok=True)
        _SESSION = Path(tempfile.mkdtemp(prefix=f"{os.getpid()}-", dir=root))
        os.chmod(_SESSION, 0o700)
    return _SESSION


def _key(dataset_uid: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(dataset_uid or "")) or "_"


def container_dir(dataset_uid: str) -> Path:
    """The folder the analysis container of the photon dataset *dataset_uid* is written into
    (the writer names the container after the measurement: ``<stem>.pto``)."""
    path = session_dir() / _key(dataset_uid)
    path.mkdir(parents=True, exist_ok=True)
    return path


def containers() -> dict[str, list[Path]]:
    """The analysis containers of this session, by the photon dataset they belong to."""
    out: dict[str, list[Path]] = {}
    root = session_dir()
    for folder in sorted(p for p in root.iterdir() if p.is_dir()):
        found = sorted(folder.glob("*.pto"))
        if found:
            out[folder.name] = found
    return out


def is_derived(address: Any) -> bool:
    """Whether *address* points into an analysis container (a run row: derived, not stored)."""
    try:
        Path(str(address)).resolve().relative_to(session_dir().resolve())
    except (ValueError, OSError):
        return False
    return True


def project_files(taken: set[str]) -> tuple[list, dict[str, list[str]]]:
    """The analysis containers as embedded project objects, and which dataset owns which.

    Returns ``(files, mapping)``: :class:`chisurf.core.project.pto.ProjectFile` entries (named
    ``<stem>.pto``, made unique against *taken*) and ``{dataset_uid: [object names]}`` for the
    project record (:data:`EXTRA_KEY`).
    """
    from .pto import ProjectFile

    files, mapping = [], {}
    for uid, paths in containers().items():
        for path in paths:
            name = path.name
            if name in taken:
                name = f"{path.stem}~{uid[:8]}.pto"
            taken.add(name)
            files.append(
                ProjectFile(name, "measurement", "pto", (), str(path), path.stat().st_size)
            )
            mapping.setdefault(uid, []).append(name)
    return files, mapping


def restore(project_path: Any, mapping: dict[str, list[str]] | None) -> None:
    """Write the embedded analysis containers of *project_path* back to this session's folder."""
    import shutil

    from .links import _extract_object

    # The session now holds this project: the previous project's containers go.
    for folder in [p for p in session_dir().iterdir() if p.is_dir()]:
        shutil.rmtree(folder, ignore_errors=True)
    for uid, names in (mapping or {}).items():
        for name in names:
            stem = Path(name).stem.split("~")[0]
            target = container_dir(uid) / f"{stem}.pto"
            try:
                _extract_object(Path(project_path), name, target)
            except Exception:  # noqa: BLE001 - the rest of the project still opens
                _log.exception("could not restore the analysis container %s", name)


def derived_datasets() -> list:
    """The run rows of the workspace: one per burst run of every analysis container, a child of
    its photon dataset (whose uid names the container's folder)."""
    from chisurf.core.experiments.linked import reader_for_kind
    from chisurf.core.fio.classify import container_entries

    from chisurf.core.fio.analysis_path import run_path, split_container_path

    reader = reader_for_kind("bursts")
    if reader is None:
        return []
    out = []
    for uid, paths in containers().items():
        for path in paths:
            try:
                runs = [a for kind, a in container_entries(path) if kind == "bursts"]
                _uids, needs = _run_graph(path)
            except Exception:  # noqa: BLE001 - an unreadable container shows no runs
                _log.exception("could not list the runs of %s", path)
                continue
            for run in runs:
                dataset = reader.make_dataset(run, result_of="" if uid == "_" else uid)
                dataset.data_reader = reader
                # a run computed from another run (a fusion of a search) is that run's child
                of = sorted(needs.get(split_container_path(run)[1], ()))
                dataset.source_run = run_path(path, of[0]) if of else ""
                out.append(dataset)
    return out


#: Called with the container's path after any write into an analysis container (or a dropped
#: measurement's .pto): the Datasets view, the PTO inspector, Project data.
_LISTENERS: list = []


def on_container_changed(callback) -> None:
    """Call *callback(path)* after every container write (:func:`container_changed`)."""
    if callback not in _LISTENERS:
        _LISTENERS.append(callback)


def container_changed(path: Any = None) -> None:
    """The one notification every container writer sends after it wrote (a burst search, a
    fusion, a companion table, an import, a recording's live run): the runs the analysis
    containers hold that the workspace does not list yet become rows now -- a child of their
    photon dataset -- and the listeners are told. A writer never calls a view itself."""
    try:
        sync_runs()
    except Exception:  # noqa: BLE001 - the write stands; the rows come with the next restore
        _log.exception("listing the new runs of %s failed", path)
    for callback in list(_LISTENERS):
        try:
            callback(path)
        except Exception:  # noqa: BLE001 - one listener never breaks a writer
            _log.exception("a container listener failed")


def sync_runs() -> list:
    """Add every run of the analysis containers that the workspace does not list yet.

    Returns
    -------
    list
        The run datasets that were added.
    """
    if not containers():
        return []
    from chisurf.core.api import dataset_objects
    from chisurf.core.plugin.workspace_input import register_result

    listed = {
        str(getattr(d, "address", "")): str(getattr(d, "unique_identifier", ""))
        for d in dataset_objects()
    }
    added = []
    for run in derived_datasets():  # in write order: a source run is listed before its results
        address = str(getattr(run, "address", ""))
        if address and address not in listed:
            source = str(getattr(run, "source_run", "") or "")
            parent = listed.get(source, "") if source else ""
            if parent:
                run.result_of = parent
            register_result(run, result_of=str(getattr(run, "result_of", "") or ""))
            # the uid the workspace gave it (the session keeps its own copy of what it loads)
            listed[address] = next(
                (
                    str(getattr(d, "unique_identifier", ""))
                    for d in dataset_objects()
                    if str(getattr(d, "address", "")) == address
                ),
                "",
            )
            added.append(run)
    return added



def _run_graph(container: Path) -> tuple[dict[str, list[int]], dict[str, set[str]]]:
    """The runs of *container*: ``{run: [object uids]}`` and ``{run: {runs it is derived from}}``.

    An object belongs to the run its name starts with (``<run>/<table>``); a run depends on another
    when one of its objects names one of the other's as a parent. Objects without an analysis
    operation (the photons themselves) are never part of a run.
    """
    from chisurf.core.fio.analysis_path import split_artifact_name
    from chisurf.core.fio.pto import Measurement

    uids: dict[str, list[int]] = {}
    run_of: dict[int, str] = {}
    with Measurement.open(container, writable=False) as measurement:
        objects = [
            obj
            for obj in measurement.artifacts()
            if measurement.tag(obj.uid, "_mmfdb_operation.operation_type")
        ]
        for obj in objects:
            run = split_artifact_name(obj.name)[0]
            uids.setdefault(run, []).append(int(obj.uid))
            run_of[int(obj.uid)] = run
        parents = {int(obj.uid): measurement.parents(obj.uid) for obj in objects}
    needs: dict[str, set[str]] = {run: set() for run in uids}
    for uid, of in parents.items():
        needs[run_of[uid]].update(run_of[p] for p in of if p in run_of and run_of[p] != run_of[uid])
    return uids, needs


def run_dependents(address: Any) -> list[str]:
    """The runs of the same container derived from the run at *address* (directly or through
    another run), in write order: what goes when that run is removed.

    Parameters
    ----------
    address : str or Path
        A run of an analysis container (``…/m.pto/<run>``).
    """
    from chisurf.core.fio.analysis_path import split_container_path

    container, run = split_container_path(address)
    if container is None or not container.exists():
        return []
    uids, needs = _run_graph(container)
    gone = {run}
    grew = True
    while grew:
        grew = False
        for other, of in needs.items():
            if other not in gone and of & gone:
                gone.add(other)
                grew = True
    return [r for r in uids if r in gone and r != run]


def remove_run(address: Any) -> list[str]:
    """Remove the run at *address* and every run derived from it (:func:`run_dependents`) from
    its container, then tell the listeners (:func:`container_changed`).

    The photons and every other run stay. The space the objects took is freed when the container
    is next rewritten; nothing is compacted under an open handle.

    Returns
    -------
    list of str
        The addresses of the runs removed (the run first, then its dependents).
    """
    from chisurf.core.fio.analysis_path import run_path, split_container_path
    from chisurf.core.fio.pto import Measurement, PtoMfdbError

    container, run = split_container_path(address)
    if container is None or not container.exists():
        return []
    runs = [run, *run_dependents(address)]
    uids, _needs = _run_graph(container)
    with Measurement.open(container, writable=True) as measurement:
        for name in runs:
            for uid in uids.get(name, ()):
                if not measurement._f.remove(uid):
                    raise PtoMfdbError(
                        f"could not remove {name!r} from {container}: {measurement._f.error()}"
                    )
    container_changed(container)
    return [run_path(container, name) for name in runs]
