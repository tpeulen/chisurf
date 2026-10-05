"""Project-document identity and the decision gate before destructive actions.

Scientific snapshots and their storage transports do not own application shutdown.
This module provides that independent lifecycle, without Qt or MMFDB dependencies.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

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
    payload["resources"] = project.resources.to_transport_dict()
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
