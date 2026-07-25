---
name: fit-correlation
description: >-
  Fit fluorescence correlation curves (FCS) for diffusion times, particle
  numbers and fast photophysics. Use when the user mentions FCS, correlation
  curves, diffusion, or a .cor/.asc/.sin correlation file.
triggers:
  - fcs
  - correlation
  - correlogram
  - diffusion
  - diffusion time
  - triplet
  - autocorrelation
  - cross-correlation
  - brightness
experiments: [FCS, PCF]
tools:
  - list_files
  - load_data
  - list_experiments
  - create_fit
  - run_fit
  - get_fit
  - set_parameter
  - fit_report
  - plot_fit
---

# Fitting a correlation curve

An FCS curve is the temporal autocorrelation of the fluorescence signal. Its
amplitude carries the number of molecules in the observation volume and its
decay carries how fast they move through it.

## How these models differ from decay models

There is **no instrument response and no component count to raise** — the
correlation models are closed-form expressions with a fixed parameter set, so
`set_irf` and `set_components` do not apply. Improving a correlation fit means
deciding **which parameters are free and which are fixed**, and that is a
judgement about the instrument, not about the data.

Call `get_fit` and look at what is free before doing anything else.

## What the parameters mean

The general diffusion model exposes, among others:

* `N` — average number of particles in the observation volume. The
  correlation amplitude is essentially `1/N`, and the concentration follows
  from it and the effective volume.
* `D` — diffusion coefficient; `tauD` is the corresponding diffusion time.
* `w0`, `wem` — the lateral and axial dimensions of the observation volume,
  with `w_r`/`w_z` as their ratios.
* `b` — the bunching/antibunching amplitude, for fast photophysics such as
  triplet blinking (typically microseconds, well below the diffusion time).
* `bg` — background.

## The judgement that matters

**The shape of the observation volume is a calibration, not a fit result.**
`w0`, `wem` and their ratios come from a calibration measurement with a dye of
known diffusion coefficient — and they arrive **free** in a fresh fit. Leaving
them free while also fitting `D` makes both meaningless, because the fit can
trade a wider volume against slower diffusion and reach the same curve. Fix
them (`set_parameter` with `fixed=true`) at the calibrated values, then fit
`N` and `D`.

If the curve shows a fast component that diffusion cannot explain, free `b`.
Do not free it by reflex: an unnecessary bunching term will absorb noise.

## Interpreting

* A brighter species contributes to the correlation quadratically, so a
  correlation-derived particle number is not a headcount of a mixed sample.
* Diffusion times scale with the square of the beam waist, so they are only
  comparable between measurements on the same calibrated instrument.
* Report `N` and `D` (or `tauD`) with uncertainties, and **say which
  parameters you fixed and to what** — the numbers are meaningless without it.

## When it will not fit

Correlation curves are weighted most heavily at short lag times, where the
noise is smallest. Structured residuals only at long lag usually mean the
measurement was too short. A curve that does not flatten at long lag, or that
rises again, means drift, aggregates or a bleaching sample — no choice of
model fixes that, and saying so is the useful answer.
