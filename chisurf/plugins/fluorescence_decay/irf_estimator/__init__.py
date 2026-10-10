"""IRF Estimator Plugin.

Blind IRF estimation from fluorescence decay data using truncated exponential
fitting and Richardson-Lucy deconvolution.
"""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "⚡"

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Spectroscopy:Fluorescence decay:IRF Extraction"


__all__: list[str] = []
