"""ChiSurf Help Plugin.

Documentation browser and help resource viewer for ChiSurf.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Help:Documentation"
    cli_entrypoint = "help=chisurf.plugins.core.help.cli.main:cli"

icon = "📖"


def __getattr__(attribute):
    """Resolve the optional Qt host adapter without affecting native EMTK imports."""
    if attribute in {"HelpEmtkTool", "HelpWidget", "HelpTool"}:
        from chisurf.plugins.core.help.gui import tool

        value = getattr(tool, "HelpEmtkTool" if attribute == "HelpTool" else attribute)
        globals()[attribute] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")


__all__ = ["HelpEmtkTool", "HelpWidget", "HelpTool"]

# Entry point support — when loaded via plugin mechanism
if __name__ == "plugin":
    from chisurf.plugins.core.help.gui.tool import HelpEmtkTool

    window = HelpEmtkTool()
    window.show()
