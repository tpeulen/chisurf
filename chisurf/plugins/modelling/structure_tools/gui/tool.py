"""StructureToolsTool — unified structure-modelling panel using NavigationPanelTool.

A single window with a left navigation list and a lazily-loaded right panel area.
Each panel embeds one of the existing structure tools **unchanged**:

    1. FPS JSON Editor          — FpsJsonEditorTool
    2. FRET Docking & Screening — FretDockingTool
    3. Kappa2 Distribution      — Kappa2Dist
    ───────────────────────────  (separator)
    4. QuEst                    — QuEstWindow
    5. HydroPro                 — HydroGui
    ───────────────────────────  (separator)
    6. Trajectory Tools         — TrajectoryToolsTool

Panels are imported lazily inside their factory functions so the combined window
opens fast and a sub-tool whose heavy dependencies are missing only breaks its own
panel (NavigationPanelTool renders an error panel) rather than the whole window.
"""

from __future__ import annotations

import logging

from qtpy import QtWidgets

from chisurf.gui.widgets.navigation import NavigationPanelTool, embed_mainwindow

logger = logging.getLogger(__name__)


# ``QMainWindow`` sub-tools are flattened with the shared ``embed_mainwindow``
# helper (see chisurf.gui.widgets.navigation) so no nested QMainWindow remains.
_embed_mainwindow = embed_mainwindow


# ---------------------------------------------------------------------------
# Panel factory functions — each imported lazily to keep startup fast.
# QMainWindow-based tools are flattened via ``_embed_mainwindow`` so their
# DockArea tabs remain clickable when embedded (see helper above).
# ---------------------------------------------------------------------------


def _fps_json_editor(parent: StructureToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.modelling.fps_json_editor.gui.tool import FpsJsonEditorTool

    return _embed_mainwindow(FpsJsonEditorTool())


def _docking(parent: StructureToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.modelling.fret.gui.dock_tool import FretDockingTool

    return FretDockingTool()


def _kappa2(parent: StructureToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.calculator.kappa2_dist.gui.tool import Kappa2Dist

    return Kappa2Dist()


def _quest(parent: StructureToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.quenching_estimator import QuEstWindow

    return _embed_mainwindow(QuEstWindow())


def _hydropro(parent: StructureToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.modelling.hydropro.gui.tool import HydroProTool

    return _embed_mainwindow(HydroProTool())


def _traj_tools(parent: StructureToolsTool) -> QtWidgets.QWidget:
    from chisurf.plugins.traj.traj_tools.gui.tool import TrajectoryToolsTool

    return TrajectoryToolsTool()


# ---------------------------------------------------------------------------
# Panel list
# ---------------------------------------------------------------------------

STRUCTURE_PANELS: list[dict] = [
    {
        "name": "1. FPS JSON Editor",
        "icon": "📝",
        "description": "Edit fps.json files for FRET accessible-volume modelling and fetch reference PDBs.",
        "factory": _fps_json_editor,
        "role": "fps_json_editor",
    },
    {
        "name": "2. Docking & Screening",
        "icon": "🎯",
        "description": "FRET-restrained rigid-body docking, refinement and structure-library screening (IMP + IMP.bff).",
        "factory": _docking,
        "role": "docking",
    },
    {
        "name": "3. Kappa2 Distribution",
        "icon": "📐",
        "description": "Calculate and visualise the κ² orientation-factor distribution for FRET.",
        "factory": _kappa2,
        "role": "kappa2",
    },
    {
        "name": "────────",
        "icon": "",
        "separator": True,
        "role": "separator_compute",
    },
    {
        "name": "QuEst",
        "icon": "💡",
        "description": "Quenching estimator — dye-diffusion simulation of fluorescence quenching and decays.",
        "factory": _quest,
        "role": "quest",
    },
    {
        "name": "HydroPro",
        "icon": "🌊",
        "description": "Hydrodynamic property prediction (HydroPro) from atomic structures.",
        "factory": _hydropro,
        "role": "hydropro",
    },
    {
        "name": "────────",
        "icon": "",
        "separator": True,
        "role": "separator_traj",
    },
    {
        "name": "Trajectory Tools",
        "icon": "🎞️",
        "description": "Combined workspace for trajectory alignment, conversion, energy calculation and FRET.",
        "factory": _traj_tools,
        "role": "traj_tools",
    },
]


class StructureToolsTool(NavigationPanelTool):
    """Unified structure-modelling toolbox with a left-navigation panel."""

    def __init__(self, parent=None):
        super().__init__(
            title="🧬 Structure Tools",
            panels=STRUCTURE_PANELS,
            parent=parent,
            minimum_size=(900, 600),
            initial_size=(1200, 750),
            navigation_width=210,
        )


__all__ = ["StructureToolsTool"]
