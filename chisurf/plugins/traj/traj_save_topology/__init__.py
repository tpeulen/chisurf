"""
Topology File Generator

This plugin extracts and saves topology information from molecular structures
and trajectories. Features include:
- Support for multiple topology file formats (PDB, PSF, TOP, etc.)
- Ability to extract topology from trajectory frames
- Options to select specific atoms, residues, or chains
- Support for preserving or modifying bond information
- Validation of topology consistency

Topology files are essential for many molecular dynamics simulations and
analysis tools, providing the connectivity and parameter information needed
to interpret coordinate data correctly.
"""

# Plugin brand icon (unified emoji set)
icon = "💾"

# Define the plugin name - this will appear in the Plugins menu
name = "Structure:Trajectory:Save Topol"
