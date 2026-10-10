"""Project-document identity and the decision gate before destructive actions.

Scientific snapshots and their storage transports do not own application shutdown.
This module provides that independent lifecycle, without Qt or MMFDB dependencies.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .fit_state import SAMPLING_ENTRY_PREFIX
from .project import Project


class SaveDecision(str, Enum):
    """User choices for replacing or closing an active project."""

    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


def confirm_transition(
    *,
    has_content: bool,
    prompt: Callable[[], SaveDecision],
    save: Callable[[], bool],
) -> bool:
    """Accept a destructive transition only after an explicit safe decision.

    Parameters
    ----------
    has_content : bool
        Whether the session contains work that must be protected.
    prompt : callable
        Return Save, Don't Save, or Cancel. Closing the dialog means Cancel.
    save : callable
        Return True only after a complete, verified save. A cancelled dialog,
        None result, or exception never authorizes losing the active session.

    Returns
    -------
    bool
        Whether the caller may now close or replace the session.
    """
    if not has_content:
        return True
    decision = prompt()
    if decision == SaveDecision.DISCARD:
        return True
    if decision == SaveDecision.SAVE:
        return save() is True
    return False


def snapshot_fingerprint(project: Project) -> str:
    """Hash persisted content, ignoring capture timestamps and save bookkeeping.

    Parameters
    ----------
    project : Project
        Complete scientific and presentation snapshot.

    Returns
    -------
    str
        Stable digest for dirty-state comparison. History events and the action
        catalogue are not edits to scientific state; save/load itself changes them.
    """
    payload = project.to_dict()
    # A sampling chain can be megabytes and an autosave tick fingerprints the
    # whole project; its name and size stand in for its bytes, which are never
    # encoded. A new run still changes the digest: its diagnostics report (small,
    # hashed in full) differs.
    resources = project.resources
    payload["resources"] = {
        "entries": {
            name: (
                f"bytes:{len(content)}"
                if name.startswith(SAMPLING_ENTRY_PREFIX) and name.endswith(".er4")
                else base64.b64encode(content).decode("ascii")
            )
            for name, content in resources.entries.items()
        },
        "sources": resources.encoded_sources(),
    }
    payload["meta"] = dict(payload.get("meta", {}))
    payload["meta"].pop("created", None)
    payload["extra"] = dict(payload.get("extra", {}))
    for key in ("history", "history_events", "action_catalog"):
        payload["extra"].pop(key, None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class ProjectDocument:
    """Identity and baseline of the last successfully saved/restored project.

    The caller records success only after the storage adapter has read back the
    exact written target. Selecting a filename or receiving a RPC success without
    verifying its content must not change this document.
    """

    name: str = "untitled"
    backend: str = "file"
    path: Path | None = None
    project_id: str | None = None
    version_id: str | None = None
    visibility: str = "private"
    _saved_fingerprint: str | None = None

    def clone(self) -> ProjectDocument:
        """Return a detached copy suitable for transactional staging."""
        return ProjectDocument(
            name=self.name,
            backend=self.backend,
            path=self.path,
            project_id=self.project_id,
            version_id=self.version_id,
            visibility=self.visibility,
            _saved_fingerprint=self._saved_fingerprint,
        )

    def adopt(self, staged: ProjectDocument) -> None:
        """Atomically adopt an already validated document state."""
        if not isinstance(staged, ProjectDocument):
            raise TypeError("staged document state must be a ProjectDocument")
        values = staged.clone()
        self.name = values.name
        self.backend = values.backend
        self.path = values.path
        self.project_id = values.project_id
        self.version_id = values.version_id
        self.visibility = values.visibility
        self._saved_fingerprint = values._saved_fingerprint

    def is_modified(self, project: Project) -> bool:
        """Return whether the snapshot differs from the accepted baseline."""
        return self._saved_fingerprint != snapshot_fingerprint(project)

    def stage_file_save(self, project: Project, path: str | Path) -> ProjectDocument:
        """Build validated file identity without changing the live document."""
        fingerprint = snapshot_fingerprint(project)
        destination = Path(path)
        if not str(destination).lower().endswith(".cs.pto"):
            raise ValueError("ChiSurf project files must end in .cs.pto")
        return ProjectDocument(
            name=project.name,
            backend="file",
            path=destination,
            project_id=None,
            version_id=None,
            visibility="private",
            _saved_fingerprint=fingerprint,
        )

    def record_file_save(self, project: Project, path: str | Path) -> None:
        """Accept a verified file save or file restore as the new baseline."""
        self.adopt(self.stage_file_save(project, path))

    def stage_database_save(self, project: Project, result: dict[str, Any]) -> ProjectDocument:
        """Build validated database identity without changing the live document."""
        fingerprint = snapshot_fingerprint(project)
        project_id = result.get("project_id")
        version_id = result.get("version_id")
        if result.get("ok") is not True or not project_id or not version_id:
            raise ValueError("A verified MMFDB save requires project_id and version_id")
        return ProjectDocument(
            name=project.name,
            backend="mmfdb",
            path=None,
            project_id=str(project_id),
            version_id=str(version_id),
            visibility=str(result.get("visibility", "private")),
            _saved_fingerprint=fingerprint,
        )

    def record_database_save(self, project: Project, result: dict[str, Any]) -> None:
        """Accept the exact verified MMFDB version and preserve its parent identity."""
        self.adopt(self.stage_database_save(project, result))

    def reset(self) -> None:
        """Forget document identity after an accepted new/close-project operation."""
        self.name = "untitled"
        self.backend = "file"
        self.path = None
        self.project_id = None
        self.version_id = None
        self.visibility = "private"
        self._saved_fingerprint = None


AUTOSAVE_SUFFIX = ".autosave.cs.pto"


@dataclass
class Autosave:
    """Periodic, silent copy of the live project beside its document.

    Autosave is not a save: it never changes the document's accepted baseline
    (``ProjectDocument._saved_fingerprint``), never records a history row and
    never asks the user anything. It writes only when the scientific content
    differs from what it last wrote, so an idle session is not rewritten on
    every tick. Qt-free: the caller owns the clock.

    Parameters
    ----------
    interval_s : float
        Minimum seconds between two writes.
    enabled : bool
        Master switch; a disabled autosave is never due.
    """

    interval_s: float = 120.0
    enabled: bool = True
    _last_fingerprint: str | None = field(default=None, repr=False)
    _last_time: float = field(default=-math.inf, repr=False)

    def due(self, now: float) -> bool:
        """Return whether a write may happen at monotonic time ``now``."""
        return bool(self.enabled) and (now - self._last_time) >= float(self.interval_s)

    @staticmethod
    def target(document: ProjectDocument, working_path: str | Path) -> Path:
        """Return the autosave file for ``document``.

        A document with a file path gets a sibling ``<name>.autosave.cs.pto``;
        an unsaved one goes to ``<working_path>/autosave/``. Both keep the
        ``.cs.pto`` suffix the project storage requires.
        """
        path = getattr(document, "path", None)
        if path is not None:
            path = Path(path)
            name = path.name
            if name.lower().endswith(".cs.pto"):
                name = name[: -len(".cs.pto")]
            return path.with_name(f"{name}{AUTOSAVE_SUFFIX}")
        name = str(getattr(document, "name", None) or "untitled")
        return Path(working_path) / "autosave" / f"{name}{AUTOSAVE_SUFFIX}"

    def run(
        self,
        project: Project,
        save: Callable[[Project, Path], Any],
        document: ProjectDocument,
        working_path: str | Path,
        now: float,
    ) -> Path | None:
        """Write ``project`` through ``save`` when due and changed.

        Parameters
        ----------
        project : Project
            Live snapshot to write.
        save : callable
            ``save(project, path)``; the atomic storage writer.
        document : ProjectDocument
            Identity that decides the target path; never modified.
        working_path : str or Path
            Fallback folder for a document that has no file yet.
        now : float
            Monotonic clock reading.

        Returns
        -------
        Path or None
            The written file, or None when nothing was written. An exception
            from ``save`` propagates and leaves the recorded state unchanged.
        """
        if not self.due(now):
            return None
        fingerprint = snapshot_fingerprint(project)
        if fingerprint == self._last_fingerprint:
            return None
        destination = self.target(document, working_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        written = save(project, destination)
        self._last_fingerprint = fingerprint
        self._last_time = now
        return Path(written) if written is not None else destination
