# Remove clashed frames

Writes a new DCD with only the frames in which **no two selected atoms are
closer than the minimum distance**. The kept frames keep their source times,
written beside the DCD, so the gaps the removed frames leave stay visible.

## Files

- **Trajectory** — the DCD to filter. Drop it on the window or press **…**.
- **Topology** — the PDB that names the atoms; it also resolves the selection.

## Settings

- **Atom selection** — an atom-selection expression, for example
  `name CA` or `name CA and resSeq 1 to 256`. Every pair of the selected atoms
  is tested in every frame.
- **Stride** — read every Nth frame.
- **Min distance** — the threshold in Ångström.

## What the test does not know

There is no bond exclusion and no per-element radius: two bonded atoms are a
clash if the threshold exceeds their bond length. On all heavy atoms, 2 Å
flags every frame. Use a sparse set such as Cα, below the 3.8 Å spacing of
consecutive Cα atoms, and look at how many frames go: the log says *Kept N of
M frames*. If a threshold drops most of the ensemble, the threshold is wrong,
not the ensemble.

## Further reading

- [Trajectory tools guide](docs/guides/81_trajectory_tools.md)
- [Structure trajectories](docs/concepts/structure_trajectories.md)
