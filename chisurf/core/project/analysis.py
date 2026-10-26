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
    "container_dir",
    "containers",
    "derived_datasets",
    "is_derived",
    "project_files",
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


def derived_datasets() -> list:
    """The run rows of the workspace: one per burst run of every analysis container, a child of
    its photon dataset (whose uid names the container's folder)."""
    from chisurf.core.experiments.linked import reader_for_kind
    from chisurf.core.fio.classify import container_entries

    reader = reader_for_kind("bursts")
    if reader is None:
        return []
    out = []
    for uid, paths in containers().items():
        for path in paths:
            try:
                runs = [a for kind, a in container_entries(path) if kind == "bursts"]
            except Exception:  # noqa: BLE001 - an unreadable container shows no runs
                _log.exception("could not list the runs of %s", path)
                continue
            for run in runs:
                dataset = reader.make_dataset(run, result_of="" if uid == "_" else uid)
                dataset.data_reader = reader
                out.append(dataset)
    return out
