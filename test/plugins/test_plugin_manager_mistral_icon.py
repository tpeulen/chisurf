"""Tests for Mistral-backed plugin icon generation.

Icon generation talks to a provider through :mod:`chisurf.core.http`, the
in-tree HTTP client that replaced the ``requests`` dependency. These tests used
to stub ``sys.modules["requests"]`` instead, which the production code no longer
imports -- so they passed a ``requests_module`` argument the helpers had
dropped, and the ones that got past that reached the *real* api.mistral.ai.
Everything here therefore patches :func:`chisurf.core.http.post` and
:func:`chisurf.core.http.get`, the seam actually used.

The helpers now live in :mod:`chisurf.plugins.core.plugin_manager.api.icons` as
ordinary functions over an :class:`~...api.icons.IconConfig`. They used to be
methods on the manager widget, which is why these tests bound unbound methods to
a ``SimpleNamespace`` carrying fake Qt line edits -- that scaffolding is gone.
"""

from types import SimpleNamespace

import pytest

from chisurf.core import http
from chisurf.plugins.core.plugin_manager import AIIconRateLimitError
from chisurf.plugins.core.plugin_manager.api import icons


def _no_network(monkeypatch, post=None, get=None):
    """Point the HTTP client at the given doubles and forbid anything else."""

    def _forbidden(kind):
        def call(url, **kwargs):
            raise AssertionError(f"unexpected HTTP {kind} to {url}")

        return call

    monkeypatch.setattr(http, "post", post or _forbidden("POST"))
    monkeypatch.setattr(http, "get", get or _forbidden("GET"))


class _Response:
    """Small requests response double used by icon generation tests."""

    def __init__(self, status_code=200, payload=None, content=b"", text="", headers=None):
        """Store response attributes consumed by the production code."""
        self.status_code = status_code
        self._payload = payload or {}
        self.content = content
        self.text = text
        self.headers = headers or {}

    def json(self):
        """Return the configured JSON payload."""
        return self._payload

    def raise_for_status(self):
        """Raise an HTTP-like error for failing status codes."""
        if self.status_code >= 400:
            raise RuntimeError(f"{self.status_code}: {self.text}")


def _config(endpoint="https://api.mistral.ai/v1/beta", provider="mistral"):
    """The generation settings the helpers read."""
    return icons.IconConfig(
        provider=provider, endpoint=endpoint, model="mistral-medium-latest"
    )


@pytest.fixture(autouse=True)
def _stub_api_key(monkeypatch):
    """Keep the tests off the real AI Settings store.

    The prompt builder is deliberately *not* stubbed here -- one test checks the
    real template, and a blanket stub would have made it pass vacuously.
    """
    monkeypatch.setattr(icons, "api_key_for_provider", lambda _provider: "test-key")


def test_mistral_icon_generation_uses_stable_v1_endpoints(monkeypatch):
    """Mistral icon generation should strip stale beta suffixes from endpoints."""
    calls = []

    def post(url, **kwargs):
        calls.append(("POST", url, kwargs.get("json")))
        if url.endswith("/agents"):
            return _Response(payload={"id": "agent-123"})
        return _Response(
            payload={
                "outputs": [
                    {
                        "content": [
                            {
                                "type": "tool_file",
                                "file_id": "file-123",
                                "file_type": "png",
                            }
                        ]
                    }
                ]
            }
        )

    def get(url, **kwargs):
        calls.append(("GET", url, None))
        return _Response(content=b"png-bytes")

    _no_network(monkeypatch, post=post, get=get)

    image_bytes = icons.request_mistral_generated_icon_bytes(
        _config(), {"name": "Demo"}, prompt="make an icon"
    )

    assert image_bytes == b"png-bytes"
    assert [call[1] for call in calls] == [
        "https://api.mistral.ai/v1/agents",
        "https://api.mistral.ai/v1/conversations",
        "https://api.mistral.ai/v1/files/file-123/content",
    ]
    assert calls[1][2]["stream"] is False


def test_openai_compatible_icon_generation_retries_without_response_format(monkeypatch):
    """OpenAI-compatible image fallback should not force legacy response_format."""
    calls = []
    config = icons.IconConfig(
        provider="custom", endpoint="https://api.example.test/v1", model="image-model"
    )

    def post(url, **kwargs):
        payload = kwargs.get("json") or {}
        calls.append(payload)
        if len(calls) == 1:
            return _Response(status_code=400, text="unknown output_format")
        if "response_format" in payload:
            return _Response(status_code=400, text="Unknown parameter: response_format")
        return _Response(payload={"data": [{"b64_json": "cG5nLWJ5dGVz"}]})

    _no_network(monkeypatch, post=post)

    image_bytes = icons.request_openai_compatible_icon_bytes(
        config, {"name": "Demo"}, prompt="make an icon"
    )

    assert image_bytes == b"png-bytes"
    assert calls[0]["output_format"] == "png"
    assert "output_format" not in calls[1]
    assert "response_format" not in calls[1]


def test_openai_compatible_icon_generation_passes_api_key(monkeypatch):
    """OpenAI-compatible image requests should include the configured API key."""
    captured = {}
    monkeypatch.setattr(icons, "api_key_for_provider", lambda _provider: "sk-test-key")
    config = icons.IconConfig(
        provider="openai", endpoint="https://api.example.test/v1", model="gpt-image-2"
    )

    def post(url, **kwargs):
        captured.update(kwargs)
        return _Response(payload={"data": [{"b64_json": "cG5nLWJ5dGVz"}]})

    _no_network(monkeypatch, post=post)

    image_bytes = icons.request_openai_compatible_icon_bytes(
        config, {"name": "Demo"}, prompt="make an icon"
    )

    assert image_bytes == b"png-bytes"
    assert captured["headers"]["Authorization"] == "Bearer sk-test-key"


def test_openai_icon_defaults_ignore_text_model_for_image_generation():
    """OpenAI image defaults should not reuse a text model as the image model."""
    endpoint, model = icons.default_icon_generation_values("openai")

    assert endpoint == "https://api.openai.com/v1"
    assert model == "gpt-image-2"


def test_mistral_icon_generation_falls_back_to_file_download(monkeypatch):
    """Mistral file retrieval should tolerate download endpoints."""
    calls = []

    def post(url, **kwargs):
        calls.append(("POST", url))
        if url.endswith("/agents"):
            return _Response(payload={"id": "agent-123"})
        return _Response(payload={"file_id": "file-123", "file_type": "png"})

    def get(url, **kwargs):
        calls.append(("GET", url))
        if url.endswith("/content"):
            return _Response(status_code=404, text="not found")
        return _Response(content=b"downloaded-png")

    _no_network(monkeypatch, post=post, get=get)

    image_bytes = icons.request_mistral_generated_icon_bytes(
        _config("https://api.mistral.ai/v1"),
        {"name": "Demo"},
        prompt="make an icon",
    )

    assert image_bytes == b"downloaded-png"
    assert calls[-2:] == [
        ("GET", "https://api.mistral.ai/v1/files/file-123/content"),
        ("GET", "https://api.mistral.ai/v1/files/file-123/download"),
    ]


def test_ai_icon_prompt_uses_scientific_template():
    """AI icon prompts should follow the configured scientific icon template."""
    prompt = icons.ai_icon_prompt(
        {
            "name": "FCS:Correlation",
            "doc": "Analyze fluorescence correlation spectroscopy curves.\nAdditional details.",
        }
    )

    assert prompt.startswith("Scientific Software Icon Template")
    assert "Square icon, 128x128 pixels" in prompt
    assert "Plugin: FCS:Correlation" in prompt
    assert "Analyze fluorescence correlation spectroscopy curves." in prompt
    assert "correlation curve + confocal detection spot" in prompt
    assert "Negative prompts" in prompt


def test_mistral_post_retries_429_with_retry_after(monkeypatch):
    """Mistral POST helper should retry rate limits before returning."""
    calls = []
    sleeps = []

    def post(url, **kwargs):
        calls.append(url)
        if len(calls) == 1:
            return _Response(status_code=429, text="rate limited", headers={"Retry-After": "0.25"})
        return _Response(payload={"ok": True})

    monkeypatch.setattr("time.sleep", lambda delay: sleeps.append(delay))
    _no_network(monkeypatch, post=post)

    response = icons.post_mistral_json_with_retries(
        "https://api.mistral.ai/v1",
        "conversations",
        headers={},
        payload={},
        timeout=1,
    )

    assert response.json() == {"ok": True}
    assert calls == [
        "https://api.mistral.ai/v1/conversations",
        "https://api.mistral.ai/v1/conversations",
    ]
    assert sleeps == [0.25]


def test_mistral_post_raises_clear_error_after_429_retries(monkeypatch):
    """Mistral POST helper should raise a provider-specific error after retrying."""
    calls = []

    def post(url, **kwargs):
        calls.append(url)
        return _Response(status_code=429, text="rate limited")

    monkeypatch.setattr("time.sleep", lambda _delay: None)
    _no_network(monkeypatch, post=post)

    with pytest.raises(AIIconRateLimitError, match="429 Too Many Requests"):
        icons.post_mistral_json_with_retries(
            "https://api.mistral.ai/v1",
            "conversations",
            headers={},
            payload={},
            timeout=1,
        )

    assert len(calls) == 3
