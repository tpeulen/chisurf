# FRET Analysis from Molecular Dynamics Trajectories

This plugin writes, for every frame of a molecular dynamics trajectory, the donor–acceptor distance, the
orientation factor κ² and the FRET rate constant, from two atoms per dye.

## Features

- DCD trajectories with the PDB topology that names their atoms (either picked first)
- Donor and acceptor dipoles of two atoms each, picked by chain, residue and atom
- κ² per frame from the dipoles, or the isotropic 2/3 with one atom per dye
- A CSV per trajectory: `Frame`, `time[ns]`, `RDA[Ang]`, `kappa`, `kappa2`, `FRETrate[1/ns]`
- No efficiency and no averaging in the table: which average applies depends on the timescales

## Overview

Förster Resonance Energy Transfer (FRET) is a powerful technique for measuring distances between fluorescent labels in biomolecules. This plugin bridges the gap between computational molecular dynamics simulations and experimental FRET measurements by calculating theoretical FRET efficiency values from MD trajectories.

By analyzing the distances between specified residues over time and applying appropriate models for dye behavior, the plugin enables direct comparison between simulated structural dynamics and experimental FRET data. This comparison is valuable for validating simulation results, refining structural models, and interpreting experimental observations in the context of molecular motion.

Ideal for comparing experimental FRET data with structural models from molecular dynamics simulations, this plugin facilitates the integration of computational and experimental approaches in structural biology.

## Requirements

- ChiSurf's trajectory readers (`chisurf.core.structure.trajectory_data`) and κ² code; no Qt for the emtk window
  (`app.py`), Qt only for the legacy AutoForm widget (`gui.py`).

## Usage

1. Open *Structure > Trajectory > FRET* (or the *FRET* panel of Traj Tools).
2. Choose the trajectory and its topology (**…**, or drop a `.dcd` and a `.pdb`).
3. Pick the two donor and the two acceptor atoms (chain, residue, atom).
4. Set R0, τ0, the time between frames and whether κ² is computed from the dipoles.
5. Press **▶ Process trajectory** and pick the output CSV; the log lists the frames written.

**📖 Guide** walks through these steps; **❓ Help** has the details.

## Applications

- Validation of molecular dynamics simulations against experimental FRET data
- Interpretation of experimental FRET results in the context of structural dynamics
- Investigation of conformational changes and molecular flexibility
- Refinement of structural models based on FRET constraints
- Design of optimal labeling strategies for FRET experiments
- Study of biomolecular interactions and complex formation

## Theory

The plugin calculates FRET efficiency (E) using the Förster equation:
E = 1 / [1 + (r/R₀)⁶]

Where:
- r is the distance between donor and acceptor
- R₀ is the Förster radius (the distance at which E = 0.5)

For the accessible volume model, the plugin considers the spatial distribution of the dyes around their attachment points, providing a more realistic representation of the experimental setup.

## License

This plugin is part of the ChiSurf package and is distributed under the same license.

## Author

This plugin was created as part of the ChiSurf project.