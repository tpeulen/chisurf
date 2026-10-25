"""The session the agent panel drives: the full tool registry, live context.

The command line and this panel share one construction; the difference is the
context — here it is the running application's working directory, so file
tools and the burst chain act on what the user sees.
"""

from __future__ import annotations

from typing import Any

#: The panel's step budget. An interactive session wants an answer within a
#: coffee sip, not an overnight run; ``run_python`` pipelines can be long, so
#: this is a floor to raise per request, not a ceiling to fight.
MAX_STEPS = 40


def build_context() -> Any:
    """The live application context: the session's working directory."""
    from chisurf.core.agent.context import AgentContext

    return AgentContext(working_directory=".")


def build_session(model: str = "", provider: str = "", **overrides: Any):
    """Create the workflow session the panel talks to.

    Parameters
    ----------
    model : str
        Model identifier override; the configured default when empty.
    provider : str
        Provider key override (e.g. ``"zai"``); the selected provider when
        empty. Keys come from the environment or the stored AI settings —
        never from the panel.
    **overrides
        Further LLM settings overrides.

    Returns
    -------
    AgentSession
    """
    from chisurf.core.agent.llm import LLMClient, LLMSettings
    from chisurf.core.agent.runtime import AgentConfig, AgentSession
    from chisurf.core.agent.spec import SAFETY_WRITE
    from chisurf.core.agent.tools import build_default_registry

    settings = LLMSettings.from_provider(provider or None, model=model or None, **overrides)
    config = AgentConfig(
        max_steps=MAX_STEPS,
        max_tool_calls=MAX_STEPS * 2,
        # Read and write tools run; destructive (dangerous) operations stay
        # out of the panel until the user deliberately widens the tier.
        max_safety=SAFETY_WRITE,
        auto_load_skills=True,
    )
    return AgentSession(
        LLMClient(settings),
        registry=build_default_registry(),
        config=config,
        context=build_context(),
    )


def build_registry():
    """The registry the panel exposes (the default one, unmodified)."""
    from chisurf.core.agent.tools import build_default_registry

    return build_default_registry()
