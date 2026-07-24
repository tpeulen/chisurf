"""Unified **FCS** plugin — a meta tool hosting the FCS workflow behind a rail.

Merges the FCS *Correlator* workflow (detector → files → filter → correlate →
merge) with the optional FCS tools (2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS,
diffusion/volume calculator, fFCS filter calculator, correlation-channel
presets) into a single left-navigation tool. Built on the reusable
``NavigationPanelTool`` shell. The ribbon execs this file with
``__name__ == "plugin"``.
"""

from __future__ import annotations

from .tool import FcsTool, FcsToolboxTool

name = "Spectroscopy:FCS"
icon = "〰️"

__all__ = ["FcsTool", "FcsToolboxTool", "name"]


if __name__ == "plugin":  # pragma: no cover
    _fcs_window = FcsTool()
    _fcs_window.show()
