"""The code editor's settings (emtk app), ported from the retired Qt ``EditorSettingsDialog`` tests.

The emtk editor draws its settings in the *Editor settings* dock and keeps them as its own
preferences (``chisurf.emtk.state``); the global ``gui.editor`` section of the ChiSurf settings
file is still written by :func:`chisurf.plugins.core.code_editor.settings.save_editor_settings`.
"""

import yaml
from emtk.testing import Driver

import chisurf as cs
from chisurf.plugins.core.code_editor.gui.editor_app import make_editor_app
from chisurf.plugins.core.code_editor.settings import save_editor_settings


def _app(tmp_path):
    return make_editor_app(str(tmp_path))


class TestCodeEditorSettings:
    """Persistent code editor settings."""

    def test_settings_button_uses_gear_and_opens_the_settings(self, tmp_path):
        """The toolbar's settings button is a gear and opens the Editor settings dock."""
        app = _app(tmp_path)
        try:
            driver = Driver(app, (1400, 900))
            drawn = [t[5] for t in driver.frame(3).texts]
            assert "⚙ Settings" in drawn
            driver.click("⚙ Settings")
            assert "Apply & Save" in [t[5] for t in driver.frame(2).texts]
        finally:
            app.close()

    def test_the_settings_offer_font_language_colours_and_options(self, tmp_path):
        """Font, size, language and colour scheme, Ruff, display and RPC options are all there."""
        app = _app(tmp_path)
        try:
            driver = Driver(app, (1400, 1400))
            driver.frame(3)
            driver.click("⚙ Settings")
            drawn = [t[5] for t in driver.frame(3).texts]
            for label in (
                "Font family",
                "Color scheme",
                "Highlight current line",
                "Enable Ruff",
                "Ruff after save",
                "Ruff timeout (ms)",
                "Ruff extra arguments",
                "Line numbers",
                "Enable editor RPC",
                "RPC host",
                "RPC command port",
                "RPC event port",
            ):
                assert label in drawn, label
            settings = app.model.export_settings()
            for key in (
                "font_family",
                "font_size",
                "language",
                "color_scheme",
                "caret_line_visible",
                "show_line_numbers",
                "enable_lsp",
                "enable_ruff",
                "run_ruff_on_save",
                "ruff_timeout_ms",
                "ruff_extra_args",
                "enable_rpc",
                "rpc_host",
                "rpc_cmd_port",
                "rpc_pub_port",
            ):
                assert key in settings, key
        finally:
            app.close()

    def test_editor_settings_apply_to_the_editor(self, tmp_path):
        """Settings change the editor's font, language, line numbers and current-line highlight."""
        app = _app(tmp_path)
        try:
            doc = app.model.new_document("data.json", "{}")
            app.model.restore_settings({"show_line_numbers": False})
            app.model.apply_editor_preferences(doc.editor)
            assert doc.editor.config.show_line_numbers is False
            app.model.restore_settings(
                {
                    "font_size": 12,
                    "language": "Python",
                    "caret_line_visible": True,
                    "show_line_numbers": True,
                }
            )
            app.model.apply_editor_preferences(doc.editor)
            assert app.model.font_size == 12
            assert doc.editor.language_name.lower() == "python"
            assert doc.editor.config.highlight_current_line is True
            assert doc.editor.config.show_line_numbers is True
        finally:
            app.close()

    def test_save_editor_settings_persists_to_yaml(self, tmp_path, monkeypatch):
        """Editor settings are written to the ChiSurf settings YAML (``gui.editor``)."""
        settings_file = tmp_path / "settings_chisurf.yaml"
        settings_file.write_text(
            "gui:\n  editor:\n    font_family: Courier New\n    font_size: 9\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(cs.core.settings, "chisurf_settings_file", settings_file)
        monkeypatch.setattr(
            cs.core.settings,
            "cs_settings",
            {"gui": {"editor": {"font_family": "Courier New", "font_size": 9}}},
        )
        monkeypatch.setattr(
            cs.core.settings,
            "gui",
            {"editor": {"font_family": "Courier New", "font_size": 9}},
        )

        assert save_editor_settings(
            {
                "font_family": "Consolas",
                "font_size": 11,
                "line_numbers_visible": False,
                "enable_lsp": False,
            }
        )

        data = yaml.safe_load(settings_file.read_text(encoding="utf-8"))
        assert data["gui"]["editor"]["font_family"] == "Consolas"
        assert data["gui"]["editor"]["font_size"] == 11
        assert data["gui"]["editor"]["line_numbers_visible"] is False
        assert data["gui"]["editor"]["enable_lsp"] is False
        assert cs.core.settings.gui["editor"]["font_family"] == "Consolas"
        assert cs.core.settings.gui["editor"]["font_size"] == 11
        assert cs.core.settings.gui["editor"]["line_numbers_visible"] is False
        assert cs.core.settings.gui["editor"]["enable_lsp"] is False
