"""Model Manager: enable or disable the fitting models ChiSurf offers.

The window is the native emtk app in :mod:`.gui.app`; importing this package needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Setup:Models"

description = "Model Manager Plugin for ChiSurf"
icon = "⚙️"

__all__ = ["name", "description", "icon"]
