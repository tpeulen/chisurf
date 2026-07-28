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
- [F-test — is the second lifetime justified?](/usecases/ftest-model-comparison.md)
  — the question every lifetime fit raises: fit one decay with one and then two
  exponentials, pull both fits into the *F-test / χ²-max* calculator from its own
  *From fit* menu, and read the confidence that the extra component is warranted
  plus the χ² ceiling behind the accepted fit's error bars.
  *(last driven 2026-07-27; RF-493..RF-495)*
- [Burst-wise FCS](/usecases/burst-wise-fcs.md) — one more observable per burst:
  define the FCS channel pairs for a detector setup, correlate every burst of a
  burst-analysis folder on its own, fit each curve for a diffusion time and
  browse the per-burst correlations. Fast and correct in the middle, unusable at
  both ends — the pairs cannot be created in it and the τ_D values cannot leave
  it. *(last driven 2026-07-27; RF-509..RF-516)*
- [Photon-by-photon kinetics (Gopich–Szabo)](/usecases/photon-by-photon-kinetics.md)
  — the continuous-time sibling of H2MM: fit rate constants and per-state FRET
  efficiencies directly to the arrival time and colour of every burst photon,
  learn the method on the built-in simulator, then run it on a real burst
  folder, with a transition-time scan and an independent H2MM cross-check. The
  likelihood is right and fast; getting real data into it is not.
  *(last driven 2026-07-27; RF-524..RF-531)*
- [Inter-frame drift correction](/usecases/image-drift-correction.md) — the step
  before every per-pixel map: measure how far the sample moved between frames,
  remove it (whole-pixel rolls for a camera stack, photon-by-photon for a
  confocal stream), read the drift trace and the before/after projections, and
  export the corrected stack and the shift table. The estimator is right; the
  window around it shows the previous file's result after a file it cannot read.
  *(last driven 2026-07-28; RF-554..RF-562)*
- [Molecule-wise MLE](/usecases/molecule-wise-lifetime-mle.md) — a lifetime per
  *object* rather than per region or per pixel: segment a confocal TTTR image
  into discrete emitters, pool each one's photons into a VV/VH micro-time
  histogram, fit every molecule by single-lifetime Poisson MLE (Fit23), and
  browse the per-molecule decays before exporting the table. Right and quick in
  the middle; the measured outlines never reach the canvas and the shipped fit
  window turns a handful of photons into a confident lifetime.
  *(last driven 2026-07-28; RF-576..RF-579)*
- [TTTR file preparation](/usecases/tttr-file-preparation.md) — everything a user
  does to a raw photon file before an analysis window is opened, in one window:
  read and correct the file header, split a long acquisition into chunks and
  convert the container, check the count rate per detector across a whole folder,
  and apply the stream-level corrections (micro-time shift, ALEX→micro-time).
  Fast and photon-exact where it works; a header edit quietly breaks a scan file
  and the count rates are reported without a plausibility check.
  *(last driven 2026-07-28; RF-596..RF-603)*
- [Save, version, export and restore a project](/usecases/project-save-restore.md)
  — the workflow around every other one: store a whole session as a versioned
  MMFDB project, read the version history, export and re-import the `.csp`, and
  reopen it in a fresh ChiSurf. Saving, versioning, dedup, export and the
  housekeeping controls are solid; the restore hands back the storage schema, so
  the session comes back with empty datasets and no fits — and one *Save* click
  writes two versions. *(last driven 2026-07-28; RF-616..RF-620)*
- [Simulate a TCSPC decay and recover its lifetimes](/usecases/tcspc-simulate-and-recover.md)
  — the validation loop before trusting any lifetime fit: type a known
  bi-exponential spectrum into the `Simulator` file type, convolve it with a
  measured prompt, add it to the session and fit it back. The round trip is
  exact (0.75/4.0 ns and 0.25/1.0 ns returned at χ²ᵣ = 1.00), but the panel's
  own **Add** and the header's **+ Data** generate different decays, and the
  **+ Data** one cannot be fitted at all. *(last driven 2026-07-28;
  RF-636..RF-639)*

- [FRC resolution](/usecases/frc-resolution.md) — how fine a detail the
  acquisition actually resolved, measured from the image itself: split a TIFF
  stack or a confocal photon stream into two independent halves, correlate them
  ring by ring, and read the crossing of the 1/7, ½-bit or 2σ threshold. The
  estimator is right and sub-second; the panel around it shows one channel pair
  and correlates another, and calls an empty detector "resolved beyond what this
  sampling can show". *(last driven 2026-07-28; RF-664..RF-669)*

- [FRET observables from an MD trajectory](/usecases/md-trajectory-fret.md) —
  the simulation side of a FRET experiment: drop an MD trajectory into the
  *Traj Tools* FRET tab, pick the two dipole atoms of the donor and of the
  acceptor, and export `RDA(t)`, `κ²(t)` and the FRET-rate constant frame by
  frame. The distances are exact to 0.0000 Å; unticking *Dipole (κ2)* zeroes
  every FRET rate, and the atom pickers come up on one and the same atom, so an
  untouched **Process** writes 464 rows of `nan` and calls it finished.
  *(last driven 2026-07-28; RF-676..RF-681)*

- [QuEst — the decay a structure predicts](/usecases/quest-dye-quenching-decay.md)
  — the structural side of a lifetime: diffuse a tethered dye through its
  accessible volume on a PDB, quench it on contact with the aromatic residues it
  meets, transfer to an acceptor, and read the predicted quantum yield, mean
  lifetime, FRET efficiency and decay — the τ₀ every other TCSPC workflow assumes.
  Fast (7 s at the shipped defaults) and beautifully labelled; the decay plot is
  72 % a spike of photons that were never emitted, **▶ Simulate** leaves the
  previous state on screen, and the predicted decay cannot leave the window.
  *(last driven 2026-07-28; RF-689..RF-695)*

- [Preparing an MD trajectory for FRET analysis](/usecases/trajectory-preparation.md)
  — the seven Traj Tools tabs a user works through *before* the FRET tab:
  export the topology, superpose out the tumbling, drop the clashed frames,
  place the molecule, join the runs, convert the format and check the result
  with a potential. The maths is exact (rotation, translation and superposition
  all verified to 3–4 decimals) but the reporting is not: aligning with the
  **default empty atom selection** writes a 100 %-NaN trajectory and calls it
  saved, a too-large clash distance writes a 0-frame one and calls it saved, and
  Align/Rot-Translate silently replace the time axis with a frame counter that
  ignores the stride. *(last driven 2026-07-28; RF-706..RF-710)*

- [Merging FCS repeats and calibrating the confocal volume](/usecases/fcs-merge-and-calibrate.md)
  — the two steps that bracket the FCS fit: average a folder of repeat
  correlation chunks into one `.cor` with per-point errors, then calibrate *Veff*
  on a reference dye of known *D* and turn the fitted τ_D, S and G(0) of an
  unknown sample into a diffusion coefficient, a hydrodynamic radius and an
  absolute concentration. Every closed-form quantity checks out by hand, but the
  merger shows and writes **every count rate 2000× too small**, its zero error
  values become **infinite fit weights** in the curve it hands to ChiSurf,
  unticking every row merges all of them anyway, and two of its three buttons do
  nothing. *(last driven 2026-07-28; RF-730..RF-738)*

- [Planning a raster scan](/usecases/rics-scan-precision.md) — the workflow that
  happens *before* the microscope time is spent: from the intended scan settings
  and the `D` you expect, predict the relative error on the fitted `D` and sweep
  the pixel dwell time for the one that measures it best. The estimator is fast
  (0.9 s), threaded with a real progress readout, and reproduces the CLI exactly;
  the panel around it reports the frame time **1000× too small**, answers a
  failed prediction with the two words "Prediction failed" while holding the
  exact diagnosis, and calls the last point of a hard-coded 0.5 µs–0.5 ms sweep
  "the best dwell" on curves that never turned around.
  *(last driven 2026-07-28; RF-793..RF-797)*

- [Running a measurement — simulated single-molecule acquisition](/usecases/acquisition-simulated-measurement.md)
  — the workflow *before* every file-based one: configure the sample, optics and
  detection of a confocal single-molecule experiment, run the acquisition
  against the built-in tttrlib photon simulator, watch the live decay,
  correlation, count-rate and MCS readouts, and pick the recorded SPC stream up
  for a burst search or an FCS fit. The simulated physics is sound (the
  correlation amplitude reproduces the configured occupancy exactly and the
  written files read back as valid streams); everything between the settings and
  that stream is not — the recordings ignore the configured folder and land in
  the working directory, a 20 000-photon budget returns 190 671 photons, half
  the detectors never reach the decay window, and that decay is drawn backwards
  on an axis six times too wide. *(last driven 2026-07-28; RF-819..RF-827)*

- [How certain is that lifetime? — posterior sampling](/usecases/mcmc-posterior-sampling.md)
  — the step after every fit: press **Sample** beside **Fit**, sample the
  posterior of the free parameters, and read credible intervals that need no
  Gaussian assumption. The engine is excellent — ten chains over a 4094-channel
  two-exponential fit in 2 s, honest rank-normalised R̂ / bulk-and-tail ESS, a
  self-contained output folder with the project that produced it — and almost
  none of it reaches the user: pressing **OK** in the settings dialog without
  changing anything switches proposal adaptation off for good, the two plots
  that exist to judge a chain cannot be opened from any model, a four-minute run
  shows no progress and can be started twice over itself, and the shipped
  defaults cannot pass the convergence gate, so the chain is discarded and the
  covariance error bar is quoted instead. *(last driven 2026-07-28;
  RF-840..RF-845)*

- [Rates from a binned trace — the hidden Markov model](/usecases/hmm-binned-trace-kinetics.md)
  — the binned-trace counterpart of H2MM and the declared shared HMM seam of
  ChiSurf: drop a trace, let the state scan choose the state count by BIC, fit,
  and read the emissions, dwell times and per-second transition rates. The
  estimator is exact and fast (a 30 000-bin three-state trace returns
  12.02 / 33.91 / 59.98 counts and every rate within 15 % of truth in 0.7 s, and
  the CLI reproduces it digit for digit); the window around it does not connect
  to the rest of the application — the trace is not drawn until a fit runs, a
  file it cannot read is reported as no file at all, the only binned-trace CSV
  ChiSurf itself writes fails to load (and with its header removed its time
  column is fitted as a detection channel), a sub-microsecond bin width collapses
  to 10⁻¹² s and is reported as rates of 10¹⁰ s⁻¹, and the finished fit cannot
  leave the window. *(last driven 2026-07-28; RF-853..RF-862)*

- [Lazy Lifetime Analysis (LLTF)](/usecases/lltf-lazy-lifetime-analysis.md) — the
  one-button TCSPC fit: hand the *Decay Analysis* hub's panel 3 a decay and its
  IRF and let it estimate the analysis range, the background and the IRF shift,
  fit 1…N exponentials and F-test the series for the component count. The engine
  is real and quick (a 1…4 scan in 31 s; an explicit two-exponential fit returns
  χ²ᵣ = 1.54), but almost nothing around it is: **Find Optimal** returns the
  *worst* model it fitted (n = 1 at χ²ᵣ = 9.07 out of scores 7.97 / 3.95 / 12.88
  / 68.78) because the selection loop falls through to its initial index and the
  config's `selection_mode` is overwritten by the CLI default; the IRF shift is
  converted with a hard-coded 2 ns channel width, so 8 ns moves the prompt
  0.032 ns; the only route to the settings aborts the application; and the
  saved plot is a green block. *(last driven 2026-07-28; RF-877..RF-884)*

- [The Converter hub — raw stream → time-window BIDs → analysis folder](/usecases/converter-time-window-bids.md)
  — the burst-search-free route to a `.bur` table, all three steps in one window:
  transcode/split the container, cut the measurement into fixed-duration
  time-window BID (`.bst`) files, and turn those into `bi4_bur/<stem>.bur` plus
  `Info/`. The transcode is bit-exact (183 657 photons, micro-times identical,
  0.02 s) and the `.bst` writer is right, but the two panels disagree about their
  own contract: the BIDs are written half-open (`[start, stop)`) and read closed,
  so every window gains a photon, every boundary photon is counted twice and the
  final window is silently dropped (624 windows → 623 rows) — a *missing* row in
  a format merged column-wise by position; and the total `Count Rate (KHz)` is
  1000× too small next to per-detector kHz columns that are correct. Around that,
  the preview draws one white line per window (6233 at the default, hiding the
  trace and costing 1.8 s a redraw), the ⏭ pipeline-walk runs nothing and reports
  "the pipeline is done", and one unreadable BID aborts the batch with an
  unhandled exception. *(last driven 2026-07-29; RF-896..RF-906)*

- [VV/VH G-factor and l1/l2 detection calibration](/usecases/vv-vh-g-factor-calibration.md)
  — where the `G`, `l1` and `l2` that every anisotropy fit takes as *given*
  actually come from: tail-match a fast-rotating dye against its own VH channel,
  subtract the pre-pulse background, estimate the channel mixing from a
  slow-rotating sample via Perrin, read `r(t)`, and batch a folder. The tail
  match is quick (0.08 s per file) and its overlay makes a good `G` obvious, but
  the l1/l2 half never runs — a transport method with **no `return`** makes every
  FP load raise, and poisons every later click on the window — the shipped
  background region is sampled from the **decay** rather than the baseline (so
  the "corrected" `G` is 1.0048 instead of 1.2866, and 0.2173 instead of 1.7418
  on the water file), the `l1/l2` it does determine never reaches the `r(t)` it
  corrects, and the batch turns an unreadable file and an out-of-range region
  into the same silent `nan`. *(last driven 2026-07-29; RF-918..RF-925)*

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
