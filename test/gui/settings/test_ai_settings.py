"""Settings-module and plugin-entrypoint tests for AI/LLM configuration.

The widget-level tests that used to live here drove the pre-AutoForm dialog
(``provider_combo``/``base_url_input``/``chat_model_combo``) and the retired
``chisurf.plugins.ai_settings.plugin`` module, so they had been failing to even
import since the AutoForm port. The current widget/model behaviour is covered by
``chisurf/plugins/ai_settings/test/test_widgets.py``; what is unique here — the
settings file round-trip and the plugin entrypoints — is kept and brought up to
the canonical provider keys (``mistral``/``local``/``openai``, with the
``*_api``/``local_llm`` spellings now legacy aliases).
"""

import json
import pathlib
import tempfile
from unittest.mock import patch

import pytest
from qtpy import QtWidgets

from chisurf.core.settings import ai_settings
from chisurf.plugins.ai_settings.gui.tool import AISettingsWidget


class TestAISettingsModule:
    """Tests for the ai_settings module."""

    def test_default_settings_structure(self):
        """Test that default settings have the correct structure."""
        defaults = ai_settings.DEFAULT_SETTINGS
        assert "provider" in defaults
        assert "base_url" in defaults
        assert "model" in defaults
        assert "api_key" in defaults

    def test_get_provider_returns_a_known_provider(self):
        """``get_provider`` returns one of the canonical provider keys."""
        known = {key for key, *_ in ai_settings.PROVIDERS.values()}
        assert ai_settings.get_provider() in known

    def test_legacy_provider_keys_normalize(self):
        """Settings written with the old ``*_api`` spellings still resolve."""
        assert ai_settings.normalize_provider_key("mistral_api") == "mistral"
        assert ai_settings.normalize_provider_key("openai_api") == "openai"
        assert ai_settings.normalize_provider_key("local_llm") == "local"

    def test_get_base_url_returns_string(self):
        """Test that get_base_url returns a string."""
        assert isinstance(ai_settings.get_base_url(), str)

    def test_get_model_returns_string(self):
        """Test that get_model returns a string."""
        assert isinstance(ai_settings.get_model(), str)

    def test_get_api_settings_returns_dict(self):
        """Test that get_api_settings returns a dictionary."""
        settings = ai_settings.get_api_settings()
        assert isinstance(settings, dict)
        for key in ("provider", "base_url", "model", "api_key"):
            assert key in settings


class TestAISettingsSaveLoad:
    """Tests for save/load functionality with temp directory."""

    def test_save_settings_creates_file(self):
        """Test that save_settings creates a JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = pathlib.Path(tmpdir)

            with patch.object(
                ai_settings, "_get_settings_path", return_value=tmp_path / "ai_api_settings.json"
            ):
                test_settings = {
                    "provider": "mistral",
                    "base_url": "https://api.mistral.ai/v1",
                    "model": "mistral-large-latest",
                    "api_key": "test-key-123",
                }
                assert ai_settings.save_api_settings(test_settings) is True
                assert (tmp_path / "ai_api_settings.json").exists()

    def test_load_settings_reads_file(self):
        """Test that load_settings reads from JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = pathlib.Path(tmpdir) / "ai_api_settings.json"

            test_settings = {
                "provider": "mistral",
                "base_url": "https://api.mistral.ai/v1",
                "model": "mistral-small-latest",
                "api_key": "test-mistral-key",
            }
            test_file.write_text(json.dumps(test_settings))

            with patch.object(ai_settings, "_get_settings_path", return_value=test_file):
                loaded = ai_settings.get_api_settings()
                assert loaded["provider"] == "mistral"
                assert loaded["base_url"] == "https://api.mistral.ai/v1"
                assert loaded["model"] == "mistral-small-latest"
                assert loaded["api_key"] == "test-mistral-key"


@pytest.fixture(scope="module")
def app():
    """Create QApplication instance for Qt tests."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    yield app


class TestAISettingsIntegration:
    """Integration tests for AI settings plugin."""

    def test_plugin_load_function_returns_widget(self, app):
        """Test that plugin load returns a widget."""
        from chisurf.plugins.ai_settings import load

        assert isinstance(load(), AISettingsWidget)

    def test_plugin_name_defined(self):
        """Test that plugin name is defined."""
        from chisurf.plugins import ai_settings as plugin

        assert plugin.name == "Tools:AI Settings"

    def test_plugin_icon_defined(self):
        """Test that plugin icon is defined."""
        from chisurf.plugins import ai_settings as plugin

        assert plugin.icon == "🤖"

    def test_plugin_exports_widget(self, app):
        """Test that widget is exported."""
        from chisurf.plugins.ai_settings import AISettingsWidget as ImportedWidget

        assert ImportedWidget is AISettingsWidget
