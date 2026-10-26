"""The temporary project a session starts with until the user saves it somewhere.

ChiSurf starts with a blank ``.cs.pto`` (profile ``ChiSurf.Project``) so that data can be embedded
from the first drop. Until the user chooses a location it lives in a per-user temporary folder,
``<tmp>/chisurf-projects/untitled-<timestamp>.cs.pto`` (mode 0700). Beside it a small marker,
``<name>.cs.pto.session``, names the process that owns it and whether it has content, so a later
start can tell an abandoned project (its process is gone) from one in use, and an empty abandoned
project (deleted) from one with work in it (kept for recovery for :data:`KEEP_DAYS`).

The folder can be redirected with ``CHISURF_PROJECT_TEMP_DIR`` (tests; the web release points it
at its browser file system).
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path

__all__ = [
    "KEEP_DAYS",
    "MARKER_SUFFIX",
    "abandoned",
    "clean_abandoned",
    "is_temporary",
    "mark",
    "new_path",
    "remove",
    "temp_root",
]

_log = logging.getLogger(__name__)

#: An abandoned temporary project with content is kept this long for recovery, then deleted.
KEEP_DAYS = 14
#: The marker beside a temporary project (owner process, content flag).
MARKER_SUFFIX = ".session"
_PREFIX = "untitled-"
_SUFFIX = ".cs.pto"


def temp_root() -> Path:
    """The per-user folder of temporary projects (created, mode 0700)."""
    override = os.environ.get("CHISURF_PROJECT_TEMP_DIR")
    root = Path(override) if override else Path(tempfile.gettempdir()) / "chisurf-projects"
    root.mkdir(parents=True, exist_ok=True)
    try:
        root.chmod(0o700)
    except OSError:  # a file system without POSIX modes (the browser's) keeps its own
        pass
    return root


def new_path(now: datetime | None = None) -> Path:
    """A fresh ``untitled-<timestamp>.cs.pto`` path in :func:`temp_root` (not created)."""
    stamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    root = temp_root()
    path = root / f"{_PREFIX}{stamp}{_SUFFIX}"
    n = 2
    while path.exists() or _marker(path).exists():
        path = root / f"{_PREFIX}{stamp}-{n}{_SUFFIX}"
        n += 1
    return path


def is_temporary(path: str | Path | None) -> bool:
    """Whether *path* is a temporary project (a file of :func:`temp_root`)."""
    if not path:
        return False
    try:
        return Path(path).resolve().parent == temp_root().resolve()
    except OSError:
        return False


def _marker(path: str | Path) -> Path:
    return Path(f"{path}{MARKER_SUFFIX}")


def mark(path: str | Path, *, has_content: bool) -> None:
    """Record that this process owns the temporary project *path* and whether it has content."""
    payload = {"pid": os.getpid(), "has_content": bool(has_content), "updated": time.time()}
    try:
        _marker(path).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        _log.exception("could not write the temporary project's marker")


def remove(path: str | Path | None) -> None:
    """Delete a temporary project and its marker (never raises; refuses non-temporary paths)."""
    if not is_temporary(path):
        return
    for target in (Path(path), _marker(path)):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            _log.exception("could not remove %s", target)


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # it exists, owned by someone else
        return True
    except OSError:
        return False
    return True


def abandoned() -> list[tuple[Path, bool, float]]:
    """Temporary projects whose owning process is gone: ``(path, has_content, age_s)``."""
    found = []
    now = time.time()
    for path in sorted(temp_root().glob(f"{_PREFIX}*{_SUFFIX}")):
        try:
            info = json.loads(_marker(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            info = {}
        if _alive(int(info.get("pid", 0) or 0)):
            continue
        try:
            age = now - path.stat().st_mtime
        except OSError:
            continue
        found.append((path, bool(info.get("has_content", True)), age))
    return found


def clean_abandoned(keep_days: float = KEEP_DAYS) -> list[Path]:
    """Delete abandoned empty projects and those older than *keep_days*; return the ones kept.

    The kept ones hold work of a session that ended without saving (a crash): they are offered
    for recovery.
    """
    kept = []
    for path, has_content, age in abandoned():
        if not has_content or age > keep_days * 86400.0:
            remove(path)
        else:
            kept.append(path)
    return kept
