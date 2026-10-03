"""The trajectory tools the native workspace hosts, in display order.

Mirrors the Qt hub's ``_tool_factories``; every entry points at the child's
native EMTK factory so the hub stays Qt-free.
"""

from __future__ import annotations

TOOL_PANELS: list[dict] = [
    {
        "name": "Align",
        "description": "Align molecular dynamics trajectories to a reference frame or structure.",
        "emtk": "chisurf.plugins.traj.traj_align.app:make_app",
    },
    {
        "name": "Convert",
        "description": "Convert molecular dynamics trajectory files between supported formats.",
        "emtk": "chisurf.plugins.traj.traj_convert.app:make_app",
    },
    {
        "name": "Energy Calc",
        "description": "Calculate potential energy components for structures and trajectories.",
        "emtk": "chisurf.plugins.traj.potential_energy.app:make_app",
    },
    {
        "name": "FRET",
        "description": "Calculate FRET observables from molecular dynamics trajectories.",
        "emtk": "chisurf.plugins.traj.fret_trajectory.app:make_app",
    },
    {
        "name": "Join",
        "description": "Join or stack molecular dynamics trajectories.",
        "emtk": "chisurf.plugins.traj.traj_join.app:make_app",
    },
    {
        "name": "Remove Clashed",
        "description": "Remove frames containing steric clashes from trajectories.",
        "emtk": "chisurf.plugins.traj.traj_remove_clashes.app:make_app",
    },
    {
        "name": "Rot Translate",
        "description": "Apply rigid-body rotation and translation to trajectories.",
        "emtk": "chisurf.plugins.traj.traj_rotate_translate.app:make_app",
    },
    {
        "name": "Save Topol",
        "description": "Save topology or first-frame structure files from trajectories.",
        "emtk": "chisurf.plugins.traj.traj_save_topology.app:make_app",
    },
]

__all__ = ["TOOL_PANELS"]
