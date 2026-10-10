"""Integrated burst analysis plugin.

The window is the native emtk hub in :mod:`.gui.native`; importing this package needs no Qt binding.
"""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "💥"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Spectroscopy:Single-Molecule:Burst Analysis"

description = "Integrated burst analysis workflow."
