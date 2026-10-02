# QuEst: quenching and FRET of a tethered dye

QuEst (Peulen, Opanasyuk and Seidel, [10.1021/acs.jpcb.7b03441](https://doi.org/10.1021/acs.jpcb.7b03441)) simulates a dye on a flexible linker diffusing over a protein. Contact with a quenching residue quenches the dye by photo-induced electron transfer (PET); with an acceptor dye the transfer of energy (FRET) is simulated too. The result is the donor fluorescence decay, from which the quantum yield and the lifetime follow.

If you have not used it before, press **Guide** for the walk-through.

## What you enter

| Panel | Meaning |
|---|---|
| **Structure** | The structure file and the attachment site (chain, residue, atom) of the donor. |
| **Dye** | Linker length and width and the dye radius: they define the accessible volume. The grid resolution is the voxel size. |
| **Simulation** | Unquenched lifetime, the dye's diffusion coefficient, simulation time and step, the number of photons and the decay bins. |
| **Quenching** | The fallback contact radius; the per-residue chemistry is in the **Quenching Chemistry** tab. |
| **FRET** | Switch on to add an acceptor dye with its own attachment site, linker and diffusion, the Foerster radius and kappa squared. |
| **Advanced** | Parallel trajectories, slowing radius, random seed and output options. |

Every field has a tooltip with the project path it edits.

## Results

**Simulate** runs the project in the background; **Cancel** discards the result of a run (a single trajectory cannot be interrupted). The state line shows the donor quantum yield QY, the mean lifetime and, with FRET, the transfer efficiency E. The plots are the decay, the dye's distance from its mean position over the trajectory and its position autocorrelation. **Project JSON** shows the project as the command line and the web interface read it.

## Limits

QuEst needs the IMP.bff quenching tables; where they are missing the window says so and **Retry** tries again. The Qt tool showed the structure with the ChiMol viewer and let you pick residues in it; this window draws the backbone trace with the attachment sites and takes chain, residue and atom from the form.

## Further reading

[QuEst guide](docs/guides/80_quenching_estimator.md) · [Structure Tools guide](docs/guides/88_structure_tools.md)
