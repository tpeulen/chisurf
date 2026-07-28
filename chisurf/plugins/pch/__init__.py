"""Photon Counting Histogram (PCH) analysis.

This plugin provides tools for analyzing the distribution of photon counts in
fluorescence time traces. PCH analysis can reveal information about:
- Molecular brightness (epsilon)
- Number of molecules in the detection volume (<N>)
- Presence of multiple species with different brightness values

The plugin supports loading TTTR files, calculating PCH histograms, and fitting
them with theoretical models for single or multiple species.

The Qt tool is resolved lazily (PEP 562), so importing this package — and with it
the ``api`` / ``backend`` / ``cli`` layers — needs no Qt binding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from chisurf.core.plugin import load_manifest
from chisurf.core.plugin.registry import apply_manifest_statefulness

# Load manifest as source of truth
_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Spectroscopy:Single-Molecule:PCH"
    cli_entrypoint = "pch=chisurf.plugins.pch.cli:cli"

__all__ = ["PCHApp"]


def __getattr__(attribute: str) -> Any:
    """Resolve the Qt tool on first access (PEP 562 lazy import)."""
    if attribute == "PCHApp":
        from .gui.tool import PCHApp

        return PCHApp
    raise AttributeError(f"module {__name__!r} has no attribute {attribute!r}")


if __name__ == "plugin":
    from .gui.tool import PCHApp

    window = PCHApp()
    if _manifest is not None:
        apply_manifest_statefulness(window, _manifest)
    window.show()
