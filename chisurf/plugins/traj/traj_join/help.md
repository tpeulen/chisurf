# Join trajectories

Joins two trajectories into one DCD.

## Files

- **Trajectory 1**, **Trajectory 2** — the two DCDs. Drop them on the window
  (the first `.dcd` fills an empty row) or press **…**.
- **Topology** — the PDB that names the atoms; shared by both.

## Settings

- **Join mode** — *By time* writes every frame of trajectory 1, then every
  frame of trajectory 2 (they need the same atoms). *By atoms* places frame i
  of both side by side as one system (they need the same number of frames); the
  output has the atoms of both, so a topology for the combined system is needed
  to read it back.
- **Reverse trajectory 1 / 2** — last frame first, for the whole trajectory.
- **Chunk size** — frames written per block. The inputs are read whole; the
  block bounds the copy the join makes.

## Save joined…

Asks for the output DCD and writes it; the log says how many frames and atoms
were written. A mismatch (different atoms in time mode, different frame counts
in atoms mode) stops the join with a message under the button.

## Example

A trajectory joined in time with itself reversed runs forward and back: a
round trip whose last frame is its first.

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
