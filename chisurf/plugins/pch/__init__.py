"""Photon Counting Histogram (PCH) analysis.

This plugin provides tools for analyzing the distribution of photon counts in
fluorescence time traces. PCH analysis can reveal information about:
- Molecular brightness (epsilon)
- Number of molecules in the detection volume (<N>)
- Presence of multiple species with different brightness values

The plugin supports loading TTTR files, calculating PCH histograms, and fitting
them with theoretical models for single or multiple species.

The window is the native emtk app in :mod:`.gui.app`; importing this package needs no
Qt binding.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

# Load manifest as source of truth
_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "Spectroscopy:Correlation:PCH"
    cli_entrypoint = "pch=chisurf.plugins.pch.cli:cli"
