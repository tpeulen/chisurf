"""AI Settings: configure the API providers and backends the assistants use.

The window is the native emtk app in :mod:`.gui.app`; importing this package needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:AI Settings"

description = "AI Settings plugin for configuring API providers and backends."
icon = "🤖"

__all__ = ["name", "icon"]
