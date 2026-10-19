"""Style Manager: edit, save and apply ChiSurf's emtk style sheets (``.css``).

The window is the emtk app in :mod:`.gui.app`.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Setup:Styles"

description = "Style Manager Plugin for ChiSurf"
icon = "🎨"

__all__ = ["name", "description", "icon"]
