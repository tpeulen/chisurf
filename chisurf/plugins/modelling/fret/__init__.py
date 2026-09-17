"""
FRET Docking & Screening Plugin
================================

Consolidates functionality from FPS (FRET Positioning System) and
OLGA (Oligonucleotide Library Generation and Analysis) as a
self-contained ChiSurf plugin using LabelLib (Windows) or IMP.bff
(macOS/Linux) for accessible-volume calculations and IMP for
structure I/O and RMF output.

Reference
---------
- Kalinin, S., Peulen, T., et al. (2012). *Nature Methods* 9(12), 1218-1225.
- Dimura, M., Peulen, T., et al. (2016). *Nature Communications* 7, 10947.
"""

from __future__ import annotations

name = "Structure:FRET:Docking & Screening"
description = (
    "Rigid-body FRET-restrained docking, structure-library screening, "
    "and Metropolis Monte Carlo sampling using accessible-volume (AV) "
    "calculations."
)
cli_entrypoint = "fret=chisurf.plugins.modelling.fret.cli.main:main"

# Expose core modules and actions.
# IMP + IMP.bff PMI-based docking engine — the maintained backend (replaces the
# removed hand-rolled spring/Verlet engine).
from .core import (
    av,
    distance,
    engine,
    evaluate,
    imp_engine,
    io,
    olga_greedy,
    pair_selection,
    results,
    screening,
    trajectory,
)
from .core.av import compute_av, compute_avs_for_structure, load_structure_with_vdw
from .core.distance import (
    average_distance,
    chi2_score,
    distance_between_mean_positions,
    mean_fret_distance,
    model_distance,
)
from .core.engine import DistanceRestraint, RigidBody, SpringParameters
from .core.imp_engine import DockingParameters, DockingResult, dock, refine, score, screen
from .core.io import load_structure, write_pdb
from .core.screening import score_single_structure, screen_structure_library

# ChiSurf plugin entry point.
if __name__ == "plugin":
    # ``FretDockingTool`` is the maintained AutoForm-based GUI driven by the
    # IMP/IMP.bff engine; the legacy ``FretDockWizard`` (and its spring engine)
    # has been removed.
    from .gui import FretDockingTool

    window = FretDockingTool()
    window.show()
