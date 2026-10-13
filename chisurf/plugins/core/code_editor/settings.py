from __future__ import annotations

from typing import Any

import yaml

import chisurf as cs
import chisurf.core.settings
from chisurf import logging

EDITOR_DEFAULT_FONTS = [
    "Courier New",
    "Consolas",
    "SF Mono",
    "Menlo",
    "Monaco",
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Courier",
    "Monospace",
]

EDITOR_LANGUAGE_OPTIONS = ["Python", "JSON", "YAML", "Plain text"]

EDITOR_COLOR_SCHEMES = {
    "ChiSurf": {
        "paper_color": "#cfcfcf",
        "default_color": "#000006",
        "margins_background_color": "#808080",
        "marker_background_color": "#f0f0f0",
        "caret_line_background_color": "#afafaf",
    },
    "Light": {
        "paper_color": "#ffffff",
        "default_color": "#000000",
        "margins_background_color": "#f0f0f0",
        "marker_background_color": "#d8e8ff",
        "caret_line_background_color": "#eef4ff",
    },
    "Dark": {
        "paper_color": "#1e1e1e",
        "default_color": "#d4d4d4",
        "margins_background_color": "#252526",
        "marker_background_color": "#3c3c3c",
        "caret_line_background_color": "#2d2d30",
    },
    "Monokai": {
        "paper_color": "#272822",
        "default_color": "#f8f8f2",
        "margins_background_color": "#1e1f1c",
        "marker_background_color": "#3e3d32",
        "caret_line_background_color": "#3e3d32",
    },
}

EDITOR_SETTINGS_KEYS = [
    "font_family",
    "font_size",
    "language",
    # Absent until 2026-08-06, which made the Run-endpoint dropdown inert:
    # save_editor_settings filters by this list, so the chosen endpoint was
    # dropped on the way to disk and run_macro always fell back to "process".
    "run_endpoint",
    "color_scheme",
    "paper_color",
    "default_color",
    "margins_background_color",
    "marker_background_color",
    "caret_line_background_color",
    "caret_line_visible",
    "line_numbers_visible",
    "show_whitespace",
    "enable_lsp",
    "enable_ruff",
    "run_ruff_on_save",
    "ruff_timeout_ms",
    "ruff_extra_args",
    "enable_rpc",
    "rpc_host",
    "rpc_cmd_port",
    "rpc_pub_port",
    "agent_actions_enabled",
    "agent_autofit_enabled",
    "agent_code_run_enabled",
    "agent_default_mode",
    "agent_max_tool_iterations",
    "agent_invalid_json_retries",
    "agent_tool_timeout_ms",
    "agent_code_timeout_ms",
    "agent_output_max_chars",
    "agent_chisurf_rpc_host",
    "agent_chisurf_rpc_cmd_port",
    "agent_chisurf_rpc_pub_port",
    "agent_editor_rpc_host",
    "agent_editor_rpc_cmd_port",
    "agent_editor_rpc_pub_port",
]


def editor_language_key(language: str | None) -> str:
    """Return the normalized internal language key for *language*."""
    key = str(language or "").strip().lower().replace("_", "-")
    if key in {"plain-text", "plain text"}:
        return "plain"
    return key


def normalize_editor_language(language: str | None) -> str:
    """Return a display language name for *language*."""
    key = editor_language_key(language)
    if key in {"json"}:
        return "JSON"
    if key in {"yaml", "yml"}:
        return "YAML"
    if key in {"plain", "text"}:
        return "Plain text"
    return "Python"


def default_editor_settings() -> dict[str, Any]:
    """Return the default editor settings dictionary."""
    settings: dict[str, str | int | bool | list[str]] = {
        "font_family": "Courier New",
        "font_size": 9,
        "language": "Python",
        "run_endpoint": "console",
        "color_scheme": "ChiSurf",
        "caret_line_visible": False,
        "line_numbers_visible": True,
        "show_whitespace": False,
        "enable_lsp": True,
        "enable_ruff": True,
        "run_ruff_on_save": False,
        "ruff_timeout_ms": 5000,
        "ruff_extra_args": [],
        "enable_rpc": False,
        "rpc_host": "127.0.0.1",
        "rpc_cmd_port": 8775,
        "rpc_pub_port": 8776,
        "agent_actions_enabled": True,
        "agent_autofit_enabled": True,
        "agent_code_run_enabled": False,
        "agent_default_mode": "chat_only",
        "agent_max_tool_iterations": 25,
        "agent_invalid_json_retries": 2,
        "agent_tool_timeout_ms": 30000,
        "agent_code_timeout_ms": 5000,
        "agent_output_max_chars": 20000,
        "agent_chisurf_rpc_host": "127.0.0.1",
        "agent_chisurf_rpc_cmd_port": 8765,
        "agent_chisurf_rpc_pub_port": 8766,
        "agent_editor_rpc_host": "127.0.0.1",
        "agent_editor_rpc_cmd_port": 8775,
        "agent_editor_rpc_pub_port": 8776,
    }
    settings.update(EDITOR_COLOR_SCHEMES["ChiSurf"])
    return settings


def get_editor_settings() -> dict[str, Any]:
    """Return editor settings merged with the current ChiSurf GUI settings."""
    settings = default_editor_settings()
    cfg = cs.core.settings.gui.get("editor", {})
    if not isinstance(cfg, dict):
        cfg = {}
    for key, value in cfg.items():
        if key in EDITOR_SETTINGS_KEYS:
            settings[key] = value
    scheme = settings.get("color_scheme")
    if scheme in EDITOR_COLOR_SCHEMES:
        settings.update(EDITOR_COLOR_SCHEMES[scheme])
    for key, value in cfg.items():
        if key in EDITOR_SETTINGS_KEYS:
            settings[key] = value
    settings["language"] = normalize_editor_language(settings.get("language"))
    return settings


def save_editor_settings(settings: dict) -> bool:
    """Persist editor settings to the user ChiSurf settings file."""
    editor_settings = {key: settings[key] for key in EDITOR_SETTINGS_KEYS if key in settings}
    if not editor_settings:
        return False

    try:
        settings_file = cs.core.settings.chisurf_settings_file
        data = cs.core.settings.safe_open_file(
            file_path=settings_file,
            processor=yaml.safe_load,
            default_value={},
            error_message=f"Error opening settings file {settings_file}",
        )
        if not isinstance(data, dict):
            data = {}

        gui_cfg = data.setdefault("gui", {})
        if not isinstance(gui_cfg, dict):
            gui_cfg = {}
            data["gui"] = gui_cfg

        editor_cfg = gui_cfg.setdefault("editor", {})
        if not isinstance(editor_cfg, dict):
            editor_cfg = {}
            gui_cfg["editor"] = editor_cfg

        editor_cfg.update(editor_settings)

        cs_settings = cs.core.settings.cs_settings
        if not isinstance(cs_settings, dict):
            cs.core.settings.cs_settings = {}
            cs_settings = cs.core.settings.cs_settings
        cs_gui = cs_settings.setdefault("gui", {})
        if not isinstance(cs_gui, dict):
            cs_gui = {}
            cs_settings["gui"] = cs_gui
        cs_editor = cs_gui.setdefault("editor", {})
        if not isinstance(cs_editor, dict):
            cs_editor = {}
            cs_gui["editor"] = cs_editor
        cs_editor.update(editor_settings)

        gui = cs.core.settings.gui
        if not isinstance(gui, dict):
            cs.core.settings.gui = {}
            gui = cs.core.settings.gui
        gui_editor = gui.setdefault("editor", {})
        if not isinstance(gui_editor, dict):
            gui_editor = {}
            gui["editor"] = gui_editor
        gui_editor.update(editor_settings)

        with open(settings_file, "w", encoding="utf-8") as file:
            yaml.safe_dump(data, file, default_flow_style=False, sort_keys=False)
        return True
    except Exception as e:
        logging.log(1, f"Error saving editor settings: {e}")
        return False
