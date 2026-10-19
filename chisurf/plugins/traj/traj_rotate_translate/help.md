# Rotate / translate trajectory

Applies one rigid-body transform to every frame, **x′ = R x + t**: rotate
first, then translate (Å). The result is a new DCD; frame times are kept.

## Files

- **Trajectory** — the DCD to transform. Drop it on the window or press **…**.
- **Topology** — the PDB that names the atoms; a DCD stores coordinates only.

## Settings

- **Rotation matrix** — the 3×3 matrix R. A matrix that is not a rotation
  (RᵀR ≠ 1, or det R = −1) shears, scales or mirrors the molecule; the window
  says so under the matrix, but the save still runs.
- **Translation [Ang.]** — the vector t added after the rotation.
- **Stride** — read every Nth frame.

## Save rotated/translated…

Asks for the output DCD, then transforms chunk by chunk. The log lists each
step; a failure is shown under the button.

## Example

A 90° rotation about z, R = ((0, −1, 0), (1, 0, 0), (0, 0, 1)), plus 10 Å
along x moves a point (x, y, z) to (10 − y, x, z).

## When to use it

To place a trajectory into the frame of a reference structure, for example
with the rotation and translation from a superposition done elsewhere.

## Example data and the other trajectory tools

No trajectory of your own? Use the T4 lysozyme ensemble in
`chisurf/plugins/modelling/fret/examples/olga_t4l/`: `3GUN_NMSim_cl-rep_894.dcd`
(894 frames) with the topology `3GUN_NMSim_cl-rep-001.pdb`.

This is one of the eight trajectory tools of **Structure › Trajectory**, each its
own window. A trajectory is usually prepared in the order **Align** (superpose on
frame 0), **Remove Clashed** (drop frames that cannot exist, on Cα below 3.8 Å),
then **FRET** (R_DA, κ² and k_FRET per frame).

## Further reading

- [Trajectory tools guide](docs/guides/81_trajectory_tools.md)
- [Structure trajectories](docs/concepts/structure_trajectories.md)
