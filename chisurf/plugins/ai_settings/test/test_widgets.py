"""Headless tests for the AutoForm-based AI Settings plugin."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Isolate the settings file **and** the environment.

    The file redirect keeps auto-save away from ``~/.chisurf``. Clearing the
    provider environment variables matters just as much now that
    :func:`get_api_settings` honours them: without it, whether these tests pass
    depends on whether the developer happens to have ``MISTRAL_API_KEY``
    exported, which is exactly the kind of machine-dependent result a test must
    not have.
    """
    from chisurf.core.settings import ai_settings

    monkeypatch.setattr(
        ai_settings, "_get_settings_path", lambda: tmp_path / "ai_api_settings.json"
    )
    for provider_key, *_rest in ai_settings.PROVIDERS.values():
        for name in ai_settings.provider_key_env_names(provider_key):
            monkeypatch.delenv(name, raising=False)


# --- backing-model tests (no Qt) -----------------------------------------------
class TestAISettingsModel:
    """The GUI-free AISettingsModel: provider/network/persistence behaviour."""

    def test_view_spec_has_collapsible_panels(self):
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        view = AISettingsModel().view_spec()
        titles = [getattr(s, "title", None) for s in view.sections]
        assert "API Configuration" in titles
        assert "Models" in titles
        assert "Generation Settings" in titles

    def test_set_provider_loads_provider_defaults(self):
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        model = AISettingsModel()
        model.set_provider("mistral")
        assert model.provider == "mistral"
        assert "mistral" in model.base_url

    def test_save_separates_text_and_image_models(self, monkeypatch):
        from chisurf.core.settings import ai_settings
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        saved: dict = {}
        monkeypatch.setattr(
            ai_settings, "save_api_settings", lambda settings: saved.update(settings) or True
        )

        model = AISettingsModel()
        model.text_model = "text-model"
        model.image_model = "image-model"
        model.save()

        assert saved["text_model"] == "text-model"
        assert saved["image_model"] == "image-model"

    def test_reset_restores_defaults(self, monkeypatch):
        from chisurf.core.settings import ai_settings
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        monkeypatch.setattr(ai_settings, "save_api_settings", lambda settings: True)
        model = AISettingsModel()
        model.set_provider("openai")
        model.api_key = "new-key"
        model.base_url = "http://custom.url"
        model.reset()
        assert model.api_key == ""
        assert model.base_url == "https://api.openai.com/v1"

    def test_fetch_models_populates_option_sources(self, monkeypatch):
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        class Response:
            status_code = 200

            def json(self):
                return {"data": [{"id": "chat-model"}, {"id": "image-model"}]}

        # Patch the seam the code actually uses. This stubbed ``sys.modules
        # ["requests"]`` for years after the tree moved to chisurf.core.support.http, so
        # the stub was inert and the test reached the network for
        # example.invalid.
        from chisurf.core.support import http

        monkeypatch.setattr(http, "get", lambda *a, **k: Response())

        model = AISettingsModel()
        model.base_url = "https://example.invalid/v1"
        model.fetch_models()

        assert "chat-model" in model.available_text_models()
        assert "image-model" in model.available_image_models()

    def test_on_change_fires_on_status_update(self, monkeypatch):
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        model = AISettingsModel()
        calls = []
        model.on_change = lambda: calls.append(1)
        model.set_provider("local")
        assert calls  # provider switch notified the view

    def test_editing_a_field_auto_persists(self):
        from chisurf.core.settings import ai_settings
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        model = AISettingsModel()
        model.set_provider("openai")
        model.api_key = "sk-pasted-token"  # a plain edit, no Save click
        # It is on disk immediately, under the current provider.
        assert ai_settings.get_api_settings("openai")["api_key"] == "sk-pasted-token"

    def test_apply_token_tests_connection(self, monkeypatch):
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        monkeypatch.setattr(
            AISettingsModel, "_get_models", staticmethod(lambda *a, **k: {"data": []})
        )
        model = AISettingsModel()
        model.set_provider("openai")
        model.api_key = "sk-token"
        model.apply_token()
        assert "successful" in model.status_html.lower()

    def test_provider_switch_does_not_carry_key_across_providers(self):
        from chisurf.core.settings import ai_settings
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        model = AISettingsModel()
        model.set_provider("openai")
        model.api_key = "openai-only-key"  # auto-saved under openai
        model.set_provider("mistral")  # loads mistral; must not inherit the key
        assert model.api_key == ""
        assert ai_settings.get_api_settings("mistral")["api_key"] != "openai-only-key"

    def test_async_runner_is_used_for_network(self, monkeypatch):
        from chisurf.plugins.ai_settings.gui.model import AISettingsModel

        monkeypatch.setattr(
            AISettingsModel, "_get_models", staticmethod(lambda *a, **k: {"data": []})
        )
        model = AISettingsModel()
        model.set_provider("openai")

        used = []

        def runner(work, done):
            used.append(True)
            done(work())  # synchronous stand-in for the real off-thread runner

        model.async_runner = runner
        model.test_connection()
        assert used == [True]
        assert "successful" in model.status_html.lower()


def test_connection_runs_off_the_ui_thread(monkeypatch):
    """The blocking request runs on a background thread, never the caller's."""
    import threading
    import time

    from chisurf.plugins.ai_settings.gui.model import AISettingsModel

    seen = {}

    def fake_get_models(base_url, api_key):
        seen["worker"] = threading.current_thread()
        return {"data": []}

    monkeypatch.setattr(AISettingsModel, "_get_models", staticmethod(fake_get_models))
    from chisurf.plugins.ai_settings.gui.app import AISettingsApp

    app = AISettingsApp()
    model = app.model
    model.set_provider("openai")
    model.api_key = "sk-x"
    model.test_connection()
    end = time.monotonic() + 3
    while "successful" not in model.status_html.lower() and time.monotonic() < end:
        time.sleep(0.01)
        app.job.poll()
    assert "successful" in model.status_html.lower()
    assert seen["worker"] is not threading.main_thread()


def test_native_acp_command_is_saved_without_replacing_http_provider():
    from chisurf.core.settings import ai_settings

    ai_settings.save_api_settings(
        {"provider": "local", "base_url": "http://localhost/v1", "text_model": "test-model"}
    )
    assert ai_settings.save_api_settings(
        {
            "provider": "acp",
            "command": 'agent --stdio "quoted path"',
            "acp_backend_provider": "local",
        },
        provider="acp",
    )
    assert ai_settings.get_api_settings("acp")["command"] == 'agent --stdio "quoted path"'
    assert ai_settings.get_provider() == "local"
