"""
Trajectory Clash Removal Tool

This plugin identifies and removes frames from molecular dynamics trajectories
that contain steric clashes or other structural problems. Features include:
- Detection of atom-atom clashes based on van der Waals radii
- Customizable clash criteria and thresholds
- Ability to focus on specific regions or residues
- Options to repair clashed frames or remove them entirely
- Statistical reporting on the number and types of clashes

Removing clashed frames is important for preparing clean trajectories for
further analysis, especially when working with modeled structures or
trajectories from enhanced sampling methods.
"""

# Plugin brand icon (unified emoji set)
icon = "💢"

# Define the plugin name - this will appear in the Plugins menu
name = "Structure:Trajectory:Remove Clashed"


def __getattr__(attribute):
    if attribute == "RemoveClashedFrames":
        from chisurf.plugins.traj.traj_remove_clashes.widget import RemoveClashedFrames
        return RemoveClashedFrames
    raise AttributeError(attribute)


# When the plugin is loaded as a module with __name__ == "plugin",
# this code will be executed
if __name__ == "plugin":
    # Create an instance of the RemoveClashedFrames class
    window = __getattr__("RemoveClashedFrames")()
    # Show the window
    window.show()
