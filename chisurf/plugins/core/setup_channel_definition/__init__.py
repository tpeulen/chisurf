"""Setup Channel Definition: detector channels and PIE time windows.

The window is the native emtk app in :mod:`.gui.app`; importing this package needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Setup:Channel Definition"

description = "This tool defines and configures detector channels and time windows."
icon = "🔢"

__all__ = ["name", "description", "icon"]
