---
type: Reference
title: User Workflows & Use Cases
description: Text descriptions of what a ChiSurf user typically does, discovered and maintained by the headless GUI-tester job.
tags: [usecases, workflows, testing, gui, ux]
timestamp: '2026-07-25T00:00:00Z'
---

# User workflows & use cases

Plain-text descriptions of **what a ChiSurf user actually does**, one workflow per
file, discovered and kept current by the hourly GUI-tester job
(`com.chisurf.gui-tester`, see [scheduled-jobs](/workflows/scheduled-jobs.md)).
Each doc doubles as a **manual test script** (the numbered steps a person or an
agent follows) and a **UX record** (what worked, what confused, what to improve).

The tester drives the real Qt GUI **headlessly** (offscreen), walks a workflow the
way a user would, inspects the result (including screenshots), then writes the
use case here. Concrete, verifiable defects it finds are filed into the
[review findings queue](/reviews/findings.md) (so the fix job acts on them); softer
**UX/UI suggestions** stay here under each workflow.

## Coverage (typical user tasks)

The workflows a first pass should cover — expand as the tester discovers more:

- **Burst analysis** — single-molecule burst selection, BVA, burst MLE, FRET.
- **TCSPC fitting** — load a decay, pick a lifetime/FRET model, set the fit range,
  fit, read χ²ᵣ and parameters.
- **FCS** — correlate, fit diffusion/volume, filtered-FCS.
- **Correlation / TTTR tools** — channel definition, correlator, microtime
  histograms, LUT calibration.
- **Imaging / CLSM** — image representations, pixel selection, phasor, pixel-wise MLE.
- **Calculators & wizards** — FRET lines, kappa², anisotropy, the guided wizards.
- **Structure / modelling** — labelling positions and accessible volumes on a
  PDB structure, FRET distance restraints, docking and screening.

## Recorded workflows

- [TCSPC lifetime fit](/usecases/tcspc-lifetime-fit.md) — load a decay and its
  prompt, create a `Lifetime` fit, assign the IRF, fit, read χ²ᵣ and the
  lifetimes. *(last driven 2026-07-25; RF-012..RF-017)*
- [FCS diffusion fit](/usecases/fcs-diffusion-fit.md) — load a `.cor`
  correlation curve, create a `Parse-Model` fit, pick the 3D-Gauss equation,
  restrict the lag range, fit, read `N`, `t_d` and χ²ᵣ.
  *(last driven 2026-07-25; RF-018..RF-025)*
- [CLSM image and pixel-selected decay](/usecases/clsm-image-decay.md) — load a
  CLSM `.ptu`, auto-detect the scan markers, build a CLSM image and an intensity
  representation, brush a pixel selection, read its decay, save it as an ROI and
  export it to ChiSurf. *(last driven 2026-07-25; RF-030..RF-035)*
- [Burst selection and FRET histogram](/usecases/burst-selection-fret.md) — load
  raw single-molecule TTTR files into the integrated Burst Analysis workflow,
  pick a detector setup, find and filter bursts, read the proximity-ratio
  histogram, then carry the burst folder into BVA, 2CDE, burst-MLE and the
  Burst Browser. *(last driven 2026-07-25; RF-052..RF-056)*
- [TTTR micro-time histogram](/usecases/tttr-microtime-histogram.md) — turn a raw
  photon stream into a fittable decay: pick a detector setup and colour, drop the
  TTTR file, build the polarization-resolved micro-time histogram, read its width,
  save the stacked VV/VH curve and push it into ChiSurf. The step before every
  TCSPC fit. *(last driven 2026-07-26; RF-090..RF-097)*
- [FCS correlation from raw TTTR](/usecases/fcs-correlate-tttr.md) — the step
  before the FCS fit: define correlation channels, drop TTTR files, multi-tau
  correlate in chunks, inspect and merge the chunks, save the `.cor` and push it
  into ChiSurf. *(last driven 2026-07-26; RF-107..RF-112)*
- [Anisotropy wizard](/usecases/anisotropy-wizard-global-fit.md) — the guided
  wizards: open the Wizards hub, walk the Anisotropy wizard (polarised IRF/decay
  files, IRF background region, g-factor and l1/l2, lifetime and rotation
  spectra) and let it build the VV, VH and global fits with all shared
  parameters linked. *(last driven 2026-07-26; RF-126..RF-130)*
- [FLIM pixel maps and pixel-wise MLE](/usecases/flim-pixel-maps-mle.md) — the
  numbered Image Tools pipeline on a confocal FLIM measurement: detector setup,
  browse, intensity, number & brightness, mean micro-time, IRF & background,
  phasor, then the pixel-wise MLE lifetime map.
  *(last driven 2026-07-26; RF-155..RF-162)*
- [Decay Analysis hub — MaxEnt lifetime distribution](/usecases/decay-analysis-maxent.md)
  — the model-free counterpart to a discrete lifetime fit: fit a decay, then let
  the MaxEnt MEM panel read decay, IRF and range from that fit and return a
  lifetime distribution; plus the hub's IRF-estimation and VV/VH G-factor
  calibration panels. *(last driven 2026-07-26; RF-169..RF-173)*
- [filtered-FCS filter calculator](/usecases/ffcs-filter-calculator.md) — the
  species-selective half of FCS: open the FCS window's *Filter Calc* tool,
  auto-fit the mixed decay into lifetime components, compute the per-species
  lifetime filters, unmix the mixture and export the filters for a filtered
  correlation. *(last driven 2026-07-26; RF-190..RF-192)*
- [PCH molecular brightness](/usecases/pch-molecular-brightness.md) — what FCS
  cannot answer: bin the photon stream into short counting intervals, build the
  photon counting histogram P(k), and fit it for molecular brightness ε and mean
  occupancy ⟨N⟩. *(last driven 2026-07-26; RF-208..RF-214)*
- [PDA distance fit](/usecases/pda-distance-fit.md) — the step after burst
  selection: drop the `.bur` burst tables into the PDA experiment, let the reader
  rebuild the S1S2 photon-count histograms per time window, and fit a
  shot-noise-exact donor–acceptor distance instead of a histogram width.
  *(last driven 2026-07-26; RF-263..RF-268)*
- [FRET calculators](/usecases/fret-calculators.md) — open the Calculators hub,
  convert a measured efficiency into a donor–acceptor distance, bound the κ²
  orientation error, and generate a static FRET line to overlay on an smFRET
  histogram. The one core workflow that needs no data file.
  *(last driven 2026-07-25; RF-070..RF-077)*
- [Global analysis — two fits, one shared donor spectrum](/usecases/global-analysis-linked-fits.md)
  — the feature ChiSurf is named for: fit a donor-only and a donor–acceptor
  decay side by side, link the donor lifetime spectrum across the two fits in
  the Global View graph, and run one global fit over both datasets.
  *(last driven 2026-07-26; RF-278..RF-285)*
- [Light Path Simulator](/usecases/lightpath-crosstalk-r0.md) — the step before
  the measurement: assemble a two-colour detection path from catalogue spectra
  (lasers, excitation dichroic, emission splitter, bandpasses, detector QE) and a
  dye pair, and read the Förster radii and the excitation / emission / detected
  crosstalk matrices that prime the accurate-FRET correction factors.
  *(last driven 2026-07-26; RF-269..RF-277)*

- [FPS JSON Editor — labelling positions and distance restraints](/usecases/fps-labelling-positions.md)
  — the structure side of FRET: put dyes on a PDB structure (chain, residue,
  attachment atom, linker geometry), simulate each dye's accessible volume, pair
  the sites into distance restraints with R₀ and asymmetric errors, group them
  into scoring sets and save the `fps.json` that drives FRET docking and
  screening. *(last driven 2026-07-27; RF-379..RF-385)*
- [2D-FLCS lifetime exchange](/usecases/flc-2d-lifetime-exchange.md) — what a
  lifetime fit and an FCS curve cannot answer apart: build the 2D
  fluorescence-decay correlation of a photon stream at a macro-time lag, invert
  it into a lifetime–lifetime distribution, and correlate the resolved species
  against each other for the interconversion rates — validated against the
  plugin's own two-state simulator. *(last driven 2026-07-27; RF-396..RF-407)*
- [Particle tracking — from spots to a diffusion coefficient](/usecases/particle-tracking-diffusion.md)
  — the imaging counterpart of an FCS measurement: detect diffraction-limited
  particles in every frame, link them into trajectories by exact global
  assignment, and fit D (and optionally the anomalous exponent) from the
  ensemble MSD — checked against the tool's own ground-truth simulator, a real
  TIFF stack and a photon stream. *(last driven 2026-07-27; RF-418..RF-421)*
- [DEER/PELDOR distance distribution](/usecases/deer-distance-distribution.md) —
  the EPR counterpart of a FRET distance and a first-class experiment of its own:
  load a Bruker BES3T or CSV dipolar trace, pick a Gaussian, Rice, Tikhonov or
  MaxEnt model, fit the dipolar evolution and read `P(r)` with its bootstrap
  band and the L-curve behind the chosen regularisation.
  *(last driven 2026-07-27; RF-432..RF-436)*

- [PSF determination from a bead scan](/usecases/psf-bead-scan.md) — the
  instrument calibration behind every image and every FCS volume: load a bead
  z-stack, set pixel size and z step, detect the beads, fit a 3-D Gaussian and
  read the lateral/axial FWHM and the axial ratio, then export the per-bead
  table. *(last driven 2026-07-27; RF-451..RF-456)*
- [ndXplorer — gating a multiparameter burst space](/usecases/ndx-mfd-burst-gating.md)
  — what a burst search is *for*: load a Paris burstwise MFD folder, plot any
  burst parameter against any other, cut out a sub-population with a 1-D range
  gate or a painted 2-D bitmap, and carry it out as Burst IDs or into an
  FCS / TCSPC / PDA / PCH analysis.
  *(last driven 2026-07-27; RF-470..RF-475)*

## Per-workflow file format

`okf/usecases/<workflow-slug>.md`, one `##` step-list plus observations:

```
---
type: Reference
title: Use case — <workflow>
tags: [usecase, <area>]
---
# Use case: <workflow>
**Goal:** what the user is trying to achieve.
**Data:** the sample data / example used (repo path).
## Steps
1. … (each concrete UI action, in order)
## Expected
- what a correct run produces.
## Observed (last run: <date>)
- what actually happened; screenshots noted.
## UX / UI suggestions
- concrete, actionable improvements (not filed as bugs).
## Bugs filed
- RF-NNN … (cross-ref into /reviews/findings.md)
```
