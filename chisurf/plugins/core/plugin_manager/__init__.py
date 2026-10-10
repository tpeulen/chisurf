"""Plugin Manager: enable, disable, install and remove ChiSurf plugins.

The window is the native emtk app in :mod:`.gui.app`; importing this package needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest
from chisurf.plugins.core.plugin_manager.api.icons import AIIconRateLimitError
from chisurf.plugins.core.plugin_manager.api.records import read_module_docstring

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Setup:Plugins"

description = "This tool manages the list of active/disabled plugins in ChiSurf."
icon = "🔌"

__all__ = ["AIIconRateLimitError", "read_module_docstring", "name", "description", "icon"]
