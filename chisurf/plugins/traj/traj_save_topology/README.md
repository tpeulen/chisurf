# Topology File Generator Plugin

This plugin extracts and saves topology information from the first frame of molecular dynamics trajectories.

## Features

- Extraction of topology from the first frame of a trajectory
- Saving topology as a PDB file
- Simple and intuitive interface

## Overview

The Topology File Generator plugin enables users to extract and save topology information from the first frame of a 
molecular trajectory. Topology files are essential for many molecular dynamics simulations and analysis tools, 
providing the connectivity and parameter information needed to interpret coordinate data correctly.

The plugin provides a simple interface for loading a trajectory file and saving its first frame as a PDB file. 
This is useful for extracting a representative structure from a trajectory for further analysis or visualization.

## Requirements

- ChiSurf's trajectory readers (`chisurf.core.structure.trajectory_data`); no Qt for
  the emtk window (`app.py`), Qt only for the legacy AutoForm widget (`widget.py`).

## Usage

1. Open *Structure > Trajectory > Save Topol* (or the *Save Topol* panel of Traj Tools).
2. Choose the trajectory: press **…** beside *Trajectory*, or drop a `.dcd` on the window.
3. Choose the topology: press **…** beside *Topology*, or drop a `.pdb`/`.cif`/`.ent`.
   A DCD stores coordinates only, so the topology is required for it.
4. Press **💾 Save topology…** and pick a file name; frame 0 is written as a PDB and
   every step is listed in the log.

**📖 Guide** walks through these steps; **❓ Help** has the details.

## Applications

The Topology File Generator plugin can be used for:
- Extracting a representative structure from a trajectory for visualization
- Saving the first frame of a trajectory as a PDB file for further analysis
- Creating input files for molecular viewers or analysis tools that require PDB format
- Preserving the initial structure of a simulation for reference

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.
