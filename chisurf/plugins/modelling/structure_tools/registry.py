"""The structure-modelling tools the native workspace hosts, in display order.

Mirrors the Qt hub's ``STRUCTURE_PANELS``. Entries with a native ``emtk``
factory open as embedded children; the rest are listed but open the standard
"native version pending" panel, exactly as the games hub treats its pending
games.
"""

from __future__ import annotations

STRUCTURE_TOOL_PANELS: list[dict] = [
    {
        "name": "FPS JSON Editor",
        "description": "Edit fps.json files for FRET accessible-volume modelling and fetch reference PDBs.",
        "emtk": None,
    },
    {
        "name": "Docking & Screening",
        "description": "FRET-restrained rigid-body docking, refinement and structure-library screening (IMP + IMP.bff).",
        "emtk": None,
    },
    {
        "name": "Kappa2 Distribution",
        "description": "Calculate and visualise the κ² orientation-factor distribution for FRET.",
        "emtk": "chisurf.plugins.calculator.kappa2_dist.gui.app:make_app",
    },
    {
        "name": "QuEst",
        "description": "Quenching estimator — dye-diffusion simulation of fluorescence quenching and decays.",
        "emtk": None,
    },
    {
        "name": "HydroPro",
        "description": "Run HYDROPRO / HYDRO++ hydrodynamic calculations on structural files.",
        "emtk": "chisurf.plugins.modelling.hydropro.app:make_app",
    },
    {
        "name": "Trajectory Tools",
        "description": "Combined workspace for trajectory alignment, conversion, energy, FRET, joining, clash removal, rotation/translation and topology saving.",
        "emtk": "chisurf.plugins.traj.traj_tools.app:make_app",
    },
]

__all__ = ["STRUCTURE_TOOL_PANELS"]
