"""A plugin's manifest emoji is its icon even when the caller does not pass the manifest.

Every plugin whose emoji lives only in ``manifest.json`` (Image Tools, File tools,
...) must show it, without its whole module being imported to discover that.
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


def test_the_manifest_icon_is_read_without_importing_the_module(plugin_dir):
    from chisurf.emtk.plugin_icons import _manifest_icon

    # The directory holds only a manifest: no module exists to import.
    assert _manifest_icon(str(plugin_dir)) == "🔬"


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
