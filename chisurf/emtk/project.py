"""Qt-free adapters for ChiSurf's portable project payload operations.

The project browser runs as a native EMTK app.  Keep access to the established
project serializer while importing its legacy macro module lazily; that module
must remain safe to import in a process where Qt is unavailable.
"""

from __future__ import annotations

from typing import Any

from chisurf.core.project import Project


def get_project_payload(project_name: str = "chisurf_project") -> Project:
    """Capture the current ChiSurf session in the canonical project format."""
    from chisurf.macros.core_fit import get_project_payload as capture

    return capture(project_name)


def load_project_payload(
    payload: Project | dict[str, Any], project_path: str | None = None
) -> Any:
    """Restore a canonical project payload without requiring the Qt GUI."""
    from chisurf.macros.core_fit import load_project_payload as restore

    project = payload if isinstance(payload, Project) else Project.from_dict(payload)
    return restore(project, project_path=project_path, _skip_gui_creation=True)
