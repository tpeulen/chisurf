"""Model-independent decoding of authoritative project-capture replies."""

from __future__ import annotations

from typing import Any

from .project import Project, ResourceContext


def project_from_capture_reply(reply: Any, *, name: str) -> Project:
    """Require explicit success before adopting a detached snapshot and resources."""
    if not isinstance(reply, dict) or reply.get("ok") is not True:
        error = (
            reply.get("error", "missing acknowledgement")
            if isinstance(reply, dict)
            else "invalid response"
        )
        raise RuntimeError(f"Project capture failed: {error}")
    project = Project.from_dict(reply["project"])
    project.resources = ResourceContext.from_transport_dict(reply["resources"])
    project.name = name
    return project
