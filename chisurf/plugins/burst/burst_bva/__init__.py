"""Single-molecule Burst Variance Analysis (BVA) plugin.

This plugin implements Burst Variance Analysis for single-molecule FRET experiments.
BVA is a technique that analyzes the variance of FRET efficiency within individual
bursts to distinguish between static and dynamic heterogeneity in the sample.

The window is the native emtk app in :mod:`.gui.app`; importing this package — and with it the
``api`` / ``core`` / ``backend`` / ``cli`` layers — needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

# Plugin brand icon (unified emoji set)
icon = "📊"

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest else "Spectroscopy:Single-Molecule:BVA"

__all__ = ["name"]
