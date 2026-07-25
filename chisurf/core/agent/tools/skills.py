"""Agent tools for listing and loading skills.

The runtime loads the skills a request obviously needs before the model even
sees it (see :meth:`AgentSession.ask`).  These tools exist for the cases the
matcher cannot see: a request whose wording gives nothing away, or a job that
turns into something else halfway through — "actually, now export all of
this" — where the model itself notices which procedure it needs.
"""

from __future__ import annotations

from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_READ, ToolError, ToolRegistry

registry = ToolRegistry()


def _library(context: AgentContext) -> Any:
    """Return the skill library carried by the session.

    Raises
    ------
    ToolError
        When the session has no library (skills are disabled).
    """
    library = context.extras.get("skill_library")
    if library is None:
        raise ToolError("no skills are available in this session")
    return library


@registry.add(
    name="list_skills",
    description=(
        "List the procedures (skills) available for working with ChiSurf, "
        "with a one-line description of when each applies.\n"
        "The ones relevant to the request are already loaded; use this when "
        "you suspect a procedure exists for what you are about to do."
    ),
    parameters={"type": "object", "properties": {}},
    safety=SAFETY_READ,
)
def list_skills(context: AgentContext) -> dict[str, Any]:
    """Return the skill catalogue and which skills are active."""
    library = _library(context)
    active = list(context.extras.get("active_skills", []))
    return {
        "ok": True,
        "loaded": active,
        "available": [
            {"name": skill.name, "description": skill.description}
            for skill in sorted(library.skills.values(), key=lambda s: s.name)
        ],
    }


@registry.add(
    name="load_skill",
    description=(
        "Load a skill's full instructions into the conversation.\n"
        "Call this when a task matches a skill that was not loaded "
        "automatically — the description in the catalogue tells you when each "
        "one applies. The instructions stay available for the rest of the "
        "conversation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Skill name, exactly as listed in the catalogue.",
            }
        },
        "required": ["name"],
    },
    safety=SAFETY_READ,
)
def load_skill(context: AgentContext, name: str) -> dict[str, Any]:
    """Return the full text of a skill and mark it active for the session."""
    library = _library(context)
    skill = library.get(name)
    if skill is None:
        raise ToolError(f"there is no skill called {name!r}. Available: {library.names()}")

    active = context.extras.setdefault("active_skills", [])
    if skill.name not in active:
        active.append(skill.name)
    context.emit("skill.loaded", {"skill": skill.name, "trigger": "model"})
    return {
        "ok": True,
        "skill": skill.name,
        "tools": skill.tools,
        "instructions": skill.rendered(),
    }
