"""Tool descriptions and registry for the ChiSurf LLM agent.

A :class:`ToolSpec` carries everything a language model needs in order to
call a ChiSurf operation correctly: a name, a prose description, a JSON
Schema for its arguments, and a safety tier.  The specs are handed to the
model verbatim (as OpenAI-style function definitions), which is what lets a
model pick the right call and fill in its arguments instead of guessing RPC
method names.

The registry is deliberately independent of the transport: a tool handler is
a plain Python callable that receives an :class:`~chisurf.core.agent.context.AgentContext`
and keyword arguments, and returns a JSON-serialisable dict.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


#: Tools that only read state and can always run unattended.
SAFETY_READ = "read"
#: Tools that change the ChiSurf session (load data, fit, edit parameters).
SAFETY_WRITE = "write"
#: Tools that can touch anything on the machine and need explicit consent.
SAFETY_DANGEROUS = "dangerous"

_SAFETY_ORDER = {SAFETY_READ: 0, SAFETY_WRITE: 1, SAFETY_DANGEROUS: 2}


class ToolError(Exception):
    """Raised by a tool handler to report a clean, model-readable failure.

    The message is fed back to the model as the tool result, so it should say
    what went wrong *and* what to do instead.
    """


@dataclass
class ToolSpec:
    """Description of a single agent-callable operation.

    Parameters
    ----------
    name : str
        Tool name as exposed to the model (``snake_case``).
    description : str
        Prose description.  The first line should say what the tool does; the
        remainder may describe when to use it and what it returns.
    parameters : dict
        JSON Schema (``type: object``) describing the arguments.
    handler : callable
        ``handler(context, **arguments) -> dict``.
    safety : str
        One of :data:`SAFETY_READ`, :data:`SAFETY_WRITE`,
        :data:`SAFETY_DANGEROUS`.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    handler: Callable[..., dict[str, Any]]
    safety: str = SAFETY_READ

    def to_openai_tool(self) -> dict[str, Any]:
        """Return the OpenAI ``tools`` entry describing this tool.

        Returns
        -------
        dict
            ``{"type": "function", "function": {...}}``.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description.strip(),
                "parameters": self.parameters,
            },
        }

    def validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """Check *arguments* against the schema and drop unknown keys.

        Only the parts of JSON Schema that models actually get wrong are
        enforced: required keys must be present, and unknown keys are removed
        rather than passed on to the handler (a stray argument would raise an
        unhelpful ``TypeError``).

        Parameters
        ----------
        arguments : dict
            Arguments as produced by the model.

        Returns
        -------
        dict
            The cleaned arguments.

        Raises
        ------
        ToolError
            When a required argument is missing.
        """
        if not isinstance(arguments, dict):
            raise ToolError(
                f"arguments for '{self.name}' must be a JSON object, got {type(arguments).__name__}"
            )
        properties = self.parameters.get("properties", {}) or {}
        required = self.parameters.get("required", []) or []
        missing = [key for key in required if key not in arguments]
        if missing:
            raise ToolError(
                f"missing required argument(s) {missing} for '{self.name}'. "
                f"Expected arguments: {sorted(properties)}"
            )
        unknown = [key for key in arguments if key not in properties]
        cleaned = {key: value for key, value in arguments.items() if key in properties}
        if unknown:
            logger.debug("tool %s: dropping unknown arguments %s", self.name, unknown)
        return cleaned


@dataclass
class ToolRegistry:
    """Collection of :class:`ToolSpec` objects addressable by name."""

    tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> ToolSpec:
        """Add *spec* to the registry, replacing any tool of the same name."""
        self.tools[spec.name] = spec
        return spec

    def add(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any] | None = None,
        safety: str = SAFETY_READ,
    ) -> Callable[[Callable[..., dict[str, Any]]], Callable[..., dict[str, Any]]]:
        """Return a decorator registering the wrapped function as a tool.

        Parameters
        ----------
        name : str
            Tool name.
        description : str
            Prose description handed to the model.
        parameters : dict, optional
            JSON Schema for the arguments.  Defaults to "no arguments".
        safety : str
            Safety tier.

        Returns
        -------
        callable
            Decorator that registers and returns the function unchanged.
        """
        schema = parameters or {"type": "object", "properties": {}}
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})

        def decorator(func: Callable[..., dict[str, Any]]):
            """Register *func* under *name* and return it unchanged."""
            self.register(
                ToolSpec(
                    name=name,
                    description=description or (func.__doc__ or ""),
                    parameters=schema,
                    handler=func,
                    safety=safety,
                )
            )
            return func

        return decorator

    def get(self, name: str) -> ToolSpec | None:
        """Return the tool named *name*, or ``None``."""
        return self.tools.get(name)

    def names(self) -> list[str]:
        """Return all registered tool names, sorted."""
        return sorted(self.tools)

    def filtered(self, max_safety: str = SAFETY_DANGEROUS) -> list[ToolSpec]:
        """Return the tools at or below a safety tier, sorted by name.

        Parameters
        ----------
        max_safety : str
            Highest tier to include.

        Returns
        -------
        list of ToolSpec
        """
        ceiling = _SAFETY_ORDER.get(max_safety, 2)
        return [
            spec
            for spec in sorted(self.tools.values(), key=lambda s: s.name)
            if _SAFETY_ORDER.get(spec.safety, 2) <= ceiling
        ]

    def to_openai_tools(self, max_safety: str = SAFETY_DANGEROUS) -> list[dict[str, Any]]:
        """Return OpenAI ``tools`` definitions for the permitted tools."""
        return [spec.to_openai_tool() for spec in self.filtered(max_safety)]

    def describe(self, max_safety: str = SAFETY_DANGEROUS) -> str:
        """Return a compact text catalogue of the permitted tools.

        Used by the text-protocol fallback for models without native tool
        calling, and by the ``--list-tools`` CLI flag.
        """
        lines: list[str] = []
        for spec in self.filtered(max_safety):
            summary = spec.description.strip().splitlines()[0]
            properties = spec.parameters.get("properties", {}) or {}
            required = set(spec.parameters.get("required", []) or [])
            args = ", ".join(
                f"{key}{'' if key in required else '?'}: {value.get('type', 'any')}"
                for key, value in properties.items()
            )
            lines.append(f"- {spec.name}({args}) — {summary}")
        return "\n".join(lines)

    def merge(self, other: ToolRegistry) -> ToolRegistry:
        """Return a new registry containing this registry's tools plus *other*'s."""
        merged = ToolRegistry(dict(self.tools))
        merged.tools.update(other.tools)
        return merged


def call_handler(
    spec: ToolSpec,
    context: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Invoke a tool handler with validated arguments.

    Parameters
    ----------
    spec : ToolSpec
        The tool to run.
    context : AgentContext
        Execution context handed to the handler as its first argument.
    arguments : dict
        Raw arguments from the model.

    Returns
    -------
    dict
        The handler result, always a dict carrying an ``ok`` key.
    """
    cleaned = spec.validate_arguments(arguments)
    signature = inspect.signature(spec.handler)
    if "context" in signature.parameters:
        result = spec.handler(context=context, **cleaned)
    else:
        result = spec.handler(**cleaned)
    if not isinstance(result, dict):
        return {"ok": True, "result": result}
    result.setdefault("ok", True)
    return result


def tool_names(specs: Iterable[ToolSpec]) -> list[str]:
    """Return the names of *specs*, sorted."""
    return sorted(spec.name for spec in specs)
