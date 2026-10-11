"""The recent-projects list both shells offer under *File*: one JSON file in the settings folder.

Qt-free, so the emtk shell and the Qt shell read and write the same list
(``<settings>/recent_projects.json``, ``{"projects": [path, ...]}``, newest
first, at most :data:`LIMIT`).
"""

from __future__ import annotations

import json
import logging
import os
import pathlib

_log = logging.getLogger(__name__)

#: How many projects the list keeps.
LIMIT = 10


def recent_projects_file() -> pathlib.Path:
    """``<settings>/recent_projects.json``, or ``~/.chisurf/recent_projects.json`` without settings.

    Returns
    -------
    pathlib.Path
        Where the list is kept.
    """
    try:
        import chisurf

        return chisurf.core.settings.get_path("settings") / "recent_projects.json"
    except Exception:  # noqa: BLE001 - a broken settings module must not lose the list
        return pathlib.Path.home() / ".chisurf" / "recent_projects.json"


def load() -> list[str]:
    """The stored list, newest first; ``[]`` when there is none or it cannot be read."""
    path = recent_projects_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("projects", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [str(item) for item in items if item is not None and str(item)]


def store(projects: list[str]) -> None:
    """Write *projects* as the list (a failure is logged, never raised)."""
    path = recent_projects_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"projects": list(projects or [])}, indent=2), encoding="utf-8")
    except OSError:
        _log.exception("Failed to write recent projects file: %s", path)


def _key(path: str) -> str:
    normal = os.path.normpath(str(path))
    return normal.lower() if os.name == "nt" else normal


def added(projects: list[str], project_path: str | os.PathLike) -> list[str]:
    """*projects* with *project_path* (absolute) first, duplicates dropped, at most :data:`LIMIT`."""
    first = os.path.abspath(os.path.normpath(str(project_path)))
    seen: set[str] = set()
    out: list[str] = []
    for item in [first, *list(projects or [])]:
        if item and _key(item) not in seen:
            seen.add(_key(item))
            out.append(item)
    return out[:LIMIT]


def removed(projects: list[str], project_path: str | os.PathLike) -> list[str]:
    """*projects* without *project_path*."""
    gone = _key(str(project_path))
    return [item for item in projects or [] if _key(item) != gone]


__all__ = ["LIMIT", "added", "load", "recent_projects_file", "removed", "store"]
