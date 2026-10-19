"""
Trajectory Joining Tool

This plugin provides functionality to combine multiple molecular dynamics
trajectory files into a single continuous trajectory. Features include:
- Support for multiple input trajectory formats
- Options to align frames between trajectories
- Ability to remove duplicate frames at trajectory boundaries
- Support for concatenating trajectories with different topologies
- Options to filter or select specific parts of each trajectory

Joining trajectories is useful for analyzing simulations that were run in
multiple segments or for combining related simulations into a single dataset.
"""

# Plugin brand icon (unified emoji set)
icon = "🧷"

# Define the plugin name - this will appear in the Plugins menu
name = "Structure:Trajectory:Join"
