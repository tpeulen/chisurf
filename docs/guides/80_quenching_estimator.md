---
type: Guide
title: 'QuEst: predicting dye quenching at a labelling site'
description: Simulating the PET-quenched donor decay of a dye tethered to a protein with QuEst (accessible volume, Brownian dynamics, photon Monte-Carlo), choosing its settings, reading the quantum yield and decay, the headless CLI, and the current state of the plugin, which does not run against the installed IMP.bff.
tags: [guides, structure, photophysics, fret, simulation]
---

# QuEst: predicting dye quenching at a labelling site

Will a dye at this residue be quenched by the protein, and by which residues?
QuEst (*Quenching Estimator*) predicts it from the structure. It computes the
dye's accessible volume, lets the dye diffuse inside it, quenches it whenever
it touches a tryptophan, tyrosine, methionine, histidine, proline or cysteine,
and turns the trajectory into a donor decay and a quantum yield. With an
acceptor placed, it also returns the FRET decay. The question it answers well
is comparative: which of several candidate sites is least quenched.

For the physics (PET at contact, why the dye's motion matters, the rate table),
see {ref}`concept-dye-quenching`.

```{warning}
**QuEst does not currently run in ChiSurf.** The `quest` package imports
`IMP.bff.quenching`, a Python module that IMP.bff removed when its quenching
model moved to C++. The tool therefore fails before its window is built, and
so do `quest template` and `quest simulate`. The settings and outputs below are
documented from the QuEst code and its parameter catalogue. No simulation
result is shown, because none could be computed. See
[Known defects](#known-defects).
```

## Open the tool

**Structure → Structure Tools**, then **💡 QuEst** in the left list. It has no
ribbon button of its own. In the current state the panel shows the import
error instead of the form:

```{figure} figures/quest_structure_tools.png
:name: fig-quest-structure-tools
:width: 100%

Structure Tools with QuEst selected. The panel reports
`No module named 'IMP.bff.quenching'`: the QuEst form cannot be built against
the installed IMP.bff. The other entries, including HydroPro, are unaffected.
```

When it works, the panel is QuEst's own form, with a **Load PDB…** action on
the toolbar and **Run Simulation** in the form.

## Set it up

All lengths are in Å and all times in ns. The defaults are those of
`quest template`.

**Structure**

1. **Structure file**: a PDB or mmCIF file, or a four-character RCSB ID,
   which is downloaded. Remove crystal waters first, because they block the
   accessible volume and hide quenchers. QuEst's demonstration project uses
   T4 lysozyme, 148L.
2. **Attachment chain / residue / atom**: where the linker starts, usually the
   C$_\beta$ of the labelled residue (for 148L, chain `E`; the demo uses
   residue 118).

**Dye** (the accessible volume, {ref}`concept-accessible-volume`)

3. **Linker length** (21.5), **linker width** (0.5) and **dye radius** (3.5):
   the single-sphere AV of the dye centre.
4. **Grid resolution** $d_g$ (0.5): the AV grid, which is also the grid the dye
   walks on. A coarser grid is faster and moves the contact boundaries.

**Simulation**

5. **Unquenched lifetime** $\tau_0$ (4.2 ns): the dye's lifetime with no
   quencher in reach.
6. **Donor diffusion coefficient** $D$ (7.5 Å²/ns): the tethered dye's
   diffusion coefficient away from the surface. It is smaller than a free
   dye's, which is about 36 Å²/ns ({ref}`concept-hydrodynamics`).
7. **Simulation time** $t_\text{max}$ (16 000 ns) and **time step**
   $\Delta t$ (0.032 ns): the length and resolution of the Brownian trajectory.
   The trajectory must be long enough for the dye to visit its whole volume
   many times, and the step short enough to resolve a contact.
8. **Simulated photons** (500 000) and **decay bins** (4096): the photon
   Monte-Carlo and the decay histogram.
9. **Coarse-grained structure**: reduces the protein to backbone plus one
   pseudo-atom per side chain. The AV then grows and every quenching centre
   moves to that pseudo-atom. It is a different model, not a faster one.

**Quenching** (the rate table, {ref}`concept-dye-quenching`)

10. The table has one row per residue type: **kQ** (1/ns, applied while in
    contact), **radius** (Å from the dye centre to the quenching centre),
    **atoms** (whose centroid is the quenching centre) and **slow factor**
    (0–1, how much the residue slows the dye). The template uses a slow factor
    of 0.1. Overlapping contacts add their rates, and overlapping slow factors
    multiply.
11. **Fallback contact radius** (8.5): used by a residue type whose own radius
    is empty. It must be larger than the dye radius plus van der Waals
    contact.

**FRET** (optional)

12. **FRET enabled**, the acceptor's attachment and AV, its diffusion
    coefficient and slowing radius, the **Förster radius** $R_0$ **in Å** (a
    value in nm makes FRET vanish), and **κ²** (2/3 by default, which is what
    a published $R_0$ already assumes).
13. **Acceptor dynamics**: *trajectory* walks the acceptor too and uses the
    instantaneous distance; *averaged* averages over its static AV, which is
    valid only if the acceptor explores its volume fast compared with the
    donor lifetime.

**Advanced**

14. **Slowing radius** (8.5): the radius around each residue within which its
    slow factor applies. **Parallel trajectories** (−1 = all cores, at most 8)
    are combined before the photons are drawn. **Random seed** makes the
    trajectory and the photons reproducible. **Save AV files**, **output file
    prefix** and **trajectory skip frames** control what is written to disk.

## Read the result

A run returns:

- the **donor decay** (and the FRET decay with an acceptor), on the time axis
  of the histogram;
- the **donor quantum yield** relative to the unquenched dye (1 without
  quenchers) and the mean lifetime;
- the **per-residue-type breakdown**: how much of the total quenching rate each
  residue type contributed, and how often and how long the dye was in contact
  with it;
- the AV and contact volumes, the trajectory and its autocorrelation.

A quantum yield well below 1 with most of the rate from one residue type points
to a specific quencher near the site. Moving the label, or mutating that
residue, is the design decision the number supports.

## Where the results go next

- The predicted donor quantum yield changes the Förster radius,
  $R_0 \propto Q_D^{1/6}$ ({ref}`concept-fret`).
- The predicted decay is a reference for a measured donor-only decay
  ({doc}`10_lifetime_anisotropy_fitting` fits the measured one).
- `quest scan` runs the same simulation for a list of labelling sites in the
  `fps.json` format of the FPS JSON editor ({doc}`23_accessible_volume`).

## Headless

The plugin's CLI is QuEst's own, under `csc quest`. The intended workflow:

```bash
csc quest template --with-fret > project.quest.json
csc quest simulate -p project.quest.json --pdb test/data/atomic_coordinates/pdb_files/148l.pdb \
    --set attachment.chain=E --set attachment.residue=118 -o decay.csv
csc quest scan ...        # several sites
```

and the same from Python through `quest.api.simulate(project)`. Over RPC the
methods are `quest.template`, `quest.validate`, `quest.simulate` and
`quest.scan`.

Run in the arm64 environment, the first command already fails:

```text
$ csc quest template
  File ".../quest/core/dye_diffusion.py", line 47, in _pet
    from IMP.bff.quenching import pet
ModuleNotFoundError: No module named 'IMP.bff.quenching'
```

## Using it well

**Compare sites, and calibrate before trusting absolute numbers.** The rate
table is for a xanthene dye of the Alexa488 type and is a starting point. Fit a
common scale on kQ against measured donor lifetimes at several sites at once.
One site cannot separate the kQ scale from the stickiness.

**Converge the trajectory.** Two runs with different seeds should give the same
quantum yield to the precision you intend to quote. If they do not, lengthen
$t_\text{max}$.

**Use the structure you labelled.** A missing side chain removes a quencher,
and a crystal water blocks part of the AV.

**Static quenching is not in the model.** Dark complexes formed before
excitation lower the brightness without changing the simulated decay.

## Known defects

- **QuEst does not import against the installed IMP.bff.** `quest` imports
  `IMP.bff.quenching` (in `quest/core/dye_diffusion.py`, `quest/core/photon.py`
  and `quest/core/av.py`), as well as `IMP.bff.av.compute`,
  `IMP.bff.av._kernels` and `IMP.bff.distance_metrics`. The IMP.bff checkout
  on `dev` removed these Python modules when its quenching model moved to C++
  (commit "the PET quenching model to C++"). The same functions are now
  top-level in `IMP.bff` (`amino_acid_quenching_defaults`,
  `simulate_photon_trace`, `simulate_quenched_decay`, `QuenchedDonorDecay`, …).
  As a result the tool, `quest template` and `quest simulate` all fail, and 3
  of the 14 plugin tests fail for this reason.
- **Two import-hygiene tests fail under the documented `PYTHONPATH`.**
  `modules/imp-tricks/src/sitecustomize.py` imports IMP when the interpreter
  starts, so the plugin's "does not import IMP at startup" checks see IMP
  modules that the plugin did not load.

## See also

- Concept: {ref}`concept-dye-quenching`. Related: {ref}`concept-accessible-volume`,
  {ref}`concept-fret`, {ref}`concept-hydrodynamics`,
  {ref}`fundamentals-quenching-mechanisms`.
- Tool: **QuEst** (`chisurf/plugins/quenching_estimator/`, a shell around
  `modules/quest`), reached through **Structure Tools**.
- Method: {cite}`peulen2017`.
