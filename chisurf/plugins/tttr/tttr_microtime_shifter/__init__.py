"""
Micro-time Shifter Plugin

Apply global and per-channel micro-time shifts to TTTR files.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:Photon data:Microtime Shifter"
