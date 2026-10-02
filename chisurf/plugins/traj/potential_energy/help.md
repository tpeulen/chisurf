# Potential energy calculator

Scores **every frame of a DCD trajectory** with the potentials you choose, each with its own weight, and writes one
row per frame to a tab-separated text file: the frame number followed by one column per potential. Use it to find
strained or unfavourable conformations along a simulation, or to compare conformations with the same scoring.

## Files

- **Trajectory** — the DCD to score. Drop it on the window or press **…**.
- **Topology** — the PDB that names the atoms; a DCD stores coordinates only, and every potential scores by atom
  name. A dropped `.pdb`, `.cif` or `.ent` goes here, a `.dcd` into Trajectory.

## Potentials

Choose a type, set its parameters and press **Add**. The **Weight** field scales the next potential you add. Added
potentials are listed in the table; **double-click** a row (or select it and press Delete) to remove it. The
parameters of a type are kept while you look at another type; after **Add** they are back at their defaults.

- **H-Bond** — hydrogen-bond contacts (C-alpha and heavy-atom cutoffs, which pair types count, the potential table).
- **AV-Potential** — accessible-volume restraints from an FPS labeling file.
- **Iso-UNRES**, **Miyazawa-Jernigan** — statistical contact potentials (C-alpha cutoff, potential table).
- **Go-Potential** — native and non-native contacts.
- **ASA-Calpha** — accessible surface area of the C-alpha atoms.
- **Clash potential** — van-der-Waals overlaps beyond a tolerance.
- **Ramachandran** — backbone dihedral potential.
- **Radius of Gyration** — compactness, no parameters.

## Stride

Only every Nth frame is scored. The written frame numbers count source frames, so a strided run is labelled with the
real frame it scored.

## Process

Asks for the output file, then scores the frames on a worker thread; the button shows how many are done. The log says
what was written; a failure is shown under the button. The potentials need the molecular-modelling kernels; without
them **Add** reports why in the window.

## Further reading

- [Trajectory tools guide](docs/guides/81_trajectory_tools.md)
- [Structure trajectories](docs/concepts/structure_trajectories.md)
