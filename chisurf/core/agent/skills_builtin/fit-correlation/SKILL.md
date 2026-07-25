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
  - set_parameter
  - fit_report
  - plot_fit
---

# Fitting a correlation curve

An FCS curve is the temporal autocorrelation of the fluorescence signal. Its
amplitude carries the number of molecules in the observation volume and its
decay carries how fast they move through it.

## Before fitting

* **Load with the right reader.** Correlation formats differ in whether they
  carry an uncertainty column, and the weights decide what the fit means.
  `list_experiments` shows the FCS readers; pick the one matching the
  instrument that wrote the file (`.cor` from the Seidel-style correlator,
  `.asc` from an ALV, `.sin` from a Correlator.com device, `.fcs` from a
  Confocor).
* **Look at the curve first.** `get_curve` or `plot_fit` after a first pass:
  a curve that does not flatten at long lag times, or that rises again, means
  drift, aggregates or a bleaching sample — no model choice fixes that.

## Choosing a model

Call `list_experiments` for the exact names. The general diffusion model is
the usual starting point; add a bunching/antibunching term only when the
curve shows a fast component that diffusion cannot explain (triplet
blinking typically appears in the microsecond range, well below the diffusion
time).

The shape of the observation volume is a *calibration*, not a fit result. The
axial-to-lateral ratio should come from a calibration measurement with a dye
of known diffusion coefficient, and be **fixed** — letting it float while
also fitting the diffusion time makes both meaningless.

## Interpreting

* The **amplitude** at short lag gives the average particle number, and its
  inverse is the concentration in the effective volume. A brighter species
  dominates the correlation quadratically, so a correlation-derived particle
  number is not a headcount of a mixed sample.
* The **diffusion time** scales with the square of the beam waist, so it is
  only comparable between measurements on the same calibrated instrument.
* Report the diffusion time and particle number with uncertainties, and say
  which parameters you fixed and why.

## When it will not fit

Correlation curves are heavily weighted at short lag times where the noise is
smallest. If the residuals are structured only at long lag, the measurement is
probably too short — say so rather than adding components.
