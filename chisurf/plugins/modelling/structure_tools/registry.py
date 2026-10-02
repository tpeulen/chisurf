"""The structure-modelling tools the native workspace hosts, in display order.

Mirrors the Qt hub's ``STRUCTURE_PANELS``. Every entry has a native ``emtk``
factory: the FPS JSON editor, docking and QuEst are cards of this plugin
(``cards/``), the others are the apps of their own plugins.
"""

from __future__ import annotations

STRUCTURE_TOOL_PANELS: list[dict] = [
    {
        "name": "FPS JSON Editor",
        "group": 0,
        "description": "Edit fps.json files for FRET accessible-volume modelling and fetch reference PDBs.",
        "emtk": "chisurf.plugins.modelling.structure_tools.cards.fps_json:make_app",
    },
    {
        "name": "Docking & Screening",
        "group": 0,
        "description": "FRET-restrained rigid-body docking, refinement and structure-library screening (IMP + IMP.bff).",
        "emtk": "chisurf.plugins.modelling.structure_tools.cards.docking:make_app",
    },
    {
        "name": "Kappa2 Distribution",
        "group": 0,
        "description": "Calculate and visualise the κ² orientation-factor distribution for FRET.",
        "emtk": "chisurf.plugins.calculator.kappa2_dist.gui.app:make_app",
    },
    {
        "name": "QuEst",
        "group": 1,
        "description": "Quenching estimator — dye-diffusion simulation of fluorescence quenching and decays.",
        "emtk": "chisurf.plugins.modelling.structure_tools.cards.quest:make_app",
    },
    {
        "name": "HydroPro",
        "group": 1,
        "description": "Run HYDROPRO / HYDRO++ hydrodynamic calculations on structural files.",
        "emtk": "chisurf.plugins.modelling.hydropro.app:make_app",
    },
    {
        "name": "Trajectory Tools",
        "group": 2,
        "description": "Combined workspace for trajectory alignment, conversion, energy, FRET, joining, clash removal, rotation/translation and topology saving.",
        "emtk": "chisurf.plugins.traj.traj_tools.app:make_app",
    },
]

__all__ = ["STRUCTURE_TOOL_PANELS"]
