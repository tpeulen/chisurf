# Trajectory Alignment Plugin

This plugin provides tools for aligning molecular dynamics trajectories to the first frame of the trajectory.

## Features

- Load DCD trajectories with the PDB topology that names their atoms
- Select specific atoms for alignment
- Align to the first frame of the trajectory as reference
- Apply RMSD-based alignment algorithms
- Save aligned trajectories for further analysis

## Overview

The Trajectory Alignment plugin enables users to align molecular dynamics trajectories to the first frame of the 
trajectory. Proper alignment is essential for analyzing conformational changes, calculating order parameters, and 
comparing different simulations.

The plugin provides a user-friendly interface for loading trajectories and selecting alignment criteria. Users 
can choose specific atoms to use for alignment by providing a comma-separated list of atom IDs, which is particularly 
useful when focusing on specific structural elements while allowing other regions to move freely. The RMSD-based 
alignment algorithms ensure optimal superposition of the selected structural elements.

The aligned trajectories can be saved for further analysis, ensuring that all subsequent calculations are performed 
in a consistent reference frame.

## Requirements

- ChiSurf's trajectory readers and DCD writer (`chisurf.core.structure.trajectory_data`,
  `chisurf.core.fio.trajectory`); no Qt for the emtk window (`app.py`), Qt only for the legacy
  AutoForm widget (`widget.py`).

## Usage

1. Open *Structure > Trajectory > Align* (or the *Align* panel of Traj Tools).
2. Choose the trajectory (**…** or drop a `.dcd`) and its topology (**…** or drop a `.pdb`).
3. Enter the fitting atoms as comma-separated atom ids in *Atom selection* (empty = all atoms).
4. Set *Stride* to read every Nth frame (frame times are kept).
5. Press **💾 Save aligned…** and pick the output `.dcd`; the log lists each step.

**📖 Guide** walks through these steps; **❓ Help** has the details.

## Applications

The Trajectory Alignment plugin can be used for:
- Removing overall rotational and translational motion from trajectories
- Focusing analysis on specific structural changes by aligning stable regions
- Preparing trajectories for principal component analysis or other conformational analyses
- Creating a consistent reference frame for trajectory analysis
- Improving visualization of molecular dynamics by removing global motions
- Preparing aligned trajectories for further analysis in ChiSurf or other software

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.
