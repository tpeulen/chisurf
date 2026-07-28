"""Single-molecule Burst Variance Analysis (BVA) plugin.

This plugin implements Burst Variance Analysis for single-molecule FRET experiments.
BVA is a technique that analyzes the variance of FRET efficiency within individual
bursts to distinguish between static and dynamic heterogeneity in the sample.

The Qt tool is resolved lazily (PEP 562), so importing this package — and with it
the ``api`` / ``core`` / ``backend`` / ``cli`` layers — needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chisurf.core.plugin import load_manifest

# Plugin brand icon (unified emoji set)
icon = "📊"

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest else "Spectroscopy:Single-Molecule:BVA"

__all__ = ["BVATool", "name"]


def __getattr__(attribute: str) -> Any:
    """Resolve the Qt tool on first access (PEP 562 lazy import)."""
    if attribute == "BVATool":
        from .gui.tool import BVATool

        return BVATool
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")
