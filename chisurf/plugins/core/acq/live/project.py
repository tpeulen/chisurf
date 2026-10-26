"""Where a recording goes in the project: the open project's folder, and its autosave.

A recording is written while measuring into a ``<project> recordings`` folder beside the session's
project file -- the temporary project's folder while it is unsaved -- so a crash mid-run leaves the
photons on disk; at stop the run enters the project like a dropped file and is embedded in the
``.cs.pto`` (or linked, when the user chose so) by the project's next save, which the autosave makes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = [
    "active_shell",
    "add_to_workspace",
    "autosave",
    "project_file",
    "recording_dir",
    "workspace_datasets",
]


def active_shell() -> Any:
    """The ChiSurf shell open in this process, if any (the plugin also runs standalone)."""
    try:
        from chisurf.emtk import main_app

        ref = main_app._ACTIVE_SHELL
        shell = ref() if ref is not None else None
        return None if shell is None or getattr(shell, "_shell_closed", False) else shell
    except Exception:  # noqa: BLE001 - no shell: standalone
        return None


def workspace_datasets(kind: str) -> list[Any]:
    """The workspace's datasets of *kind* (``photons``, ``setup``, ...): the shell's Datasets rows
    when a shell is open (its session lives behind the server channel, which the in-process API does
    not see), else the in-process session's datasets. Each has ``address``, ``name``,
    ``data_kind`` and, where the row carries it, ``header_json``."""
    from types import SimpleNamespace

    shell = active_shell()
    rows = getattr(getattr(getattr(shell, "data", None), "datasets", None), "datasets", None)
    if rows is not None:
        return [
            SimpleNamespace(
                address=str(r.get("address") or ""),
                name=str(r.get("name") or ""),
                data_kind=kind,
                header_json=str(r.get("header_json") or ""),
                uid=r.get("uid"),
            )
            for r in list(rows)
            if r.get("kind") == kind and r.get("address")
        ]
    try:
        from chisurf.core.api import dataset_objects

        return [d for d in dataset_objects() if str(getattr(d, "data_kind", "")) == kind]
    except Exception:  # noqa: BLE001 - no session (standalone): an empty workspace
        return []


def project_file() -> Path | None:
    """The session's project file (the temporary one while unsaved), if a shell is open."""
    shell = active_shell()
    path = getattr(getattr(getattr(shell, "project", None), "document", None), "path", None)
    return Path(path) if path else None


def recording_dir(fallback: str | Path) -> Path:
    """``<project folder>/<project name> recordings``, or *fallback* without a project."""
    project = project_file()
    if project is None:
        return Path(fallback)
    stem = project.name[: -len(".cs.pto")] if project.name.endswith(".cs.pto") else project.stem
    return project.parent / f"{stem} recordings"


def autosave() -> bool:
    """Let the shell write the project now (the temporary project in place; a saved one's working
    copy), so an embedded recording is inside the ``.cs.pto`` without waiting for the next tick."""
    shell = active_shell()
    project = getattr(shell, "project", None)
    if project is None or not hasattr(project, "autosave_now"):
        return False
    try:
        return bool(project.autosave_now())
    except Exception:  # noqa: BLE001 - the next autosave tick writes it
        return False


def add_to_workspace(datasets: list, label: str = "Adding the recording") -> bool:
    """Add *datasets* to the session the way the shell's drop does: through the shell's API (its
    server channel) on its job queue, then the project's autosave. Without a shell they go through
    ``register_result`` (the in-process API). Returns whether a shell took them.
    """
    shell = active_shell()
    data = getattr(shell, "data", None)
    api = getattr(getattr(data, "session", None), "api", None)
    if data is None or api is None or not hasattr(data, "_start"):
        from chisurf.core.plugin.workspace_input import register_result

        for dataset in datasets:
            register_result(dataset)
        return False

    def add() -> dict:
        for dataset in datasets:
            result = api.load_dataset(dataset=dataset, name=str(getattr(dataset, "name", "") or ""))
            if isinstance(result, dict) and result.get("ok") is False:
                return result
        return {"ok": True}

    data._start(label, add, lambda _result: autosave())
    return True
