"""Trajectory rotation and translation tool.

Apply rigid-body transformations (a 3x3 rotation matrix and a translation
vector) to every frame of a molecular-dynamics trajectory and stream the result
to a new HDF5 trajectory.
"""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🔃"

# Define the plugin name - this will appear in the Plugins menu
name = "Structure:Trajectory:Rotate/Translate"
