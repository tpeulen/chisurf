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


# ── a rejected tool call must not survive in the echoed turn ──────────


class BodyReplayLLM(LLMClient):
    """Replays raw provider *response bodies* through the real parser."""

    def __init__(self, bodies):
        super().__init__(LLMSettings(base_url="http://test", model="m"))
        self.bodies = list(bodies)

    def complete(self, messages, tools=None):
        """Parse the next canned response body exactly as the transport would."""
        return self.parse_response(self.bodies.pop(0))


def _body(message):
    """Return a chat-completion body carrying *message*."""
    return {"choices": [{"message": message, "finish_reason": "stop"}], "usage": {}}


def _prose_name():
    """Return a tool call whose ``function.name`` is a sentence, not a name."""
    return _tool_call(call_id="call_abc", name="I will now list the plugins for you")


def test_a_prose_tool_name_is_dropped_from_the_echoed_message():
    """A call the parser rejects must not stay in the message sent back.

    ``raw_message`` is echoed verbatim into the next request, so an entry the
    parser refused to dispatch leaves a ``tool_call`` id that no ``tool``
    message answers — which providers reject.
    """
    response = LLMClient.parse_response(
        _body({"role": "assistant", "content": None, "tool_calls": [_prose_name()]})
    )

    assert response.tool_calls == []
    assert response.text == "I will now list the plugins for you"
    assert "tool_calls" not in response.raw_message


def test_a_valid_call_beside_a_prose_one_keeps_only_the_valid_entry():
    response = LLMClient.parse_response(
        _body(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [_prose_name(), _tool_call(call_id="call_ok")],
            }
        )
    )

    assert [call.id for call in response.tool_calls] == ["call_ok"]
    assert [entry["id"] for entry in response.raw_message["tool_calls"]] == ["call_ok"]


def test_well_formed_tool_calls_are_echoed_unchanged():
    message = {"role": "assistant", "content": None, "tool_calls": [_tool_call()]}
    response = LLMClient.parse_response(_body(message))

    assert response.raw_message["tool_calls"] == message["tool_calls"]


def test_every_tool_call_id_in_the_conversation_is_answered(context):
    """The invariant `_answer_unrun_calls` exists to hold, end to end."""
    agent = AgentSession(
        BodyReplayLLM(
            [_body({"role": "assistant", "content": None, "tool_calls": [_prose_name()]})]
        ),
        context=context,
    )
    agent.ask("list the plugins")

    requested = {
        entry["id"] for message in agent.messages for entry in message.get("tool_calls") or []
    }
    answered = {
        message["tool_call_id"] for message in agent.messages if message.get("role") == "tool"
    }
    assert requested == answered, "an unanswered tool_call id poisons every later question"
