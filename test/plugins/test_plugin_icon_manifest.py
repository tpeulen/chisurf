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
        json.dumps(
            {"id": "demo_tool", "version": "1.0.0", "display_name": "Tools:Demo", "icon": "🔬"}
        ),
        encoding="utf-8",
    )
    return tmp_path


def test_the_manifest_icon_is_used_and_the_module_is_not_imported(qapp, plugin_dir, monkeypatch):
    from chisurf.gui import plugin_icons as icon_utils

    resolved = []
    monkeypatch.setattr(
        icon_utils,
        "resolve_plugin_icon",
        lambda icon, size, base_dir: resolved.append(icon) or "ICON",
    )

    def provider():
        raise AssertionError("the plugin module was imported to find its icon")

    assert icon_utils.create_plugin_icon_with_fallback(provider, plugin_dir, size=16) == "ICON"
    assert resolved == ["🔬"]


def test_every_plugin_manifest_declares_its_icon():
    """The manifest is the one place a plugin's pictogram is declared (the uniform-icon rule).

    The ribbon, the menus, the Tools dock and every hub row read it from there; a plugin without
    one shows a placeholder in some of them and its module's ``icon`` attribute in others.
    Libraries (``"library": true``) are not entries anywhere and need none.
    """
    from chisurf.emtk.plugins import manifests

    missing = sorted(
        plugin_id
        for plugin_id, data in manifests().items()
        if not data.get("library") and not str(data.get("icon") or "").strip()
    )
    assert missing == []


def test_listed_plugins_have_distinct_icons():
    """Two buttons of the ribbon or the Tools dock never share a pictogram: the icon is how a row is found."""
    from chisurf.emtk.plugins import manifests

    seen: dict[str, str] = {}
    clashes = []
    for plugin_id, data in sorted(manifests().items()):
        if data.get("menu_hidden") or data.get("library"):
            continue
        icon = str(data.get("icon") or "")
        if icon in seen:
            clashes.append((icon, seen[icon], plugin_id))
        seen[icon] = plugin_id
    assert clashes == []
