"""Unified **FCS** plugin — a meta tool hosting the FCS workflow behind a rail.

Merges the FCS *Correlator* workflow (detector → files → filter → correlate →
merge) with the optional FCS tools (2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS,
diffusion/volume calculator, fFCS filter calculator, correlation-channel
presets) into a single left-navigation tool. Built on the reusable
``NavigationPanelTool`` shell. The ribbon execs this file with
``__name__ == "plugin"``.
"""

from __future__ import annotations

name = "Spectroscopy:Correlation:FCS"
icon = "〰️"

__all__ = ["FcsTool", "FcsToolboxTool", "name"]


def __getattr__(attr):
    """The Qt tool, imported only when asked for: the native hub (``gui.app``) must load without Qt."""
    if attr in ("FcsTool", "FcsToolboxTool"):
        from . import tool

        return getattr(tool, attr)
    raise AttributeError(attr)


if __name__ == "plugin":  # pragma: no cover - the legacy macro launch; the manifest's gui/emtk entries come first
    from chisurf.plugins.fcs.fcs_toolbox.tool import FcsTool

    _fcs_window = FcsTool()
    _fcs_window.show()
