"""Cross-provider conversation shape.

The agent echoes a provider's own assistant message back in the next request,
and providers validate *input* more strictly than they format *output*: a
``content: null`` next to ``tool_calls`` is emitted by several of them and
rejected by some on the way back in. These tests replay each provider's reply
shape through the loop and check that what leaves is portable — the kind of
dialect bug that otherwise only shows up mid-conversation against one vendor.
"""

from __future__ import annotations

import json

import pytest

from chisurf.core.agent import AgentSession, LLMClient, LLMSettings
from chisurf.core.agent.llm import LLMResponse, ToolCall


class ReplayLLM(LLMClient):
    """Replays raw provider messages, recording what is sent back."""

    def __init__(self, raw_messages):
        super().__init__(LLMSettings(base_url="http://test", model="m"))
        self.raw_messages = list(raw_messages)
        self.sent: list = []

    def complete(self, messages, tools=None):
        """Return the next canned provider message."""
        self.sent.append([dict(message) for message in messages])
        raw = self.raw_messages.pop(0)
        calls = [
            ToolCall(
                id=entry["id"],
                name=entry["function"]["name"],
                arguments=json.loads(entry["function"]["arguments"] or "{}"),
            )
            for entry in raw.get("tool_calls") or []
        ]
        return LLMResponse(
            text=raw.get("content") or "",
            tool_calls=calls,
            raw_message=raw,
        )


def _tool_call(call_id="abcdefghi", name="list_fits", arguments="{}"):
    """Return one provider-shaped tool call."""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


#: How the providers ChiSurf supports word the same assistant turn.
PROVIDER_REPLIES = {
    # OpenAI and OpenRouter: content is null next to tool_calls.
    "openai": {"role": "assistant", "content": None, "tool_calls": [_tool_call()]},
    # Mistral: nine-character ids, and a reasoning-ish extra field.
    "mistral": {
        "role": "assistant",
        "content": None,
        "tool_calls": [_tool_call(call_id="Xy9aBc123")],
        "prefix": False,
    },
    # A provider that returns an empty string instead of null.
    "empty-string": {"role": "assistant", "content": "", "tool_calls": [_tool_call()]},
}


@pytest.mark.parametrize("provider", sorted(PROVIDER_REPLIES))
def test_the_echoed_assistant_turn_is_portable(context, provider):
    reply = PROVIDER_REPLIES[provider]
    agent = AgentSession(
        ReplayLLM([reply, {"role": "assistant", "content": "done"}]), context=context
    )
    agent.ask("list the fits")

    echoed = next(m for m in agent.messages if m.get("role") == "assistant")
    assert echoed["content"] is not None, "a null content is rejected by some providers"
    assert echoed["tool_calls"] == reply["tool_calls"], "tool call ids must round-trip"
    assert "prefix" not in echoed, "response-only fields must not be sent back"
    assert set(echoed) <= {"role", "content", "tool_calls", "name"}


@pytest.mark.parametrize("provider", sorted(PROVIDER_REPLIES))
def test_the_tool_result_references_the_providers_own_id(context, provider):
    reply = PROVIDER_REPLIES[provider]
    agent = AgentSession(
        ReplayLLM([reply, {"role": "assistant", "content": "done"}]), context=context
    )
    agent.ask("list the fits")

    tool_message = next(m for m in agent.messages if m.get("role") == "tool")
    assert tool_message["tool_call_id"] == reply["tool_calls"][0]["id"]
    json.loads(tool_message["content"])


def test_a_plain_answer_is_also_normalised(context):
    """A final turn is echoed too, and must be just as portable."""
    agent = AgentSession(
        ReplayLLM([{"role": "assistant", "content": None, "annotations": []}]),
        context=context,
    )
    result = agent.ask("hello")
    assert result.text == ""
    echoed = agent.messages[-1]
    assert echoed == {"role": "assistant", "content": ""}


def test_the_whole_conversation_is_json_serialisable(context):
    """Whatever ends up in `messages` is what gets posted."""
    agent = AgentSession(
        ReplayLLM(
            [
                PROVIDER_REPLIES["mistral"],
                {"role": "assistant", "content": "done"},
            ]
        ),
        context=context,
    )
    agent.ask("list the fits")
    json.dumps(agent.messages)
