"""Trajectory rotation and translation tool.

Apply rigid-body transformations (a 3x3 rotation matrix and a translation
vector) to every frame of a molecular-dynamics trajectory and stream the result
to a new HDF5 trajectory.
"""

from __future__ import annotations

# Plugin brand icon (unified emoji set)
icon = "🔃"

from chisurf.plugins.traj.traj_rotate_translate.widget import (
    RotateTranslateTrajectoryWidget,
)

# Define the plugin name - this will appear in the Plugins menu
name = "Structure:Trajectory:Rotate/Translate"

__all__ = ["RotateTranslateTrajectoryWidget"]


# When the plugin is loaded as a module with __name__ == "plugin",
# this code will be executed
if __name__ == "plugin":
    window = RotateTranslateTrajectoryWidget()
    window.show()
