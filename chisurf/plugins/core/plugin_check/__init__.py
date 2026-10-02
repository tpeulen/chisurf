"""Plugin Check Plugin.

This plugin provides a GUI interface to run the plugin checker macro.
It adds a menu item to Tools:Miscellaneous:Plugin-Check that opens the plugin testing window.

The UI logic is in this plugin, while the actual testing logic is in the macro.
"""

from __future__ import annotations

from pathlib import Path

import chisurf as cs
from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness

def __getattr__(attribute):
    if attribute in {'PluginCheckTool', 'PluginCheckWidget'}:
        from chisurf.plugins.core.plugin_check.gui import tool
        return getattr(tool, attribute)
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:Miscellaneous:Plugin-Check"

description = (
    "This tool tests all plugins for startup errors.\n"
    "Green checkmarks indicate successful loading, red crosses indicate failures.\n"
    "It uses the same mechanism as ChiSurf's plugin system."
)

icon = "🧪"


def load():
    """Return the plugin check tool."""
    from chisurf.plugins.core.plugin_check.gui.tool import PluginCheckTool

    return PluginCheckTool()


__all__ = [
    "PluginCheckTool",
    "PluginCheckWidget",
    "load",
    "name",
    "description",
    "icon",
]

if __name__ == "plugin":
    from chisurf.plugins.core.plugin_check.gui.tool import PluginCheckTool

    try:
        parent = getattr(cs, "cs", None)
        window = PluginCheckTool(parent=parent)
        if _manifest is not None:
            apply_manifest_statefulness(window, _manifest)
        window.show()
        window.raise_()
        window.activateWindow()
    except Exception as exc:
        print(f"Failed to open Plugin Check: {exc}")
        import traceback

        traceback.print_exc()
