# Trajectory to FRET

Writes, for every frame of a trajectory, the donor–acceptor distance, the
orientation factor and the FRET rate,
k = 3/2 · κ² · (R0/R)⁶ / τ0. The dye transition dipoles are taken from two
atoms each.

## Reference

- **Trajectory** — the DCD (several may be picked; each gets its own table).
- **Topology** — the PDB that names the atoms; the pickers list its atoms.
  Either file may be chosen first.
- **Stride** — read every Nth frame.

## Dipole atoms

Two atoms for the **Donor** and two for the **Acceptor**, each picked by
chain, residue and atom. With **Dipole (κ2)** on, the distance is taken
between the dipole centres and κ² is computed per frame; off, only the first
atom of each dye is used and κ² = 2/3.

## Parameters

- **R0 [Ang]** — the Förster radius for κ² = 2/3.
- **τ0 [ns]** — donor lifetime without acceptor.
- **t-step [ns]** — time between trajectory frames; sets the `time[ns]` column.

## Process trajectory

Asks for the output CSV and writes the columns `Frame`, `time[ns]`,
`RDA[Ang]`, `kappa`, `kappa2`, `FRETrate[1/ns]`. The table stores no
efficiency and does no averaging on purpose: which average applies depends on
the timescales.

Atoms are not dyes: for labelled positions, model the dye clouds with an
accessible volume.

## Further reading

- [Trajectory tools guide](docs/guides/81_trajectory_tools.md)
- [Structure trajectories](docs/concepts/structure_trajectories.md)
- [Accessible volumes](docs/guides/23_accessible_volume.md)
