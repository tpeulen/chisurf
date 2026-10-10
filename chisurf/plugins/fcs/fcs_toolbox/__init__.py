"""Unified **FCS** plugin — a meta tool hosting the FCS workflow behind a rail.

Merges the FCS *Correlator* workflow (detector → files → filter → correlate →
merge) with the optional FCS tools (2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS,
diffusion/volume calculator, fFCS filter calculator, correlation-channel
presets) into a single left-navigation tool, drawn by one native emtk surface
(:mod:`.gui.app`).
"""

from __future__ import annotations

name = "Spectroscopy:Correlation:FCS"
icon = "〰️"

__all__ = ["name"]
