"""LLM agent that operates ChiSurf in plain language.

The package is deliberately Qt-free so the same harness backs the GUI agent
panel, the ``python -m chisurf.core.agent`` command line, and the tests.

Layout
------
``spec``
    Tool descriptions, JSON schemas, safety tiers and the registry.
``context``
    Execution policy plus the resolution of loose references ("the second
    fit") to real objects.
``tools``
    The built-in catalogue: files, data loading, fitting, scripting.
``llm``
    OpenAI-compatible chat client with native tool calling.
``prompt``
    System prompt and the text-protocol fallback.
``runtime``
    The observe-act loop, budgets, and the result object.

Examples
--------
>>> from chisurf.core.agent import build_default_registry
>>> "create_fit" in build_default_registry().names()
True
"""

from __future__ import annotations

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.llm import LLMClient, LLMError, LLMSettings
from chisurf.core.agent.prompt import build_system_prompt
from chisurf.core.agent.runtime import (
    AgentConfig,
    AgentResult,
    AgentSession,
    ToolInvocation,
    build_session,
)
from chisurf.core.agent.spec import (
    SAFETY_DANGEROUS,
    SAFETY_READ,
    SAFETY_WRITE,
    ToolError,
    ToolRegistry,
    ToolSpec,
)
from chisurf.core.agent.tools import build_default_registry

__all__ = [
    "AgentConfig",
    "AgentContext",
    "AgentResult",
    "AgentSession",
    "LLMClient",
    "LLMError",
    "LLMSettings",
    "SAFETY_DANGEROUS",
    "SAFETY_READ",
    "SAFETY_WRITE",
    "ToolError",
    "ToolInvocation",
    "ToolRegistry",
    "ToolSpec",
    "build_default_registry",
    "build_session",
    "build_system_prompt",
]
