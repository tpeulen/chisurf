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
    "analysis_graph",
    "dependents",
    "operation_label",
    "remove_analysis",
    "restore",
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


#: Words of an operation term written in capitals in its label (``burst_2cde`` -> "Burst 2CDE").
_ACRONYMS = {"2cde", "bva", "fcs", "fret", "gmm", "hmm", "mle", "pch", "pda", "psf", "tcspc"}


def operation_label(operation: str) -> str:
    """The label of an operation term of the vocabulary: ``burst_variance_analysis`` ->
    "Burst variance analysis", ``photon_hmm`` -> "Photon HMM"."""
    words = [w.upper() if w in _ACRONYMS else w for w in str(operation or "analysis").split("_")]
    text = " ".join(words)
    return text[:1].upper() + text[1:]


def analysis_graph(container: Any) -> list[dict]:
    """The analyses of *container* and what each was computed from, in write order.

    An analysis is what one operation wrote into one run: the run's burst search (or import) is
    the run itself, and every other operation that wrote tables into it (BVA, 2CDE, burst-wise
    lifetimes, H2MM, ...) is an analysis of its own. Its parent is the analysis that wrote the
    tables its tables name as parents (``derived_from``): a companion hangs under the search it
    was computed from, a fusion under the search it fused, an analysis of the fusion under that.

    Returns
    -------
    list of dict
        ``key`` (``(run, operation)``), ``run``, ``operation``, ``label``, ``kind`` (``"bursts"``
        for a run, ``"table"`` for an analysis of a run), ``address``, ``tables`` (names),
        ``uids``, ``parents`` (every analysis it read, by key) and ``parent`` (the first, or
        ``None`` when it was computed from the photons).
    """
    from chisurf.core.fio.analysis_path import run_path, split_artifact_name
    from chisurf.core.fio.classify import BURST_RUN_OPERATIONS
    from chisurf.core.fio.pto import Measurement

    container = Path(container)
    nodes: dict[tuple[str, str], dict] = {}
    node_of: dict[int, tuple[str, str]] = {}
    parents_of: dict[int, list[int]] = {}
    with Measurement.open(container, writable=False) as measurement:
        for obj in measurement.artifacts():
            operation = str(measurement.tag(obj.uid, "_mmfdb_operation.operation_type") or "")
            if not operation:
                continue  # the photons, a readme: not an analysis
            run, table = split_artifact_name(str(obj.name))
            # a burst search (or import) is its run; anything else written into the run is an
            # analysis of it, one per operation
            key = (run, "") if operation in BURST_RUN_OPERATIONS else (run, operation)
            node = nodes.setdefault(
                key,
                {
                    "key": key,
                    "run": run,
                    "operation": operation,
                    "tables": [],
                    "uids": [],
                },
            )
            node["tables"].append(table)
            node["uids"].append(int(obj.uid))
            node_of[int(obj.uid)] = key
            parents_of[int(obj.uid)] = list(measurement.parents(obj.uid))
    for key, node in nodes.items():
        run, operation = key
        if not operation:
            node["kind"], node["label"] = "bursts", run
            node["address"] = run_path(container, run)
        else:
            node["kind"] = "table"
            node["label"] = operation_label(operation)
            node["address"] = run_path(container, f"{run}/{node['tables'][0]}" if run else node["tables"][0])
        found = []
        for uid in node["uids"]:
            for parent in parents_of[uid]:
                other = node_of.get(int(parent))
                if other is not None and other != key and other not in found:
                    found.append(other)
        if operation and (run, "") in nodes and (run, "") not in found:
            found.append((run, ""))  # an analysis written into a run belongs to it
        node["parents"] = found
        node["parent"] = found[0] if found else None
    return list(nodes.values())


def derived_datasets() -> list:
    """The analysis rows of the workspace, parents before children: every burst run of every
    analysis container, a child of its photon dataset (whose uid names the container's folder) or
    of the run it was computed from, and every analysis of a run (BVA, 2CDE, lifetimes, ...) a
    child of the analysis it was computed from."""
    from chisurf.core.data import LinkedDataset
    from chisurf.core.experiments.linked import reader_for_kind

    reader = reader_for_kind("bursts")
    if reader is None:
        return []
    out = []
    for uid, paths in containers().items():
        for path in paths:
            try:
                graph = analysis_graph(path)
            except Exception:  # noqa: BLE001 - an unreadable container shows no runs
                _log.exception("could not list the analyses of %s", path)
                continue
            address = {node["key"]: node["address"] for node in graph}
            for node in graph:
                if node["kind"] == "bursts":
                    dataset = reader.make_dataset(node["address"], result_of="" if uid == "_" else uid)
                    dataset.data_reader = reader
                else:
                    dataset = LinkedDataset(node["address"], data_kind="table", name=node["label"])
                    dataset.result_of = "" if uid == "_" else uid
                # the analysis it was computed from: its row is this row's parent
                dataset.source_run = address.get(node["parent"], "") if node["parent"] else ""
                out.append(dataset)
    # a restored project lists these rows as they are: each names its source row's uid already
    by_address = {str(d.address): d for d in out}
    for dataset in out:
        source = by_address.get(dataset.source_run) if dataset.source_run else None
        if source is not None:
            dataset.result_of = str(source.unique_identifier)
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
    """Add every analysis of the analysis containers (:func:`derived_datasets`) that the workspace
    does not list yet, each the child of the row it was computed from.

    Returns
    -------
    list
        The datasets that were added.
    """
    if not containers():
        return []
    from chisurf.core.api import dataset_objects
    from chisurf.core.plugin.workspace_input import register_result

    def listed_uids() -> dict[str, str]:
        return {
            str(getattr(d, "address", "")): str(getattr(d, "unique_identifier", ""))
            for d in dataset_objects()
        }

    listed = listed_uids()
    added = []
    for row in derived_datasets():  # parents first: a source is listed before its results
        address = str(getattr(row, "address", ""))
        if not address or address in listed:
            continue
        source = str(getattr(row, "source_run", "") or "")
        parent = listed.get(source, "") if source else ""
        if parent:
            row.result_of = parent
        register_result(row, result_of=str(getattr(row, "result_of", "") or ""))
        listed = listed_uids()  # the uid the session gave it (it keeps its own copy)
        added.append(row)
    return added


def _descendants(graph: list[dict], start: set) -> list[dict]:
    """The analyses of *graph* computed from *start* (keys), directly or through another, and
    *start*'s own: removing a run removes everything written into it."""
    gone = set(start)
    runs = {run for run, operation in start if not operation}
    grew = True
    while grew:
        grew = False
        for node in graph:
            key = node["key"]
            if key in gone:
                continue
            if node["run"] in runs or any(p in gone for p in node["parents"]):
                gone.add(key)
                if not key[1]:
                    runs.add(node["run"])
                grew = True
    return [node for node in graph if node["key"] in gone]


def _node_at(graph: list[dict], address: Any) -> dict | None:
    return next((n for n in graph if n["address"] == str(Path(str(address)))), None)


def dependents(address: Any) -> list[dict]:
    """The analyses removed with the run or analysis at *address* (not itself), in write order:
    everything computed from it, directly or through another analysis.

    Parameters
    ----------
    address : str or Path
        A run (``…/m.pto/<run>``) or an analysis of a run (``…/m.pto/<run>/<table>``) of an
        analysis container.
    """
    from chisurf.core.fio.analysis_path import split_container_path

    container, _ = split_container_path(address)
    if container is None or not container.exists():
        return []
    graph = analysis_graph(container)
    node = _node_at(graph, address)
    if node is None:
        return []
    return [n for n in _descendants(graph, {node["key"]}) if n["key"] != node["key"]]


def remove_analysis(address: Any) -> list[str]:
    """Remove the run or analysis at *address* and everything computed from it
    (:func:`dependents`) from its container, then tell the listeners (:func:`container_changed`).

    The photons and every unrelated analysis stay. The space the objects took is freed when the
    container is next rewritten; nothing is compacted under an open handle.

    Returns
    -------
    list of str
        The addresses removed (the one asked for first, then what was computed from it).
    """
    from chisurf.core.fio.analysis_path import split_container_path
    from chisurf.core.fio.pto import Measurement, PtoMfdbError

    container, _ = split_container_path(address)
    if container is None or not container.exists():
        return []
    graph = analysis_graph(container)
    node = _node_at(graph, address)
    if node is None:
        return []
    gone = _descendants(graph, {node["key"]})
    gone.sort(key=lambda n: n["key"] != node["key"])
    with Measurement.open(container, writable=True) as measurement:
        for item in gone:
            for uid in item["uids"]:
                if not measurement._f.remove(uid):
                    raise PtoMfdbError(
                        f"could not remove {item['label']!r} from {container}: {measurement._f.error()}"
                    )
    container_changed(container)
    return [item["address"] for item in gone]
