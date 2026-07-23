"""Unified **FCS** tool — the single FCS plugin.

Merges the FCS *Correlator* workflow (detector setup → files → photon/burst
filter → correlate → merge) with the optional FCS tools (2D-FLCS, Lifetime-FCS
Sim, Burst-wise FCS, diffusion/volume calculator, fFCS filter calculator,
correlation-channel presets) behind one left navigation rail.

The correlator steps come first (their inter-panel context wiring lives in
:class:`~chisurf.plugins.fcs.fcs_correlator.tool.FcsCorrelatorTool`, which this
tool subclasses); a ``Tools`` separator then groups the optional, independent
tools below. Built on :class:`chisurf.gui.widgets.navigation.NavigationPanelTool`
— the same shell the Burst Analysis, Decay Analysis and Imaging Tools windows
use — so it shares their look and codebase.
"""

from __future__ import annotations

import pathlib

from qtpy import QtWidgets

from chisurf.core.plugin.manifest import load_manifest
from chisurf.gui.glyphs import Glyphs
from chisurf.plugins.fcs.fcs_correlator.tool import CORRELATOR_PANELS, FcsCorrelatorTool

#: chisurf/plugins directory (this file is plugins/fcs/fcs_toolbox/tool.py).
_PLUGINS_DIR = pathlib.Path(__file__).resolve().parents[2]


def _apply_manifest_flags(panels: list[dict]) -> list[dict]:
    """Enrich panels with the ``experimental`` flag from each tool's manifest.json.

    A panel may declare ``"manifest": "<rel path under chisurf/plugins>"``; the manifest's
    ``experimental`` / ``experimental_message`` then drive the navigation marker and banner,
    so the flag lives in one place (the manifest) rather than being duplicated here.
    """
    for panel in panels:
        rel = panel.get("manifest")
        if not rel:
            continue
        manifest = load_manifest(_PLUGINS_DIR / rel / "manifest.json")
        if manifest is not None and manifest.experimental:
            panel["experimental"] = True
            if manifest.experimental_message:
                panel["experimental_message"] = manifest.experimental_message
    return panels


# ---------------------------------------------------------------------------
# Optional-tool panel factories
# ---------------------------------------------------------------------------

def _make_2dflcs(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    from chisurf.plugins.fcs.flc_2d import TwoDFCSPlugin

    w = TwoDFCSPlugin()
    w.setParent(parent)
    return w


def _make_lfcs_sim(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    from chisurf.plugins.fcs.fcs_lfcs_sim.gui.tool import LifetimeFcsSimWidget

    w = LifetimeFcsSimWidget()
    w.setParent(parent)
    return w


def _make_burst_fcs(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    from chisurf.plugins.burst.burst_fcs_correlator.gui.tool import BurstFcsTool

    w = BurstFcsTool()
    w.setParent(parent)
    return w


def _make_diffusion_calc(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    from chisurf.plugins.fcs.fcs_calculator.wizard import ConfocalCalcWidget

    w = ConfocalCalcWidget()
    w.setParent(parent)
    return w


def _make_filter_calc(parent: QtWidgets.QWidget) -> QtWidgets.QWidget:
    from chisurf.plugins.fcs.fcs_filter_calculator.gui_parts.main_window import (
        FcsFilterCalculatorWidget,
    )

    w = FcsFilterCalculatorWidget()
    w.setParent(parent)
    return w


#: Optional, independent FCS tools shown below the correlator workflow. The
#: channel-definition, detector-setup and merger tools are omitted here because
#: the correlator workflow already owns those steps.
TOOL_PANELS = _apply_manifest_flags(
    [
        {
            "name": "2D-FLCS",
            "icon": "🟦",
            "factory": _make_2dflcs,
            "role": "flc_2d",
            "manifest": "fcs/flc_2d",
            "description": "Two-dimensional fluorescence lifetime correlation spectroscopy.",
        },
        {
            "name": "Lifetime-FCS Sim",
            "icon": Glyphs.DNA,
            "factory": _make_lfcs_sim,
            "role": "lfcs_sim",
            "manifest": "fcs/fcs_lfcs_sim",
            "description": "Simulate diffusing lifetime species (+ interconversion) and recover them by lifetime-filtered correlation.",
        },
        {
            "name": "Burst-wise FCS",
            "icon": Glyphs.SCIENCE,
            "factory": _make_burst_fcs,
            "role": "burst_fcs",
            "description": "Per-burst fluorescence correlation.",
        },
        {
            "name": "Diffusion Calc",
            "icon": "🧮",
            "factory": _make_diffusion_calc,
            "role": "diffusion_calc",
            "description": "Confocal diffusion / volume calculator.",
        },
        {
            "name": "Filter Calc",
            "icon": Glyphs.TEST,
            "factory": _make_filter_calc,
            "role": "filter_calc",
            "manifest": "fcs/fcs_filter_calculator",
            "description": "Filtered-FCS lifetime filter calculator.",
        },
    ]
)

#: The full navigation for the merged FCS tool: the correlator workflow, a
#: ``Tools`` group header, then the optional tools. Section headers are
#: non-selectable ``separator`` rows rendered by the shared shell.
FCS_PANELS = [
    {"name": "Correlator", "separator": True},
    *CORRELATOR_PANELS,
    {"name": "Tools", "separator": True},
    *TOOL_PANELS,
]


class FcsTool(FcsCorrelatorTool):
    """The unified FCS window: correlator workflow + optional tools."""

    def __init__(self, parent=None):
        super().__init__(parent=parent, panels=FCS_PANELS, title="FCS")


#: Backwards-compatible alias (this tool was formerly "FCS Tools").
FcsToolboxTool = FcsTool
