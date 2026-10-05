"""A plugin's manifest emoji is its icon even when the caller does not pass the manifest.

The ribbon's plugin tabs and the plugin toolbar called the icon resolver without
the manifest, so every plugin whose emoji lives only in ``manifest.json`` (Image
Tools, File tools, ...) got a letter placeholder — and its whole module was
imported to discover that.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def plugin_dir(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"id": "demo_tool", "version": "1.0.0", "display_name": "Tools:Demo", "icon": "🔬"}),
        encoding="utf-8",
    )
    return tmp_path


def test_the_manifest_icon_is_used_and_the_module_is_not_imported(qapp, plugin_dir, monkeypatch):
    from chisurf.plugins import icon_utils

    resolved = []
    monkeypatch.setattr(
        icon_utils, "resolve_plugin_icon", lambda icon, size, base_dir: resolved.append(icon) or "ICON"
    )

    def provider():
        raise AssertionError("the plugin module was imported to find its icon")

    assert icon_utils.create_plugin_icon_with_fallback(provider, plugin_dir, size=16) == "ICON"
    assert resolved == ["🔬"]
