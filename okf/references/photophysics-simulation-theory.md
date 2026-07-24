---
type: Reference
title: "Single-molecule photon-simulation theory — diffusing particles to TTTR"
description: The physics behind ChiSurf's forward confocal simulator — Brownian trajectories in a 3-D Gaussian detection profile, position-dependent Poisson emission, FRET channel partitioning, background, detector/micro-time effects, and Markov state kinetics — mapped to tttrlib.SimEngine and the chisurf wrappers, so a simulated stream correlates/bursts/H2MM-fits exactly like real data. Prior art: PyBroMo and QuickFit3's FCS simulator.
resource: chisurf/core/fluorescence/fcs/simulate.py
tags: [reference, simulation, diffusion, fcs, burst, fret, h2mm, tttr, pedagogy]
timestamp: '2026-07-24T00:00:00Z'
---

# Single-molecule photon-simulation theory — diffusing particles to TTTR

This concept is the **science/pedagogy layer** behind ChiSurf's forward
single-molecule simulator: what physical factors compose a realistic confocal
photon stream, how they map to the fitted forward models, and where each lives in
code. It is the counterpart, for the *forward/generative* direction, of the
inverse-model references [fcs-model-theory.md](fcs-model-theory.md),
[fret-theory.md](fret-theory.md), and [h2mm-theory.md](h2mm-theory.md). The
user-facing version is `docs/concepts/photophysics_simulation.md`
(`concept-photophysics-simulation`); this note carries the code map and the
provenance the user page omits.

The engine is `tttrlib.SimEngine`. ChiSurf wraps it in two seams:
`chisurf/core/fluorescence/fcs/simulate.py` (`simulate_lifetime_fcs`, for
lifetime-FCS/FLCS validation) and the burst-workflow `simulate()` in
`chisurf/plugins/burst/burst_analysis/api/workflow.py` (two-colour smFRET → MMFDB
measurement). The interactive GUI is the `fcs_lfcs_sim` plugin. The tutorials are
`docs/guides/18_tttr_simulation.md` and
`docs/guides/31_h2mm_simulation_validation.md`.

## Documented prior art

The exposition, terminology and factorization follow two established open-source
simulators used as documented prior art (same footing as PAM/QuickFit3 in the
FCS references):

- **PyBroMo** (Ingargiola, OpenSMFS; `junk/PyBroMo/`) — a Brownian-motion confocal
  smFRET photon simulator: 3-D random walk in a box, an analytic Gaussian or
  numeric vectorial PSF, position-proportional emission rate, Poisson photon
  generation, constant-rate background/dark counts, FRET populations, and
  two-state kinetics assembled by mixing static per-state trajectories. Output is
  Photon-HDF5 for FRETBursts.
- **QuickFit3's FCS simulator plugin** (`qfe_fcssimulator`, Krieger & Langowski,
  DKFZ) — a configurable diffusion/FCS/FCCS forward simulator whose curves are
  imported back for fitting; the "simulate, then fit with the same tool" loop.

ChiSurf reimplements the physics independently on top of `tttrlib.SimEngine`;
nothing is a verbatim code copy.

## The forward factorization

A simulated confocal stream is the product of the same independent factors that
the *fit* models undo — which is exactly why a simulated stream is a valid test of
those models.

### 1 · Brownian trajectories

Free 3-D diffusion of each molecule in a box, MSD $\langle\Delta r^2\rangle=6D\tau$,
built by cumulative sum of per-axis Gaussian steps
$\Delta r\sim\mathcal N(0,2D\,\Delta t)$ at a fixed integration step $\Delta t$
(engine `settings.dt`, in ms). Reflect/re-inject boundaries keep occupancy
constant. Mean occupancy $N$ (engine `population`) sets fluctuation amplitude
($1/N$ in FCS). Diffusion time through the focus is
$\tau_D = w_{xy}^2/(4D)$ — the tie-in to [fcs-model-theory.md](fcs-model-theory.md).

### 2 · Detection/excitation profile (MDF)

3-D Gaussian $W(\mathbf r)=\exp(-2(x^2+y^2)/w_{xy}^2 - 2z^2/w_z^2)$, aspect
$\gamma=w_z/w_{xy}$ (the FCS structure parameter). Engine `excitation`
(`type: gaussian3d`, `w0`, `z0`, extents, spacing). A numeric vectorial PSF can be
substituted; the Gaussian is the analytic-FCS match.

### 3 · Position-dependent Poisson emission

Instantaneous rate $\lambda_s(\mathbf r)=q_s\,W(\mathbf r)$ from peak molecular
brightness $q_s$ (engine `species[i].q`, per channel, counts/s or kcps depending
on wrapper). Per-bin count is Poisson$(\lambda\Delta t)$; the bin index is the
macro-time stamp.

### 4 · FRET channel partitioning

FRET efficiency $E$ encoded as per-channel brightness
$q=[(1-E)q_0,\ \gamma_\text{det}E q_0]$ (see `workflow.simulate`, `species` list).
Baking $\gamma_\text{det}\neq1$ into the red channel makes the uncorrected
proximity ratio deliberately $\gamma$-distorted so calibration recovery can be
validated against `GroundTruth.gamma`. Leakage/direct-excitation are the same
mechanism as fixed cross-routing fractions. Cross-refs
[fret-theory.md](fret-theory.md), [fret-calibration.md](fret-calibration.md),
[crosstalk.md](crosstalk.md).

### 5 · Background, micro-time, detector effects

- Background: constant Poisson per channel (engine `background`, counts/ms) →
  dilutes FCS amplitude by $(1-B/I)^2$, broadens burst histograms.
- Micro-time: each photon draws a TCSPC channel from the species decay
  (`species[i].decay.lifetimes`) on a TAC axis of `n_microtime_channels ×
  microtime_resolution`; laser period `= n_microtime_channels × resolution`.
  Optional IRF convolution. This is the FLCS/lifetime axis.
- Detector artefacts: dead time and afterpulsing reproduce short-lag hardware
  distortions when enabled.

### 6 · Markov state kinetics

Continuous-time Markov process over states; off-diagonal rates in the rate matrix
(`k_nrad`/`k_rad`, or `exchange_rate` in the wrappers, 1/ms) drive spontaneous
interconversion during diffusion, so states can switch mid-burst. Zero rates →
static independent species. This is the signal dynamic-FCS relaxation terms and
H2MM ([h2mm-theory.md](h2mm-theory.md)) detect.

## Output record

Engine run interleaves species + background into one time-ordered stream, encoded
to a TTTR container (PTU/HT3/SPC) or returned as native arrays:
`macro_window()`/`arrival_time()` → absolute macro-time
(`macro_window * dt + arrival_time`), `micro_time()` → TAC channel,
`channel` → detector, and `emitting_species()` → the ground-truth per-photon label
(simulation-only) used to score recovered assignments and to build per-species
reference decays (the FLCS filter references in `simulate_lifetime_fcs`).

Note (`simulate.py` docstring): the native-array path is used rather than
`SimEngine.to_tttr` purely for simplicity/speed; `to_tttr` is faithful and yields
equally well-conditioned filters. Macro-times must be made ascending
(`np.maximum.accumulate`) before correlation.

## Closing the loop

A simulated stream is macro-times + micro-times + channels — formally
indistinguishable from a measurement. The correlator, burst search, FRET-histogram
builder and H2MM fitter are agnostic to its origin, so it **correlates, bursts and
Markov-fits exactly like real data**. Recovery of the injected parameters (across
seeds/bootstrap) is the validation criterion; mismatch isolates bias before real
data. In the burst workflow the simulated dataset is registered in MMFDB like any
real file, so `select → BVA → H2MM` runs unchanged.

## See also

- User concept: `docs/concepts/photophysics_simulation.md`
  (`concept-photophysics-simulation`).
- Guides: `docs/guides/18_tttr_simulation.md`,
  `docs/guides/31_h2mm_simulation_validation.md`.
- Code: `tttrlib.SimEngine`; `chisurf/core/fluorescence/fcs/simulate.py`;
  `chisurf/plugins/burst/burst_analysis/api/workflow.py` (`Simulation.simulate`);
  `chisurf/plugins/fcs/fcs_lfcs_sim/` (GUI); `flc_2d/simulate.py` (TCSPC/kinetics-
  only state-exchange simulator, the non-diffusing counterpart).
- Adjacent references: [fcs-model-theory.md](fcs-model-theory.md),
  [fret-theory.md](fret-theory.md), [h2mm-theory.md](h2mm-theory.md),
  [smfret-burst-analysis.md](smfret-burst-analysis.md).
- Prior art: PyBroMo (`junk/PyBroMo/`; Ingargiola et al., *PLoS ONE* **11**,
  e0160716, 2016); QuickFit3 `qfe_fcssimulator` (Krieger & Langowski, DKFZ).
- Literature: Wohland, Rigler & Vogel, *Biophys. J.* **80**, 2987 (2001) — FCS
  noise by Brownian-dynamics simulation; Gopich & Szabo, *J. Phys. Chem. B*
  **113**, 10965 (2009) — photon-by-photon FRET-trajectory theory.
