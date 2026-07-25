"""Tests for the chat-completion client (request shape, parsing, retries)."""

from __future__ import annotations

import json

import pytest

from chisurf.core.agent.llm import (
    LLMClient,
    LLMConfigurationError,
    LLMError,
    LLMSettings,
)


class FakeResponse:
    """Minimal stand-in for a ``requests`` response."""

    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        """Return the decoded body, mimicking ``requests``' behaviour."""
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    """Session that returns queued responses and records the requests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def post(self, url, headers=None, json=None, timeout=None):
        """Record the request and pop the next queued response."""
        self.requests.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def completion(content=None, tool_calls=None, usage=None):
    """Build an OpenAI-shaped chat-completion body."""
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message, "finish_reason": "stop"}],
        "usage": usage or {"total_tokens": 11},
    }


def client(responses, **settings):
    """Build a client backed by a :class:`FakeSession`."""
    defaults = {"base_url": "https://api.test/v1", "model": "test-model", "api_key": "k"}
    defaults.update(settings)
    session = FakeSession(responses)
    return LLMClient(LLMSettings(**defaults), session=session), session


# ── configuration ─────────────────────────────────────────────────────


def test_missing_model_is_a_configuration_error():
    with pytest.raises(LLMConfigurationError, match="model"):
        LLMSettings(base_url="https://api.test/v1").validate()


def test_missing_base_url_is_a_configuration_error():
    with pytest.raises(LLMConfigurationError, match="base URL"):
        LLMSettings(model="m").validate()


def test_openrouter_settings_come_from_the_provider_table(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    settings = LLMSettings.from_provider("openrouter")
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.api_key == "or-key"
    assert settings.extra_headers.get("X-Title") == "ChiSurf"


# ── request construction ──────────────────────────────────────────────


def test_tools_are_sent_when_the_model_supports_them():
    llm, session = client([FakeResponse(payload=completion("hi"))])
    tools = [{"type": "function", "function": {"name": "t", "description": "d", "parameters": {}}}]
    llm.complete([{"role": "user", "content": "hello"}], tools)
    body = session.requests[0]["json"]
    assert body["tools"] == tools
    assert body["tool_choice"] == "auto"
    assert body["model"] == "test-model"


def test_tools_are_omitted_for_models_without_tool_support():
    llm, session = client([FakeResponse(payload=completion("hi"))], supports_tools=False)
    llm.complete([{"role": "user", "content": "hello"}], [{"type": "function"}])
    assert "tools" not in session.requests[0]["json"]


def test_the_api_key_is_sent_as_a_bearer_token():
    llm, session = client([FakeResponse(payload=completion("hi"))])
    llm.complete([{"role": "user", "content": "x"}])
    assert session.requests[0]["headers"]["Authorization"] == "Bearer k"


def test_extra_headers_are_included():
    llm, session = client(
        [FakeResponse(payload=completion("hi"))], extra_headers={"X-Title": "ChiSurf"}
    )
    llm.complete([{"role": "user", "content": "x"}])
    assert session.requests[0]["headers"]["X-Title"] == "ChiSurf"


# ── response parsing ──────────────────────────────────────────────────


def test_tool_calls_are_parsed_into_structured_calls():
    payload = completion(
        tool_calls=[
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "load_data", "arguments": '{"directory": "d"}'},
            }
        ]
    )
    llm, _ = client([FakeResponse(payload=payload)])
    response = llm.complete([{"role": "user", "content": "x"}])
    assert response.wants_tools
    call = response.tool_calls[0]
    assert (call.id, call.name, call.arguments) == ("call_1", "load_data", {"directory": "d"})


def test_malformed_tool_arguments_are_kept_as_raw_text():
    payload = completion(
        tool_calls=[
            {"id": "c", "type": "function", "function": {"name": "run_fit", "arguments": "{oops"}}
        ]
    )
    llm, _ = client([FakeResponse(payload=payload)])
    call = llm.complete([{"role": "user", "content": "x"}]).tool_calls[0]
    assert call.arguments == {}
    assert call.raw_arguments == "{oops"


def test_empty_arguments_parse_to_an_empty_dict():
    payload = completion(
        tool_calls=[
            {"id": "c", "type": "function", "function": {"name": "list_fits", "arguments": ""}}
        ]
    )
    llm, _ = client([FakeResponse(payload=payload)])
    assert llm.complete([{"role": "user", "content": "x"}]).tool_calls[0].arguments == {}


def test_usage_is_accumulated():
    llm, _ = client(
        [
            FakeResponse(payload=completion("a", usage={"total_tokens": 10})),
            FakeResponse(payload=completion("b", usage={"total_tokens": 5})),
        ]
    )
    llm.complete([{"role": "user", "content": "x"}])
    llm.complete([{"role": "user", "content": "y"}])
    assert llm.total_tokens == 15


def test_a_provider_error_body_becomes_an_llm_error():
    llm, _ = client([FakeResponse(payload={"error": {"message": "model overloaded"}})])
    with pytest.raises(LLMError, match="model overloaded"):
        llm.complete([{"role": "user", "content": "x"}])


# ── failure handling ──────────────────────────────────────────────────


def test_rate_limits_are_retried_then_succeed(monkeypatch):
    monkeypatch.setattr(LLMClient, "_sleep", staticmethod(lambda attempt: None))
    llm, session = client(
        [
            FakeResponse(status_code=429, payload={"error": {"message": "slow down"}}),
            FakeResponse(payload=completion("finally")),
        ]
    )
    assert llm.complete([{"role": "user", "content": "x"}]).text == "finally"
    assert len(session.requests) == 2


def test_a_bad_key_is_explained_and_not_retried():
    llm, session = client(
        [FakeResponse(status_code=401, payload={"error": {"message": "invalid key"}})]
    )
    with pytest.raises(LLMError, match="Settings"):
        llm.complete([{"role": "user", "content": "x"}])
    assert len(session.requests) == 1


def test_an_unknown_model_is_explained():
    llm, _ = client(
        [FakeResponse(status_code=404, payload={"error": {"message": "no such model"}})]
    )
    with pytest.raises(LLMError, match="not available"):
        llm.complete([{"role": "user", "content": "x"}])


def test_network_failures_are_retried_then_reported(monkeypatch):
    monkeypatch.setattr(LLMClient, "_sleep", staticmethod(lambda attempt: None))
    llm, session = client([ConnectionError("boom")] * 4, max_retries=2)
    with pytest.raises(LLMError, match="cannot reach the model"):
        llm.complete([{"role": "user", "content": "x"}])
    assert len(session.requests) == 3


def test_a_non_json_body_is_reported_clearly():
    llm, _ = client([FakeResponse(status_code=200, payload=None, text="<html>")])
    with pytest.raises(LLMError, match="non-JSON"):
        llm.complete([{"role": "user", "content": "x"}])


def test_the_request_body_round_trips_as_json():
    llm, session = client([FakeResponse(payload=completion("hi"))])
    llm.complete([{"role": "user", "content": "x"}], [{"type": "function", "function": {}}])
    json.dumps(session.requests[0]["json"])
