"""Burst-wise FCS Correlator plugin.

Computes fluorescence correlation functions on a per-burst basis from Burst-ID
``.bst`` / BUR files. The compute core is Qt-free (:mod:`.core`), exposed via
backend RPC services (:mod:`.backend`) and reached from the GUI through
:class:`.gui.BurstFcsClient`. The window is the native emtk app in :mod:`.gui.app`,
declared by ``burst_fcs_emtk.view.json``.
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "Spectroscopy:Fluorescence Correlation Spectroscopy:Burst-wise FCS"

# Hidden from the menu: surfaced inside the FCS Toolbox meta tool.
menu_hidden = True

__all__ = ["menu_hidden", "name"]
