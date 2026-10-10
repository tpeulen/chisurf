"""FPS JSON Editor for Accessible Volume Calculations."""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Structure:FRET:FPS JSON Editor"
    cli_entrypoint = ""

__all__ = ["cli_entrypoint", "name"]
