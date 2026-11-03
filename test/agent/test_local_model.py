"""The on-device default model: provider defaults, server command, client wiring.

None of these need a model; the end-to-end proof against a running LFM3 is
``test_live_llm.py`` with ``CHISURF_AGENT_TEST_PROVIDER=local``.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent import LLMClient, LLMSettings, local_model
from chisurf.core.settings import ai_settings


@pytest.fixture()
def no_saved_settings(tmp_path, monkeypatch):
    """Point the AI settings file at an empty temporary directory."""
    monkeypatch.setattr(ai_settings, "_get_settings_path", lambda: tmp_path / "ai.json")


def test_a_fresh_install_runs_lfm3_on_this_computer(no_saved_settings):
    """No account, no key: the default is the on-device model."""
    settings = ai_settings.get_api_settings()
    assert settings["provider"] == ai_settings.DEFAULT_PROVIDER == "local"
    assert settings["text_model"] == local_model.LFM3_MODEL
    assert local_model.is_local_url(settings["base_url"])
    assert next(iter(ai_settings.PROVIDERS.values()))[0] == "local", "listed first"


def test_the_local_client_sends_liquids_sampling(no_saved_settings):
    """top_k and repeat_penalty reach llama-server; hosted APIs never see them."""
    local = LLMSettings.from_provider("local")
    payload = LLMClient(local).build_payload([{"role": "user", "content": "hi"}])
    assert payload["temperature"] == pytest.approx(0.1)
    assert payload["top_k"] == 50
    assert payload["repeat_penalty"] == pytest.approx(1.1)
    assert local.managed_server

    hosted = LLMSettings.from_provider("mistral")
    payload = LLMClient(hosted).build_payload([{"role": "user", "content": "hi"}])
    assert "top_k" not in payload and "repeat_penalty" not in payload
    assert not hosted.managed_server


def test_sampling_and_server_choice_survive_a_save(no_saved_settings):
    """The settings window must not strip the local-only fields on save."""
    stored = ai_settings.get_api_settings("local")
    stored.update(top_k=20, manage_server=False)
    assert ai_settings.save_api_settings(stored, "local")
    reloaded = ai_settings.get_api_settings("local")
    assert reloaded["top_k"] == 20
    assert reloaded["manage_server"] is False
    assert not LLMSettings.from_provider("local").managed_server


def test_a_remote_address_is_never_managed(no_saved_settings):
    """ChiSurf starts servers on loopback only."""
    stored = ai_settings.get_api_settings("local")
    stored["base_url"] = "http://gpu-box.lab:8080/v1"
    ai_settings.save_api_settings(stored, "local")
    assert not LLMSettings.from_provider("local").managed_server
    assert local_model.ensure_server("http://gpu-box.lab:8080/v1") is False


def test_the_server_command_parses_tool_calls_and_binds_loopback():
    """Without --jinja LFM3's XML tool calls arrive as prose."""
    command = local_model.server_command(binary="/bin/llama-server")
    assert command[:3] == ["/bin/llama-server", "-hf", local_model.LFM3_MODEL]
    assert "--jinja" in command
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert command[command.index("--top-k") + 1] == "50"
    # The model runs on the GPU (Metal on Apple Silicon), not the CPU.
    assert command[command.index("-ngl") + 1] == "999"
    assert command[command.index("-fa") + 1] == "on"

    gguf = local_model.server_command("/models/x.gguf", binary="/bin/llama-server")
    assert gguf[1:3] == ["-m", "/models/x.gguf"]


def test_a_missing_llama_server_says_how_to_get_one(monkeypatch):
    """The error names the package, not just 'not found'."""
    monkeypatch.setattr(local_model, "find_llama_server", lambda: None)
    with pytest.raises(local_model.LocalModelError, match="llama.cpp"):
        local_model.server_command()


class _Refused:
    """A transport whose first POST is refused, as when no server runs yet."""

    def __init__(self):
        self.calls = 0

    def post(self, url, headers=None, json=None, timeout=None):
        """Refuse once, then answer."""
        self.calls += 1
        if self.calls == 1:
            raise ConnectionRefusedError("nothing listening")
        return _Ok()


class _Ok:
    status_code = 200

    @staticmethod
    def json():
        """A minimal completion."""
        return {"choices": [{"message": {"role": "assistant", "content": "ready"}}]}


def test_a_refused_connection_starts_the_local_model(monkeypatch):
    """The first question brings the model up instead of failing."""
    started = []
    monkeypatch.setattr(
        local_model, "ensure_server", lambda base_url, model: started.append(model) or True
    )
    settings = LLMSettings(base_url="http://127.0.0.1:8080/v1", model="lfm3", managed_server=True)
    transport = _Refused()
    response = LLMClient(settings, session=transport).complete([{"role": "user", "content": "x"}])
    assert response.text == "ready"
    # A bare alias names no downloadable file; the default GGUF is fetched.
    assert started == [local_model.LFM3_MODEL]
    assert transport.calls == 2


def test_a_failed_start_is_reported_not_retried(monkeypatch):
    """An install problem must surface as itself, not as 'cannot reach'."""
    from chisurf.core.agent.llm import LLMError

    def fail(base_url, model):
        raise local_model.LocalModelError("llama-server is not installed")

    monkeypatch.setattr(local_model, "ensure_server", fail)
    settings = LLMSettings(base_url="http://127.0.0.1:8080/v1", model="m", managed_server=True)
    with pytest.raises(LLMError, match="not installed"):
        LLMClient(settings, session=_Refused()).complete([{"role": "user", "content": "x"}])
