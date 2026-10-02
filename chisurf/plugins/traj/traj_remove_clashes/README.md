# Trajectory Clash Removal Plugin

Writes a new DCD with only the frames of a molecular dynamics trajectory in which no two selected
atoms are closer than a minimum distance.

## Features

- Pairwise distance test on an atom selection (e.g. `name CA`), one threshold in Ångström
- No bond exclusion and no per-element radii: use a sparse selection
- Stride; the kept frames keep their source times (written beside the DCD)
- The log reports how many frames were kept
- Chunked reading, so the trajectory need not fit in memory

## Requirements

- ChiSurf's trajectory readers and DCD writer (`chisurf.core.structure.trajectory_data`,
  `chisurf.core.fio.trajectory`); no Qt for the emtk window (`app.py`), Qt only for the legacy
  AutoForm widget (`widget.py`).

## Usage

1. Open *Structure > Trajectory > Remove Clashed* (or the *Remove Clashed* panel of Traj Tools).
2. Choose the trajectory (**…** or drop a `.dcd`) and its topology (**…** or drop a `.pdb`).
3. Enter the atom selection, the stride and the minimum distance (Å).
4. Press **💾 Save clash-free…** and pick the output `.dcd`; the log says *Kept N of M frames*.

**📖 Guide** walks through these steps; **❓ Help** has the details.

## Applications

The Trajectory Clash Removal plugin can be used for:
- Cleaning trajectories from homology modeling or structure prediction
- Removing artifacts from enhanced sampling simulations
- Preparing trajectories for docking or other structure-based analyses
- Identifying problematic regions in protein models
- Quality control of molecular dynamics simulations
- Improving the reliability of structural analysis by removing physically unrealistic conformations
- Educational demonstrations of molecular structure validation
- Preprocessing trajectories for visualization or presentation

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.