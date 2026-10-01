"""Photon Table.

Inspect the photons of a TTTR file in a table: one row per photon with its
routing channel, micro-time and macro-time, navigable and filterable.
"""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🔆"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Tools:Inspector:Photon Table"
