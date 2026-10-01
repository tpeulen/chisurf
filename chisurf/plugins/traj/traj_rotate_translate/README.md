# Trajectory Rotation and Translation Plugin

Applies one rigid-body transform, x′ = R x + t, to every frame of a molecular dynamics trajectory
and writes the result as a new DCD.

## Features

- A 3×3 rotation matrix R and a translation t (Å), entered numerically
- A warning when R is not a rotation (RᵀR ≠ 1 shears or scales, det R = −1 mirrors)
- Stride, with the source frame times kept
- Chunked reading, so the trajectory need not fit in memory

## Requirements

- ChiSurf's trajectory readers and DCD writer (`chisurf.core.structure.trajectory_data`,
  `chisurf.core.fio.trajectory`); no Qt for the emtk window (`app.py`), Qt only for the legacy
  AutoForm widget (`widget.py`).

## Usage

1. Open *Structure > Trajectory > Rot Translate* (or the *Rot Translate* panel of Traj Tools).
2. Choose the trajectory (**…** or drop a `.dcd`) and its topology (**…** or drop a `.pdb`).
3. Enter R row by row in *Rotation matrix* and t in *Translation [Ang.]*.
4. Set *Stride* to read every Nth frame.
5. Press **💾 Save rotated/translated…** and pick the output `.dcd`; the log lists each step.

**📖 Guide** walks through these steps; **❓ Help** has the details.

## Applications

The Trajectory Rotation and Translation plugin can be used for:
- Preparing structures for docking or binding site analysis
- Aligning multiple structures for comparison
- Setting up initial configurations for molecular dynamics simulations
- Orienting molecules for optimal visualization or presentation
- Standardizing the orientation of structures for consistent analysis
- Creating symmetry-related copies of molecular structures
- Educational demonstrations of molecular geometry and symmetry
- Preparing structures for specific analytical techniques that require particular orientations

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.