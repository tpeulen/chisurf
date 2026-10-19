# Trajectory converter

Rewrites a range of frames of a trajectory as one DCD or PDB file, or as one
file per frame.

## Input

- **Topology** — the PDB that names the atoms; a DCD stores coordinates only.
- **Trajectory** — the DCD to read. With **Input is a folder of PDBs** the
  row takes a folder instead, and every `*.pdb` in it is read in name order as
  consecutive frames (they must have the same atoms).
- **Target folder** — where the output goes. It must exist.
- **First frame**, **Last frame**, **Stride** — the frames first, first + stride,
  … up to and including the last frame. Last frame −1 means the end.

## Output

- **Filename** + **Format** — one file `{filename}.dcd` or `.pdb` (a PDB holds
  one MODEL per frame).
- **Split into one file per frame** — `{filename}_{frame:08d}{format}` per
  selected frame, numbered by the frame it came from.
- **▶ Convert** — the log says how many frames (or files) were written.

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
