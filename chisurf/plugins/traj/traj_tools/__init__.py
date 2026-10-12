"""Combined trajectory tools plugin."""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🎬"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Structure:Trajectory:Traj Tools"
    cli_entrypoint = ""
