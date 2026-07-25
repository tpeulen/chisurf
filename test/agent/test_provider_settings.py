"""Tests for resolving provider credentials from the environment.

A key that is present but looked for under the wrong variable name is
indistinguishable, to the user, from a provider that does not work.
"""

from __future__ import annotations

import pytest

from chisurf.core.agent import LLMClient, LLMSettings
from chisurf.core.settings.ai_settings import (
    PROVIDERS,
    get_provider_api_key,
    provider_key_env_names,
)


def _clear_provider_keys(monkeypatch):
    """Remove every candidate key variable so a test starts from nothing."""
    for provider in ("openai", "openrouter", "mistral"):
        for name in provider_key_env_names(provider):
            monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("provider", ["openai", "openrouter", "mistral"])
def test_the_declared_variable_comes_first(provider):
    declared = next(env for key, _url, _api, env in PROVIDERS.values() if key == provider)
    assert provider_key_env_names(provider)[0] == declared


@pytest.mark.parametrize(
    ("provider", "variable"),
    [
        ("mistral", "MISTRAL_API_KEY"),
        ("mistral", "MISTRAL_KEY"),
        ("mistral", "MISTRAL_API_TOKEN"),
        ("mistral", "MISTRAL_TOKEN"),
        ("openrouter", "OPENROUTER_API_KEY"),
        ("openrouter", "OPENROUTER_API_TOKEN"),
        ("openai", "OPENAI_KEY"),
    ],
)
def test_a_key_is_found_under_any_common_variable_name(monkeypatch, provider, variable):
    """A shell profile is as likely to hold MISTRAL_KEY as MISTRAL_API_KEY."""
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv(variable, "secret-value")
    assert get_provider_api_key(provider) == "secret-value"


def test_the_canonical_variable_wins_over_an_alias(monkeypatch):
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("MISTRAL_KEY", "alias")
    monkeypatch.setenv("MISTRAL_API_KEY", "canonical")
    assert get_provider_api_key("mistral") == "canonical"


def test_an_empty_variable_is_skipped(monkeypatch):
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("MISTRAL_API_KEY", "   ")
    monkeypatch.setenv("MISTRAL_KEY", "real")
    assert get_provider_api_key("mistral") == "real"


def test_no_key_is_reported_as_empty(monkeypatch):
    _clear_provider_keys(monkeypatch)
    assert get_provider_api_key("mistral") == ""


def test_local_providers_need_no_key():
    assert provider_key_env_names("local") == []
    assert get_provider_api_key("local") == ""


def test_settings_pick_up_an_aliased_key(monkeypatch):
    """The path the agent actually uses, not just the helper."""
    _clear_provider_keys(monkeypatch)
    monkeypatch.setenv("MISTRAL_KEY", "from-alias")
    settings = LLMSettings.from_provider("mistral")
    assert settings.api_key == "from-alias"
    assert settings.base_url == "https://api.mistral.ai/v1"
    settings.validate()


def test_a_fresh_install_starts_on_an_eu_hosted_provider(monkeypatch, tmp_path):
    """Data residency is a default, not something a user must discover."""
    from chisurf.core.settings import ai_settings

    monkeypatch.setattr(ai_settings, "_get_settings_path", lambda: tmp_path / "none.json")
    settings = ai_settings.get_api_settings()

    assert settings["provider"] == ai_settings.DEFAULT_PROVIDER == "mistral"
    assert settings["base_url"] == "https://api.mistral.ai/v1"
    assert settings["text_model"]


def test_a_saved_choice_is_never_overridden_by_the_default(monkeypatch, tmp_path):
    """Changing the shipped default must not move an existing install."""
    from chisurf.core.settings import ai_settings

    settings_file = tmp_path / "ai_api_settings.json"
    monkeypatch.setattr(ai_settings, "_get_settings_path", lambda: settings_file)
    settings_file.write_text(
        '{"selected_provider": "openai", "openai": {"model": "gpt-4o"}}', encoding="utf-8"
    )

    assert ai_settings.get_api_settings()["provider"] == "openai"


def test_the_provider_list_puts_data_residency_first():
    """The order is what a user sees in the settings dialog."""
    keys = [key for key, _url, _api, _env in PROVIDERS.values()]
    assert keys[0] == "mistral"
    assert keys.index("local") < keys.index("openai")


def test_every_provider_ships_a_usable_default_model():
    from chisurf.core.settings.ai_settings import DEFAULT_PROVIDER_SETTINGS

    for provider, defaults in DEFAULT_PROVIDER_SETTINGS.items():
        if provider == "custom":
            continue
        assert defaults["text_model"], f"{provider} has no default model"
        assert defaults["base_url"], f"{provider} has no base URL"


def test_a_credit_refusal_names_the_setting_to_change():
    """HTTP 402 is a max_tokens reservation, not necessarily an empty wallet."""
    client = LLMClient(LLMSettings(base_url="https://x/v1", model="m", max_tokens=4096))
    message = client._explain_status(402, "requires more credits")
    assert "max_tokens" in message
    assert "4096" in message
