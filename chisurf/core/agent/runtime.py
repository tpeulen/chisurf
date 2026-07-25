"""The ChiSurf agent loop.

An :class:`AgentSession` owns a conversation, a tool registry and an
:class:`~chisurf.core.agent.llm.LLMClient`, and runs the standard
observe-act loop: ask the model what to do, run the tools it asks for, feed
the results back, repeat until the model answers in prose.

Design decisions that matter for how well it behaves:

* **A failing tool is not the end of the run.**  The error text goes back to
  the model as the tool result, so it can correct the call.  Only repeated
  *identical* failures are cut short.
* **Several tool calls per turn.**  Models routinely batch independent calls
  ("load these five files"); executing them all in one turn keeps the loop
  short.
* **Budgets, not guesses.**  Steps, wall-clock time, and consecutive-failure
  counts are explicit and reported in the result.
* **The conversation survives across questions**, so follow-ups like "now fix
  the lifetime and refit" work without repeating context.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.llm import LLMClient, LLMError, LLMResponse, ToolCall
from chisurf.core.agent.prompt import (
    build_system_prompt,
    parse_text_protocol,
    text_protocol_prompt,
)
from chisurf.core.agent.spec import (
    SAFETY_DANGEROUS,
    ToolError,
    ToolRegistry,
    call_handler,
)
from chisurf.core.agent.tools import build_default_registry

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Limits and policy for one agent session.

    Parameters
    ----------
    max_steps : int
        Maximum number of model turns per question.
    max_tool_calls : int
        Maximum number of tool executions per question.
    time_budget_s : float
        Wall-clock budget per question.
    max_consecutive_failures : int
        Stop after this many tool failures in a row without a success.
    max_safety : str
        Highest safety tier the model may use.  Lower it to ``"write"`` to
        take away code execution, or to ``"read"`` for a look-but-don't-touch
        session.
    max_history_messages : int
        Conversation messages kept (besides the system prompt) before older
        turns are dropped.
    """

    max_steps: int = 24
    max_tool_calls: int = 60
    time_budget_s: float = 900.0
    max_consecutive_failures: int = 4
    max_safety: str = SAFETY_DANGEROUS
    max_history_messages: int = 80


@dataclass
class ToolInvocation:
    """Record of one executed tool call."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    result: dict[str, Any]
    elapsed_ms: int
    error: str | None = None


@dataclass
class AgentResult:
    """Outcome of one question put to the agent.

    Attributes
    ----------
    text : str
        The assistant's final answer.
    invocations : list of ToolInvocation
        Every tool executed while answering, in order.
    steps : int
        Number of model turns used.
    stop_reason : str
        ``"answer"``, ``"step_budget"``, ``"time_budget"``, ``"tool_budget"``,
        ``"repeated_failures"``, ``"cancelled"`` or ``"error"``.
    error : str, optional
        Set when ``stop_reason`` is ``"error"``.
    usage : dict
        Token accounting reported by the provider for the last call.
    """

    text: str = ""
    invocations: list[ToolInvocation] = field(default_factory=list)
    steps: int = 0
    stop_reason: str = "answer"
    error: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        """Whether the run finished with a real answer."""
        return self.stop_reason == "answer" and not self.error

    def tool_names(self) -> list[str]:
        """Return the names of the tools that were executed, in order."""
        return [invocation.name for invocation in self.invocations]


class AgentSession:
    """A conversation with the ChiSurf agent.

    Parameters
    ----------
    llm : LLMClient
        Chat-completion client.
    context : AgentContext, optional
        Execution context.  A default one rooted at the current directory is
        created when omitted.
    registry : ToolRegistry, optional
        Tools to expose.  Defaults to :func:`build_default_registry`.
    config : AgentConfig, optional
        Budgets and policy.
    extra_instructions : str
        Appended to the system prompt (host application context).
    """

    def __init__(
        self,
        llm: LLMClient,
        context: AgentContext | None = None,
        registry: ToolRegistry | None = None,
        config: AgentConfig | None = None,
        extra_instructions: str = "",
    ):
        self.llm = llm
        self.context = context or AgentContext()
        self.registry = registry or build_default_registry()
        self.config = config or AgentConfig()
        self.extra_instructions = extra_instructions
        self.messages: list[dict[str, Any]] = []
        self._cancelled = False

    # ── public API ────────────────────────────────────────────────────

    @property
    def native_tools(self) -> bool:
        """Whether tool schemas are sent through the provider's tool API."""
        return bool(self.llm.settings.supports_tools)

    def cancel(self) -> None:
        """Ask the running loop to stop after the current tool call."""
        self._cancelled = True

    def reset(self) -> None:
        """Forget the conversation (tools and context are kept)."""
        self.messages = []
        self._cancelled = False

    def ask(self, question: str) -> AgentResult:
        """Answer *question*, calling tools as needed.

        Parameters
        ----------
        question : str
            The user's request in plain language.

        Returns
        -------
        AgentResult
        """
        self._cancelled = False
        self._sync_system_prompt()
        self.messages.append({"role": "user", "content": str(question)})
        self.context.emit("agent.started", {"question": question})

        result = AgentResult()
        started = time.perf_counter()
        consecutive_failures = 0
        last_failure_signature: str | None = None

        while True:
            if self._cancelled:
                result.stop_reason = "cancelled"
                break
            if result.steps >= self.config.max_steps:
                result.stop_reason = "step_budget"
                break
            if time.perf_counter() - started > self.config.time_budget_s:
                result.stop_reason = "time_budget"
                break

            try:
                response = self._complete()
            except LLMError as error:
                result.stop_reason = "error"
                result.error = str(error)
                self.context.emit("agent.failed", {"error": str(error)})
                break

            result.steps += 1
            result.usage = response.usage
            calls = self._tool_calls(response)

            if not calls:
                result.text = self._final_text(response)
                self.context.emit("message.completed", {"content": result.text})
                break

            self._append_assistant(response, calls)

            for call in calls:
                if self._cancelled:
                    result.stop_reason = "cancelled"
                    break
                if len(result.invocations) >= self.config.max_tool_calls:
                    result.stop_reason = "tool_budget"
                    break

                invocation = self._execute(call)
                result.invocations.append(invocation)
                self._append_tool_result(call, invocation)

                if invocation.ok:
                    consecutive_failures = 0
                    last_failure_signature = None
                    continue

                signature = f"{call.name}:{json.dumps(call.arguments, sort_keys=True, default=str)}"
                consecutive_failures += 1
                if signature == last_failure_signature:
                    consecutive_failures += 1
                last_failure_signature = signature
                if consecutive_failures >= self.config.max_consecutive_failures:
                    result.stop_reason = "repeated_failures"
                    break

            if result.stop_reason != "answer":
                break

        if result.stop_reason != "answer" and not result.text:
            result.text = self._explain_stop(result)
        self.context.emit(
            "agent.completed",
            {
                "stop_reason": result.stop_reason,
                "steps": result.steps,
                "tools": result.tool_names(),
                "text": result.text,
            },
        )
        return result

    # ── model interaction ─────────────────────────────────────────────

    def _complete(self) -> LLMResponse:
        """Run one chat completion with the current conversation."""
        tools = self.registry.to_openai_tools(self.config.max_safety) if self.native_tools else None
        self._trim_history()
        return self.llm.complete(self.messages, tools)

    def _tool_calls(self, response: LLMResponse) -> list[ToolCall]:
        """Return the tool calls requested by *response*, in either protocol."""
        if self.native_tools:
            return response.tool_calls
        parsed = parse_text_protocol(response.text)
        if "tool" in parsed:
            return [
                ToolCall(
                    id=f"text_{int(time.time() * 1000)}",
                    name=parsed["tool"],
                    arguments=parsed.get("arguments", {}),
                )
            ]
        return []

    def _final_text(self, response: LLMResponse) -> str:
        """Return the assistant's prose answer and record it in the conversation."""
        if self.native_tools:
            text = response.text
            self.messages.append(response.raw_message or {"role": "assistant", "content": text})
        else:
            text = parse_text_protocol(response.text).get("answer", response.text)
            self.messages.append({"role": "assistant", "content": response.text})
        return text

    def _append_assistant(self, response: LLMResponse, calls: Sequence[ToolCall]) -> None:
        """Append the assistant turn that requested *calls*."""
        if self.native_tools and response.raw_message:
            self.messages.append(response.raw_message)
            return
        self.messages.append(
            {
                "role": "assistant",
                "content": response.text
                or json.dumps({"tool": calls[0].name, "arguments": calls[0].arguments}),
            }
        )

    def _append_tool_result(self, call: ToolCall, invocation: ToolInvocation) -> None:
        """Append the result of *call* in the protocol the model understands."""
        payload = json.dumps(invocation.result, default=str)[: self.context.max_result_chars]
        if self.native_tools:
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": payload,
                }
            )
        else:
            self.messages.append(
                {
                    "role": "user",
                    "content": f"Result of {call.name}:\n{payload}",
                }
            )

    def _sync_system_prompt(self) -> None:
        """Insert or refresh the system prompt with the current session state."""
        catalogue = "" if self.native_tools else self.registry.describe(self.config.max_safety)
        extra = self.extra_instructions
        if not self.native_tools:
            extra = "\n\n".join(filter(None, [extra, text_protocol_prompt(catalogue)]))
        prompt = build_system_prompt(
            datasets=self.context.datasets,
            fits=self.context.fits,
            working_directory=self.context.working_directory,
            tool_catalogue=catalogue,
            extra=extra,
        )
        message = {"role": "system", "content": prompt}
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0] = message
        else:
            self.messages.insert(0, message)

    def _trim_history(self) -> None:
        """Drop the oldest turns when the conversation outgrows its budget."""
        limit = self.config.max_history_messages
        if len(self.messages) <= limit + 1:
            return
        head = self.messages[:1] if self.messages[0].get("role") == "system" else []
        tail = self.messages[len(self.messages) - limit :]
        # A tool result whose assistant turn was dropped confuses the provider.
        while tail and tail[0].get("role") == "tool":
            tail = tail[1:]
        self.messages = head + tail

    # ── tool execution ────────────────────────────────────────────────

    def _execute(self, call: ToolCall) -> ToolInvocation:
        """Run one tool call, converting every failure into a readable result."""
        started = time.perf_counter()
        self.context.emit("tool.started", {"tool": call.name, "arguments": call.arguments})

        spec = self.registry.get(call.name)
        if spec is None:
            return self._failure(
                call,
                started,
                f"unknown tool {call.name!r}. Available tools: {self.registry.names()}",
            )
        if spec not in self.registry.filtered(self.config.max_safety):
            return self._failure(
                call,
                started,
                f"tool {call.name!r} is not permitted in this session",
            )
        if not call.arguments and call.raw_arguments.strip() not in ("", "{}"):
            return self._failure(
                call,
                started,
                f"could not parse the arguments for {call.name!r}: "
                f"{call.raw_arguments[:200]!r} is not a JSON object",
            )
        if spec.safety == SAFETY_DANGEROUS and self.context.confirm is not None:
            try:
                approved = bool(self.context.confirm(call.name, call.arguments))
            except Exception:
                logger.exception("confirmation callback failed")
                approved = False
            if not approved:
                return self._failure(
                    call, started, "the user declined this action", event="tool.denied"
                )

        try:
            result = call_handler(spec, self.context, call.arguments)
        except ToolError as error:
            return self._failure(call, started, str(error))
        except Exception as error:  # noqa: BLE001 - reported back to the model
            logger.debug("tool %s raised", call.name, exc_info=True)
            return self._failure(call, started, f"{type(error).__name__}: {error}")

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        invocation = ToolInvocation(
            name=call.name,
            arguments=call.arguments,
            ok=bool(result.get("ok", True)),
            result=result,
            elapsed_ms=elapsed_ms,
        )
        self.context.emit(
            "tool.completed",
            {
                "tool": call.name,
                "ok": invocation.ok,
                "elapsed_ms": elapsed_ms,
                "result": result,
            },
        )
        return invocation

    def _failure(
        self,
        call: ToolCall,
        started: float,
        message: str,
        event: str = "tool.failed",
    ) -> ToolInvocation:
        """Build (and announce) a failed :class:`ToolInvocation`."""
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        self.context.emit(event, {"tool": call.name, "error": message})
        return ToolInvocation(
            name=call.name,
            arguments=call.arguments,
            ok=False,
            result={"ok": False, "error": message},
            elapsed_ms=elapsed_ms,
            error=message,
        )

    # ── reporting ─────────────────────────────────────────────────────

    @staticmethod
    def _explain_stop(result: AgentResult) -> str:
        """Return a user-facing explanation for a run that did not finish."""
        reasons = {
            "step_budget": (
                "I stopped after using up my step budget. Tell me to continue "
                "if the task is not finished."
            ),
            "tool_budget": "I stopped after reaching the limit on tool calls for one request.",
            "time_budget": "I stopped because this request took too long.",
            "repeated_failures": (
                "I stopped because the same operation kept failing. The last "
                "error was: " + (result.invocations[-1].error or "unknown")
                if result.invocations
                else "I stopped because an operation kept failing."
            ),
            "cancelled": "Cancelled.",
            "error": f"I could not reach the language model: {result.error}",
        }
        return reasons.get(result.stop_reason, "I stopped before finishing.")


def build_session(
    provider: str | None = None,
    model: str | None = None,
    working_directory: str = ".",
    config: AgentConfig | None = None,
    context: AgentContext | None = None,
    **llm_overrides: Any,
) -> AgentSession:
    """Create a session from the stored ChiSurf AI provider settings.

    Parameters
    ----------
    provider : str, optional
        Provider key; defaults to the one selected in the AI settings.
    model : str, optional
        Model identifier override.
    working_directory : str
        Directory that relative paths in tool arguments resolve against.
    config : AgentConfig, optional
        Budgets and policy.
    context : AgentContext, optional
        Pre-built context (a GUI passes one carrying its confirm/event hooks).
    **llm_overrides
        Further :class:`~chisurf.core.agent.llm.LLMSettings` overrides.

    Returns
    -------
    AgentSession
    """
    from chisurf.core.agent.llm import LLMSettings

    settings = LLMSettings.from_provider(provider, model=model, **llm_overrides)
    if context is None:
        context = AgentContext(working_directory=working_directory)
    else:
        context.working_directory = working_directory or context.working_directory
    return AgentSession(LLMClient(settings), context=context, config=config)
