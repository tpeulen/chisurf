from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest else "Setup:Plots"
description = "Configure plot appearance, colors, and rendering backend"
icon = "📊"
