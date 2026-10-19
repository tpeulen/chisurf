# Align trajectory

Superposes every frame onto **frame 0** (least-squares rotation and
translation of the fitting atoms) and writes the result as a new DCD. Only
coordinates change: the frame times of the source are kept, so a strided
read keeps its real spacing.

## Files

- **Trajectory** — the DCD to align. Drop it on the window or press **…**.
- **Topology** — the PDB that names the atoms; a DCD stores coordinates only.
  A dropped `.pdb`, `.cif` or `.ent` goes here, a `.dcd` into Trajectory.

## Settings

- **Atom selection** — comma-separated atom ids (0-based) of the fitting set.
  Empty aligns on all atoms. A token that is not an id stops the run with a
  message in the log, rather than fitting on fewer atoms than asked for.
- **Stride** — read every Nth frame.

## Save aligned…

Asks for the output DCD, then aligns chunk by chunk (the trajectory need not
fit in memory). The log lists each step; a failure is shown under the button.

## When to use it

Align before anything that compares frames: RMSD, per-atom fluctuations,
visual inspection. FRET distances and κ² are internal coordinates and do not
need it. Fit on the domain you consider the reference, so the motion of the
rest shows relative to it.

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
