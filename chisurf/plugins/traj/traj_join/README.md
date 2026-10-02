# Trajectory Joining Plugin

This plugin provides functionality to combine two molecular dynamics trajectory files into a single continuous trajectory.

## Features

- Joins two DCD trajectories (with the PDB topology that names their atoms)
- Two join modes: 'time' (all frames of 1, then all of 2) and 'atoms' (frame i of both side by side)
- Reverse either trajectory as a whole (last frame first)
- A mismatch (atoms in time mode, frame counts in atoms mode) stops the join instead of truncating

## Overview

The Trajectory Joining plugin enables users to combine two molecular trajectory files into a single 
continuous trajectory. This functionality is useful for analyzing simulations that were run in multiple segments or 
for combining related simulations into a single dataset.

The plugin provides a simple interface for loading two trajectory files, configuring how they should be joined, and 
saving the resulting combined trajectory. Users can choose between two joining modes: joining along the time axis 
(concatenating frames) or joining along the atom axis (stacking atoms). Additionally, users can reverse the order of 
either trajectory if needed.

By combining trajectory segments, users can perform analyses that span longer timescales or compare different 
simulation conditions within a unified framework.

## Requirements

- ChiSurf's trajectory readers and DCD writer (`chisurf.core.structure.trajectory_data`,
  `chisurf.core.fio.trajectory`); no Qt for the emtk window (`app.py`), Qt only for the legacy
  AutoForm widget (`widget.py`).

## Usage

1. Open *Structure > Trajectory > Join* (or the *Join* panel of Traj Tools).
2. Choose *Trajectory 1*, *Trajectory 2* (**…**, or drop `.dcd` files: each fills an empty row) and the topology.
3. Pick the join mode, tick *Reverse* for a trajectory to run backwards, set the block size.
4. Press **💾 Save joined…** and pick the output `.dcd`; the log says how many frames and atoms were written.

**📖 Guide** walks through these steps; **❓ Help** has the details.

## Applications

The Trajectory Joining plugin can be used for:
- Combining multiple simulation segments into a single continuous trajectory
- Merging trajectories from replica exchange or parallel tempering simulations
- Creating longer trajectories for improved statistical sampling
- Comparing different simulation conditions within a unified analysis framework
- Preparing trajectories for analyses that require long timescales
- Consolidating related simulations for simplified data management
- Creating custom trajectory ensembles from selected simulation segments

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.
