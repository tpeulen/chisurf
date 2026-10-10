"""Plugin Check: load every plugin once and report which fail to start.

The window is the native emtk app in :mod:`.gui.app`; the checking logic is in :mod:`.gui.model`.
Importing this package needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

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

__all__ = ["name", "description", "icon"]
