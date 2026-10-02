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

## Further reading

- [Trajectory tools guide](docs/guides/81_trajectory_tools.md)
- [Structure trajectories](docs/concepts/structure_trajectories.md)
