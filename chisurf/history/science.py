"""Canonical project records for scientific history, independent of audit payloads."""

from __future__ import annotations

import copy
import json


def encode_science(project):
    """Detach a canonical project and its owned bytes without recursive history."""
    from chisurf.core.project import Project
    from chisurf.core.project.archive import HISTORY_FILENAME
    from chisurf.core.project.project import ResourceContext

    if not isinstance(project, Project):
        raise TypeError("Scientific history capture requires a canonical Project")
    data = copy.deepcopy(project.to_dict())
    extra = data.get("extra", {})
    for key in ("history", "history_events", "history_state"):
        extra.pop(key, None)
    data.get("ui", {}).pop("history_browser", None)
    resources = ResourceContext(
        entries={
            name: value
            for name, value in project.resources.entries.items()
            if name != HISTORY_FILENAME
        },
        sources=project.resources.sources,
    )
    state = {"project": data, "resources": resources.to_transport_dict()}
    json.dumps(state, allow_nan=False)
    decode_science(state)
    return state


def decode_science(state):
    """Validate complete typed science through its canonical detached codec."""
    from chisurf.core.project import Project, restore_session
    from chisurf.core.project.project import ResourceContext

    if not isinstance(state, dict) or set(state) != {"project", "resources"}:
        raise ValueError("Invalid scientific history state")
    data = copy.deepcopy(state["project"])
    if any(key in data.get("extra", {}) for key in ("history", "history_events", "history_state")):
        raise ValueError("History state cannot recursively contain history")
    json.dumps(state, allow_nan=False)
    project = Project.from_dict(data)
    project.resources = ResourceContext.from_transport_dict(state["resources"])
    restore_session(project)
    return project


def science_fingerprint(state):
    """Use the canonical document comparison, ignoring capture-time bookkeeping."""
    from chisurf.core.project import Project
    from chisurf.core.project.lifecycle import snapshot_fingerprint
    from chisurf.core.project.project import ResourceContext

    project = Project.from_dict(copy.deepcopy(state["project"]))
    project.resources = ResourceContext.from_transport_dict(state["resources"])
    return snapshot_fingerprint(project)
