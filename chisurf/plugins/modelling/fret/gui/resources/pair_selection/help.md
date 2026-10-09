# Optimal FRET pair selection

Which pairs of labelling sites should be measured by FRET to tell the conformations of a molecule apart? The window
takes a trajectory, computes the FRET efficiency of every candidate pair in every frame, and adds pairs one at a time:
each is the pair that most reduces the mean RMSD between the conformations the chosen pairs cannot yet distinguish
(the greedy selection of Olga, `IMP.bff.select_probe_pairs`).

## Inputs

* **Trajectory**: the conformations. Choose the file with the **...** button or drop it on the window. The window
  reads every **Stride**-th frame.
* **Topology (optional)**: a PDB naming the atoms. A DCD stores coordinates only, so it needs one.
* **FPS JSON (optional)**: when given, its labelling positions are the sites and its distances the candidate pairs.
  Without it, every pair of the residues listed under *Candidate sites from residues* is a candidate: **Chain**,
  **Residues (PDB resSeq)** (numbers and ranges as written in the PDB, e.g. `35-50,85-95`) and the
  **Attachment atom** (CB, or CA where a residue has no CB).
* **R0**: the Forster radius used for every pair (a pair that the FPS JSON gives its own R0 keeps it).
* **Use AV backend**, **AV samples**, **Max AV points** (FPS JSON only): compute the efficiency from the dyes' accessible
  volumes rather than from the attachment-atom distance. When the accessible volumes cannot be computed the run
  falls back to the distance and says so.
* **Max pairs**, **Expected E error**, **Unique pairs only** and **RMSD atom selection** steer the selection.

A dropped file goes to the row it fits: a PDB (`.pdb`, `.ent`, `.cif`) to *Topology*, a `.json` to *FPS JSON*, any
other file to *Trajectory*.

## Result

The table lists the pairs in the order they were added and the mean RMSD (in Angstrom) after each; the plot shows
that decay. **Export** writes the same table to a text file.

## Limits

The run computes in the background; **Run selection** is unavailable while it works. A trajectory that does not
exist, fewer than two usable residues, or an FPS JSON that yields no pair is reported in a message and the status line.
