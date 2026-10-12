# QuEst: quenching and FRET of a tethered dye

QuEst (Peulen, Opanasyuk and Seidel, [10.1021/acs.jpcb.7b03441](https://doi.org/10.1021/acs.jpcb.7b03441)) simulates a dye on a flexible linker diffusing over a protein. Contact with a quenching residue (Trp, Tyr, His, Met, Pro, Cys) quenches the dye by photo-induced electron transfer (PET); with an acceptor dye the transfer of energy (FRET) is simulated too. The result is the donor fluorescence decay, from which the quantum yield and the lifetime follow.

If you have not used it before, press **Guide**; **Load demo** gives it T4 lysozyme (PDB 148L) to work on.

## What you enter

| Panel | Meaning |
|---|---|
| **Structure** | The structure file and the attachment site (chain, residue, atom) of the donor. |
| **Dye** | Linker length and width and the dye radius: they define the accessible volume. The grid resolution is the voxel size. |
| **Simulation** | Unquenched lifetime, the dye's diffusion coefficient, simulation time and step, the number of photons and the decay bins. |
| **Quenching** | The fallback contact radius; the per-residue chemistry is in the **Quenching Chemistry** tab. |
| **FRET** | Switch on to add an acceptor dye with its own attachment site, linker and diffusion, the Förster radius and κ². |
| **Advanced** | Parallel trajectories, slowing radius, random seed and output options. |

Every field has a tooltip with the project path it edits.

## Results

**Simulate** runs the project in the background; **Cancel** discards the result of a run (a single trajectory cannot be interrupted). The state line shows the donor quantum yield QY (1 means no quenching), the mean lifetime and, with FRET, the transfer efficiency E. The plots are the decay, the dye's distance from its mean position over the trajectory and its position autocorrelation. **Project JSON** shows the project as the command line (`quest`) and the RPC methods read it.

## Limits

- **Quenching is a step in distance.** A quencher inside its contact radius quenches at its full rate, one outside not at all; the rates are a reference table, not a fit to your data.
- **The accessible volume defines the answer.** The defaults are IMP.bff's (linker 20 Å, width 4.5 Å, dye radius 3.5 Å, grid 0.9 Å). At that width a third of the Cβ sites of T4 lysozyme have **no** accessible volume and the run stops with "Accessible Volume is empty"; a narrower linker width (for example 0.5 Å) labels every site.
- **A prediction, not a measurement.** Compare with a measured donor-only lifetime; a mismatch is evidence about the structure or the linker.

## Further reading

- [QuEst — the workflow](docs/guides/80_quenching_estimator.md) — every setting, the outputs, the command line and the Python API.
- [Dye quenching by amino acids](docs/concepts/dye_quenching.md) — the contact model, the rate table and what quenching does to lifetimes, FCS and FRET.
- [Structure Tools](docs/guides/88_structure_tools.md) — the hub this window is also a card of.
