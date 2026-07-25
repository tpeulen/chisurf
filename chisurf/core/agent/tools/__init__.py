"""Built-in tool catalogue for the ChiSurf LLM agent.

The catalogue is assembled from three groups:

``data``
    finding files on disk, loading them, describing experiments/readers/models
``fitting``
    creating fits, running them, editing parameters, exporting results
``scripting``
    running Python in the live session and reading/writing text files

Every group is a plain :class:`~chisurf.core.agent.spec.ToolRegistry`, so a
plugin can extend the agent by merging its own registry into the default one.
"""

from __future__ import annotations

from chisurf.core.agent.spec import ToolRegistry
from chisurf.core.agent.tools import data, fitting, scripting

__all__ = ["build_default_registry", "data", "fitting", "scripting"]


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
    for group in (data.registry, fitting.registry, scripting.registry):
        for spec in group.tools.values():
            registry.register(spec)
    return registry
