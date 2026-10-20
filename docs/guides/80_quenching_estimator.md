---
type: Guide
title: 'QuEst: predicting dye quenching at a labelling site'
description: Simulating the PET-quenched donor decay of a dye tethered to a protein with QuEst (accessible volume, three ensembles: Brownian walk, equilibrium, diffusion PDE; photon Monte-Carlo), choosing its settings, reading the quantum yield and decay, the built-in T4 lysozyme demo, the headless CLI and the Python API.
tags: [guides, fret, tcspc, decay, dynamics, photons, settings, headless]
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

QuEst is part of ChiSurf: the engine is the `quenching_estimator` plugin
(`chisurf/plugins/quenching_estimator/core/`), built on IMP.bff's accessible
volume, Brownian walk and photon kernels. It used to be a separate package
(`quest`), which ChiSurf no longer needs.

## Open the tool

**Structure → Computation → QuEst** (💧), or from the command line (`csg_quest`, or
`csc quest gui`). Both are the same window. Press **Guide** for a walk-through and **Load example** to start from the
shipped example: T4 lysozyme (PDB 148L), the dye on the C$_\beta$ of Ser 36,
FRET off, a short seeded run. **Simulate** then ends in a few seconds:

```{figure} figures/quest_demo_result.png
:name: fig-quest-structure-tools
:width: 100%

The QuEst window after **Load example** and **Simulate** (800 × 600): T4 lysozyme (148L), dye on E36 C$_\beta$ at the
default accessible volume, *walk* ensemble. The State line reads QY = 0.766 and ⟨τ⟩ = 3.90 ns; the panels are the donor
decay, the dye's distance from its mean position along the first walker (84 ns) and its position autocorrelation.
```

## Set it up

All lengths are in Å and all times in ns. The defaults are those of
`quest template`; the accessible-volume defaults are IMP.bff's (`IMP.bff.AV_DEFAULT_*`),
the same ones every AV in ChiSurf uses.

**Structure**

1. **Structure file**: a PDB or mmCIF file, or a four-character RCSB ID,
   which is downloaded. Remove crystal waters first, because they block the
   accessible volume and hide quenchers. **Load example** uses T4 lysozyme, 148L,
   which ships with the plugin (`examples/148l.pdb`).
2. **Attachment chain / residue / atom**: where the linker starts, usually the
   C$_\beta$ of the labelled residue (for 148L, chain `E`; the demo uses
   residue 36). After **Load PDB…** a valid site is picked for you.

**Dye** (the accessible volume, {ref}`concept-accessible-volume`)

3. **Linker length** (20), **linker width** (4.5) and **dye radius** (3.5):
   the single-sphere AV of the dye centre. At the default width a third of the
   C$_\beta$ sites of 148L have **no** accessible volume and the run stops
   with *Accessible Volume is empty*; a narrower width (0.5) labels every site
   (see [Known defects](#known-defects)).
4. **Grid resolution** $d_g$ (0.9): the AV grid, which is also the grid the dye
   walks on. A coarser grid is faster and moves the contact boundaries.

**Simulation**

5. **Unquenched lifetime** $\tau_0$ (4.2 ns): the dye's lifetime with no
   quencher in reach.
6. **Donor diffusion coefficient** $D$ (7.5 Å²/ns): the tethered dye's
   diffusion coefficient away from the surface. It is smaller than a free
   dye's, which is about 36 Å²/ns ({ref}`concept-hydrodynamics`).
7. **Ensemble** (*walk*): where the dye sits during the excited state. All
   three solve one diffusion problem, with the mobility $m(x) = \prod s$ of the
   residues in range and the equilibrium occupancy $w(x) = 1/m(x)$
   ({ref}`concept-quenching-inference`, "three ensembles"):
   - *walk*: Brownian walkers, each started from $w$, and a photon race along
     each. The only ensemble that simulates FRET; Monte-Carlo noise plus a
     small time-step bias at sticky boundaries.
   - *equilibrium*: the static limit. Every position decays on its own at
     $1/\tau_0 + k_Q$, weighted by $w$. Exact, fast, and what the inverse fit
     uses.
   - *pde*: the diffusion equation on the AV grid with the stickiness as a
     potential and quenching as a sink (IMP.bff's grid solver). Motion during the
     excited state, no sampling noise; its stationary state is the equilibrium
     ensemble.

   MalE APO site 95 with the AF488 table at slow factor 0.3: equilibrium
   $\tau_x$ 2.872 ns, PDE 2.494 ns (fast-exchange limit 1.057 ns). The
   walk agrees with the PDE; the equilibrium value is longer because it leaves
   out transport into contact during the excited state.
8. **Simulation time** $t_\text{max}$ (16 000 ns) and **time step**
   $\Delta t$ (0.032 ns), *walk* only: the walk covers *parallel trajectories*
   × $t_\text{max}$, cut into about 1000 walkers of 20–50 $\tau_0$. Every walker starts at
   equilibrium, so a longer run lowers the noise rather than removing a bias;
   a smaller step shrinks the bias at sticky boundaries.
9. **Simulated photons** (500 000) and **decay bins** (4096): the photon
   Monte-Carlo and the decay histogram.
10. **Coarse-grained structure**: reduces the protein to backbone plus one
   pseudo-atom per side chain. The AV then grows and every quenching centre
   moves to that pseudo-atom. It is a different model, not a faster one.

**Quenching** (the rate table, {ref}`concept-dye-quenching`)

11. The table has one row per residue type: **kQ** (1/ns, applied while in
    contact), **radius** (Å from the dye centre to the quenching centre),
    **atoms** (whose centroid is the quenching centre) and **slow factor**
    (0–1, how much the residue slows the dye). The template uses a slow factor
    of 0.1. Overlapping contacts add their rates, and overlapping slow factors
    multiply.
12. **Fallback contact radius** (8.5): used by a residue type whose own radius
    is empty. It must be larger than the dye radius plus van der Waals
    contact.

**FRET** (optional)

13. **FRET enabled**, the acceptor's attachment and AV, its diffusion
    coefficient and slowing radius, the **Förster radius** $R_0$ **in Å** (a
    value in nm makes FRET vanish), and **κ²** (2/3 by default, which is what
    a published $R_0$ already assumes).
14. **Acceptor dynamics**: *trajectory* walks the acceptor too and uses the
    instantaneous distance; *averaged* averages over its static AV, which is
    valid only if the acceptor explores its volume fast compared with the
    donor lifetime.

**Advanced**

15. **Slowing radius** (8.5): the radius around each residue within which its
    slow factor applies. **Parallel trajectories** (−1 = the number of cores, at
    most 8) is the number of $t_\text{max}$ blocks the walk covers. **Random seed** makes the
    trajectory and the photons reproducible. **Save AV files**, **output file
    prefix** and **trajectory skip frames** control what is written to disk.

## Read the result

A run returns:

- the **donor decay** (and the FRET decay with an acceptor), on the time axis
  of the histogram;
- the **donor quantum yield** relative to the unquenched dye (1 without
  quenchers), the species-averaged lifetime $\tau_x$ = QY × $\tau_0$ and the
  mean photon arrival time. For *equilibrium* and *pde* the result also carries
  the exact $\tau_x$, $\tau_F$ and the static and fast-exchange limits
  (`ensemble_lifetimes`);
- the **per-residue-type breakdown**: how much of the total quenching rate each
  residue type contributed, and how often and how long the dye was in contact
  with it;
- the AV and contact volumes, the trajectory and its autocorrelation (the walk's
  first walker). For *equilibrium* and *pde* there is no trajectory, and the
  residue breakdown is read off a sample of the equilibrium occupancy without
  dwell times.

`quest scan` names a site's dominant quencher only when the site loses at least
1 % of its light (QY ≤ 0.99); the full quencher list is always reported.

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

The plugin's CLI is `csc quest` (`template`, `validate`, `simulate`, `scan`,
`runs`, `gui`). The demo, from a shell:

```bash
csc quest template > project.quest.json
csc quest simulate -p project.quest.json \
    --pdb chisurf/plugins/quenching_estimator/examples/148l.pdb \
    --set attachment.chain=E --set attachment.residue=36 --set fret.enabled=false \
    --set t_max=2000 --set n_photons=200000 --set random_seed=7 -o decay.csv
csc quest scan ...        # several sites, fps.json positions
```

`decay.csv` holds the decay and the scalar results; for this run
`quantum_yield_donor` is 0.766, the same number the window shows. With
`--set ensemble=pde` it is 0.761 (exact $\tau_x$ 3.19 ns), with
`--set ensemble=equilibrium` 0.759: at this site the dye barely moves at slow
factor 0.1, so the three agree. From Python:

```python
from chisurf.plugins.quenching_estimator.api import local as quest

project = quest.template(with_fret=False)
project["pdb"] = "chisurf/plugins/quenching_estimator/examples/148l.pdb"
project["attachment"] = {"chain": "E", "residue": 36, "atom": "CB"}
result = quest.simulate(project)          # a DecaySimulationResult
print(result.quantum_yield_donor, result.lifetime_donor)

project["ensemble"] = "pde"               # or "equilibrium"; FRET needs "walk"
print(quest.simulate(project).ensemble_lifetimes)
```

Over RPC (ChiSurf's server registers the plugin's services) the methods are
`quest.template`, `quest.validate`, `quest.simulate`, `quest.scan` and the rest
of the table in the plugin's `manifest.json`.

## Using it well

**Compare sites, and calibrate before trusting absolute numbers.** The rate
table is for a xanthene dye of the Alexa488 type and is a starting point. Fit a
common scale on kQ against measured donor lifetimes at several sites at once.
One site cannot separate the kQ scale from the stickiness.

**Check the noise, and the ensemble.** With *walk*, two runs with different seeds
should give the same quantum yield to the precision you intend to quote; if
they do not, lengthen $t_\text{max}$. *pde* gives the same physics without the
noise, so it is the reference for a donor-only question.

**Use the structure you labelled.** A missing side chain removes a quencher,
and a crystal water blocks part of the AV.

**Static quenching is not in the model.** Dark complexes formed before
excitation lower the brightness without changing the simulated decay.

## Known defects

- **A third of T4 lysozyme's sites have no accessible volume at the default
  linker width.** With IMP.bff's defaults (width 4.5 Å, grid 0.9 Å) 48 of the
  151 C$_\beta$ sites of 148L chain E come back empty (among them 96, 99, 117,
  129, 132, 139). The linker search is FPS's own (hops of three voxels from
  every node); what walls these sites in is the radii: QuEst inflates atoms by
  IMP's united-atom radii (carbon up to 2.275 Å), and with FPS's smaller Bondi
  radii the same search leaves exactly FPS's 33 empty, 96, 117 and 132 among the
  labelled. A width of 0.5 Å labels all 151.
- **FRET needs the walk.** *equilibrium* and *pde* refuse a project with FRET
  enabled, because the transfer rate is read along the dyes' paths.

## See also

- Concept: {ref}`concept-dye-quenching`. Related: {ref}`concept-accessible-volume`,
  {ref}`concept-fret`, {ref}`concept-hydrodynamics`,
  {ref}`fundamentals-quenching-mechanisms`.
- Tool: **QuEst** (`chisurf/plugins/quenching_estimator/`), on the ribbon at
  **Structure → Computation**.
- Method: {cite}`peulen2017`.
