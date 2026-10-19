# Save topology

Writes **frame 0** of a trajectory as a PDB: the atom names come from the
topology, the coordinates from the trajectory. The coordinates match frame 0
of the DCD to within 2×10⁻⁶ Å.

## Files

- **Trajectory** — the DCD to read. Drop it on the window or press **…**.
- **Topology** — the PDB that names the atoms. A DCD stores coordinates
  only, so it cannot be read without one. A dropped `.pdb`, `.cif` or
  `.ent` goes here, a `.dcd` into Trajectory.

## Save topology…

Asks where to write the PDB, then reads frame 0 and writes it. The log lists
each step; a failure is shown under the button and in the log. Closing the
save dialog logs *Save cancelled*.

## When to use it

Most programs expect the starting structure next to a trajectory. Since the
topology is needed to read the DCD at all, the PDB written here is in
practice the first frame of the run in that topology's atom order.

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
