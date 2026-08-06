"""Built-in tool catalogue for the ChiSurf LLM agent.

The catalogue is assembled from three groups:

``data``
    finding files on disk, loading them, describing experiments/readers/models
``fitting``
    creating fits, running them, editing parameters, exporting results
``decay``
    the knobs that decide whether a decay fit means anything: the instrument
    response, the number of components, the quality report, and the plot
``linking``
    global analysis: sharing a parameter's value between fits
``scripting``
    running Python in the live session and reading/writing text files
``codebase``
    knowledge for *writing* ChiSurf code: the source API index, the
    documentation, the plugin catalogue, and a syntax/lint check
``documentation``
    answering a *user's* question out of the documentation: browsing it by
    kind and subject through the Open-Knowledge-Format header each page
    carries, searching it, and reading one page or one section
``skills``
    listing and loading the procedures in :mod:`chisurf.core.agent.skills`
``system``
    driving the computer itself: running programs, checking what is
    installed, listing directories

Every group is a plain :class:`~chisurf.core.agent.spec.ToolRegistry`, so a
plugin can extend the agent by merging its own registry into the default one.
"""

from __future__ import annotations

from chisurf.core.agent.spec import ToolRegistry
from chisurf.core.agent.tools import (
    codebase,
    data,
    decay,
    documentation,
    fitting,
    linking,
    scripting,
    skills,
    system,
)

__all__ = [
    "build_default_registry",
    "codebase",
    "data",
    "decay",
    "documentation",
    "fitting",
    "linking",
    "scripting",
    "skills",
    "system",
]


def build_default_registry() -> ToolRegistry:
    """Return a registry with every built-in ChiSurf agent tool.

    Returns
    -------
    ToolRegistry
        A fresh registry; callers may add or remove tools without affecting
        other agent sessions.

    Examples
    --------
    >>> registry = build_default_registry()
    >>> "load_data" in registry.names()
    True
    """
    registry = ToolRegistry()
    for group in (
        data.registry,
        codebase.registry,
        documentation.registry,
        fitting.registry,
        decay.registry,
        linking.registry,
        scripting.registry,
        skills.registry,
        system.registry,
    ):
        for spec in group.tools.values():
            registry.register(spec)
    return registry
