"""Chat-completion client for the ChiSurf agent.

The client speaks the OpenAI ``/chat/completions`` dialect, which every
provider ChiSurf supports (OpenAI, Mistral, OpenRouter, Ollama, LM Studio and
anything else "OpenAI-compatible") understands.

Two things matter for agent quality and are handled here rather than in the
runtime:

* **native tool calling** -- the tool schemas are sent in the ``tools`` field
  and the model answers with structured ``tool_calls``.  A model asked to
  hand-write JSON in prose gets it wrong regularly; a model using the tool
  API essentially never does.
* **honest errors** -- an HTTP 401/429/500 is raised as an
  :class:`LLMError` instead of being turned into a chat message that the
  runtime then tries (and fails) to parse.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

#: HTTP statuses worth retrying: rate limits and transient server errors.
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


class LLMError(RuntimeError):
    """Raised when the language model cannot be reached or refuses the request."""


class LLMConfigurationError(LLMError):
    """Raised when the provider settings are incomplete (no key, URL or model)."""


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


#: A tool name is an identifier, per every provider's function-calling schema.
_TOOL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")


def is_tool_name(name: str) -> bool:
    """Return whether *name* could be a tool name rather than prose.

    Parameters
    ----------
    name : str
        The ``function.name`` a provider returned.

    Returns
    -------
    bool
    """
    return bool(_TOOL_NAME.match(str(name or "").strip()))


def message_text(content: Any) -> str:
    """Return the assistant's prose from a chat message's ``content``.

    Providers disagree on the shape. Most send a string; some send a list of
    typed chunks (``{"type": "text", "text": ...}`` beside references, images
    or thinking blocks). Stringifying the list put a Python repr in front of
    the user — a real answer arrived as
    ``[{'type': 'text', 'text': '...'}, {'type': 'reference', ...}]``.

    Parameters
    ----------
    content : object
        The ``content`` field of an assistant message.

    Returns
    -------
    str
        The text parts, in order, joined by newlines.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if isinstance(content, (list, tuple)):
        parts = [message_text(chunk) for chunk in content]
        return "\n".join(part for part in parts if part)
    return str(content)


@dataclass
class LLMResponse:
    """Normalised result of one chat-completion call.

    Attributes
    ----------
    text : str
        The assistant's prose, if any.
    tool_calls : list of ToolCall
        Tool invocations requested by the model.
    raw_message : dict
        The provider's assistant message, appended verbatim to the
        conversation so that tool-call ids line up on the next turn.
    usage : dict
        Token accounting as reported by the provider.
    finish_reason : str
        Provider-reported reason the generation stopped.
    """

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_message: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str = ""

    @property
    def wants_tools(self) -> bool:
        """Whether the model asked for at least one tool call."""
        return bool(self.tool_calls)


@dataclass
class LLMSettings:
    """Connection and sampling settings for one provider.

    Parameters
    ----------
    base_url : str
        API root, e.g. ``https://openrouter.ai/api/v1``.
    model : str
        Model identifier.
    api_key : str
        Bearer token.  May be empty for a local server.
    temperature, top_p : float
        Sampling controls.
    max_tokens : int
        Response length cap.
    timeout_s : float
        Per-request timeout.
    max_retries : int
        How often a retryable failure is retried (exponential backoff).
    supports_tools : bool
        Whether the model supports native tool calling.  When ``False`` the
        runtime falls back to the text protocol.
    extra_headers : dict
        Additional HTTP headers (OpenRouter attribution, for example).
    """

    base_url: str = ""
    model: str = ""
    api_key: str = ""
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 4096
    timeout_s: float = 120.0
    max_retries: int = 3
    supports_tools: bool = True
    extra_headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_provider(cls, provider: str | None = None, **overrides: Any) -> LLMSettings:
        """Build settings from the stored ChiSurf AI provider configuration.

        Parameters
        ----------
        provider : str, optional
            Provider key (``"openai"``, ``"openrouter"``, ``"mistral"``,
            ``"local"``, ``"custom"``).  Defaults to the selected provider.
        **overrides
            Fields to override, e.g. ``model="openai/gpt-4o-mini"``.

        Returns
        -------
        LLMSettings
        """
        from chisurf.core.settings import ai_settings

        stored = ai_settings.get_api_settings(provider)
        api_key = str(stored.get("api_key", "") or "").strip()
        if not api_key:
            api_key = ai_settings.get_provider_api_key(stored.get("provider", ""))
        settings = cls(
            base_url=str(stored.get("base_url", "") or "").strip().rstrip("/"),
            model=str(stored.get("text_model") or stored.get("model") or "").strip(),
            api_key=api_key,
            temperature=float(stored.get("temperature", 0.2) or 0.0),
            top_p=float(stored.get("top_p", 0.9) or 0.9),
            max_tokens=int(stored.get("max_tokens", 4096) or 4096),
        )
        if str(stored.get("provider", "")) == "openrouter":
            settings.extra_headers = {
                "HTTP-Referer": "https://github.com/fluorescence-tools/chisurf",
                "X-Title": "ChiSurf",
            }
        for key, value in overrides.items():
            if value is not None:
                setattr(settings, key, value)
        return settings

    def validate(self) -> None:
        """Raise :class:`LLMConfigurationError` when the settings are unusable."""
        missing = [
            name
            for name, value in (("base URL", self.base_url), ("model", self.model))
            if not value
        ]
        if missing:
            raise LLMConfigurationError(
                "AI provider is not configured: missing "
                + " and ".join(missing)
                + ". Set it in Settings → AI."
            )


class LLMClient:
    """Minimal, dependency-light chat-completion client.

    Parameters
    ----------
    settings : LLMSettings
        Connection settings.
    session : object, optional
        A ``requests``-compatible session, injected by tests.
    """

    def __init__(self, settings: LLMSettings, session: Any = None):
        self.settings = settings
        self._session = session
        self.last_usage: dict[str, Any] = {}
        self.total_tokens: int = 0

    # ── request construction ──────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        """Return the HTTP headers for a completion request."""
        headers = {"Content-Type": "application/json"}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        headers.update(self.settings.extra_headers)
        return headers

    def build_payload(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Return the JSON body for a chat-completion request.

        Parameters
        ----------
        messages : sequence of dict
            Conversation in OpenAI message format.
        tools : sequence of dict, optional
            Tool definitions; omitted when the model has no tool support.

        Returns
        -------
        dict
        """
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": list(messages),
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            "max_tokens": self.settings.max_tokens,
        }
        if tools and self.settings.supports_tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"
        return payload

    # ── response parsing ──────────────────────────────────────────────

    @staticmethod
    def parse_response(data: dict[str, Any]) -> LLMResponse:
        """Convert a provider response body into an :class:`LLMResponse`.

        Malformed ``tool_calls`` arguments are reported through
        :class:`ToolCall.raw_arguments` with an empty ``arguments`` dict, so
        the runtime can hand the model a precise error instead of crashing.

        Parameters
        ----------
        data : dict
            Decoded JSON body.

        Returns
        -------
        LLMResponse
        """
        choices = data.get("choices") or []
        if not choices:
            error = data.get("error")
            if error:
                message = error.get("message") if isinstance(error, dict) else str(error)
                raise LLMError(f"provider returned an error: {message}")
            raise LLMError("provider returned no choices")
        choice = choices[0]
        message = choice.get("message") or {}
        calls: list[ToolCall] = []
        stray: list[str] = []
        for entry in message.get("tool_calls") or []:
            function = entry.get("function") or {}
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments) if raw_arguments.strip() else {}
            except (TypeError, ValueError, AttributeError):
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}
            name = str(function.get("name") or "")
            if not is_tool_name(name):
                # Providers sometimes put a sentence where the tool name goes.
                # Dispatching it wastes a turn on "unknown tool <paragraph>"
                # and leaves the prose out of the answer; it is the model
                # talking, so treat it as such.
                stray.append(name)
                continue
            calls.append(
                ToolCall(
                    id=str(entry.get("id") or f"call_{len(calls)}"),
                    name=name,
                    arguments=arguments,
                    raw_arguments=str(raw_arguments),
                )
            )
        text = message_text(message.get("content"))
        if stray:
            text = "\n".join(part for part in [text, *stray] if part)
        return LLMResponse(
            text=text,
            tool_calls=calls,
            raw_message=message,
            usage=data.get("usage") or {},
            finish_reason=str(choice.get("finish_reason") or ""),
        )

    # ── transport ─────────────────────────────────────────────────────

    def complete(
        self,
        messages: Sequence[dict[str, Any]],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Run one chat completion, retrying transient failures.

        Parameters
        ----------
        messages : sequence of dict
            Conversation so far.
        tools : sequence of dict, optional
            Tool definitions to expose to the model.

        Returns
        -------
        LLMResponse

        Raises
        ------
        LLMError
            On configuration problems, non-retryable HTTP errors, or after the
            retry budget is exhausted.
        """
        self.settings.validate()
        payload = self.build_payload(messages, tools)
        url = f"{self.settings.base_url}/chat/completions"

        last_error: str | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._post(url, payload)
            except Exception as error:  # network-level failure
                last_error = f"{type(error).__name__}: {error}"
                logger.debug("LLM request failed (attempt %d)", attempt + 1, exc_info=True)
                if attempt >= self.settings.max_retries:
                    raise LLMError(f"cannot reach the model at {url}: {last_error}") from error
                self._sleep(attempt)
                continue

            status = int(getattr(response, "status_code", 0))
            if status == 200:
                try:
                    data = response.json()
                except Exception as error:
                    raise LLMError(f"provider sent a non-JSON response: {error}") from error
                parsed = self.parse_response(data)
                self.last_usage = parsed.usage
                self.total_tokens += int(parsed.usage.get("total_tokens", 0) or 0)
                return parsed

            body = self._error_body(response)
            if status in RETRYABLE_STATUS and attempt < self.settings.max_retries:
                logger.info("LLM HTTP %s, retrying (attempt %d)", status, attempt + 1)
                self._sleep(attempt)
                last_error = f"HTTP {status}: {body}"
                continue
            raise LLMError(self._explain_status(status, body))

        raise LLMError(f"model request failed after retries: {last_error}")

    def _post(self, url: str, payload: dict[str, Any]) -> Any:
        """POST *payload* to *url* and return the HTTP response object."""
        session = self._session
        if session is None:
            import requests

            session = requests
        return session.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=self.settings.timeout_s,
        )

    @staticmethod
    def _error_body(response: Any) -> str:
        """Return a short, readable body from a failed HTTP response."""
        try:
            data = response.json()
        except Exception:
            return str(getattr(response, "text", ""))[:500]
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error)[:500]
            if error:
                return str(error)[:500]
        return json.dumps(data)[:500]

    def _explain_status(self, status: int, body: str) -> str:
        """Turn an HTTP status into an actionable message."""
        if status in (401, 403):
            return (
                f"the API key for {self.settings.base_url} was rejected "
                f"(HTTP {status}). Check the key in Settings → AI. {body}"
            )
        if status == 404:
            return (
                f"model {self.settings.model!r} is not available at "
                f"{self.settings.base_url} (HTTP 404). {body}"
            )
        if status == 402:
            # Providers reserve `max_tokens` up front, so a large reservation
            # is refused on a low balance even when the answer would be
            # short. Lowering it is the lever the user has in ChiSurf.
            return (
                f"the provider refused the request for lack of credit "
                f"(HTTP 402). The reservation is your max_tokens setting "
                f"({self.settings.max_tokens}); lower it in Settings → AI, or "
                f"top up the account. {body}"
            )
        if status == 429:
            return f"the provider is rate-limiting this key (HTTP 429). {body}"
        return f"model request failed with HTTP {status}: {body}"

    @staticmethod
    def _sleep(attempt: int) -> None:
        """Sleep with exponential backoff and jitter before a retry."""
        time.sleep(min(8.0, (2**attempt) * 0.5) + random.random() * 0.25)
