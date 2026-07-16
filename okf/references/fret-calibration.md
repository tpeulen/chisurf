---
type: Reference
title: "smFRET calibration: light-path prior → data-optimized posterior"
description: How ChiSurf turns calibration factors (gamma, leakage, direct excitation, R0) into fittable parameters whose prior comes from the light-path calculator and whose posterior comes from optimizing against the data.
tags: [reference, fret, calibration, priors, bursts]
timestamp: '2026-07-16T00:00:00Z'
---

# smFRET calibration — light-path prior, data-optimized posterior

Accurate single-molecule FRET requires calibration factors that turn raw
green/red/yellow photon counts into a true efficiency: the detection/quantum-yield
ratio `gamma`, the donor spectral leakage `alpha`, the direct acceptor excitation
`delta`, the channel backgrounds and the Förster radius `R0`. ChiSurf models these
as real **fitting parameters** with a Bayesian workflow:

- the **light-path calculator** supplies each factor's **prior** — a
  physically-motivated Gaussian centred on the value computed from the optics
  (spectra, filters, detector QE), width = model uncertainty;
- **optimizing against the measured data** yields the **posterior** — the
  factors actually used for accurate FRET.

The light-path value is only the prior; the data refines it. When the data is
informative the posterior follows the data; when it is scarce the posterior falls
back to the physically-motivated light-path prior.

## What is there (implemented)

- **Calibration parameter group** —
  `chisurf/core/fluorescence/fret/calibration.py::CalibrationParameters`, a
  Qt-free `FittingParameterGroup` of bounded `FittingParameter`s (`gamma`,
  `alpha`, `delta`, `Bg`/`Br`/`By`, `R0`, `PhiA`/`PhiD`). Because they are ordinary
  fitting parameters, ChiSurf's priors machinery
  (`chisurf/core/fitting/priors.py`, `Fit.set_parameter_prior`, `_prior_residuals`
  for MAP and `lnprob` for MCMC) regularizes them automatically.
- **Light-path → prior bridge** — `lightpath_correction_factors(...)` computes
  `gamma = (gR·cRA·QYA)/(gG·cGD·QYD)`, `alpha` (leakage) and `delta` (direct
  excitation) from a light-path `get_crosstalk_matrices()` payload (reusing
  `crosstalk.matrix_from_payload` and the MFD algebra from `pda/nusiance.py`);
  `set_priors_from_lightpath(...)` attaches a `NormalPrior` on `gamma`/`R0` and a
  `TruncatedNormalPrior` on the bounded `alpha`/`delta`.
- **Per-burst E-S core** — `chisurf/core/fluorescence/burst/es.py`:
  `apparent_es` (raw proximity ratio + raw stoichiometry) and `corrected_es`
  (three-cube corrected `E` and `S`, reusing `crosstalk.correct_three_cube`).
  Stoichiometry `S` for ALEX/PIE was previously absent from the burst code.
- **Layered calibration optimization** (`calibration.py`):
  - `global_es_correction(...)` — the data estimate of `gamma` from the E-S
    population linear fit `1/S = Ω + Σ·E` (Lee 2005 / Hellenkamp 2018;
    `gamma = (Ω−1)/(Ω+Σ−1)`), after leakage/direct-excitation correction.
  - `refine_calibration(...)` — the **posterior**: the precision-weighted
    (Bayesian) combination of that data estimate (uncertainty bootstrapped over
    bursts) and the light-path Gaussian prior. Strong data → posterior ≈ data;
    weak data → posterior ≈ prior.
- **Simulated ground truth** — `BurstWorkflow.simulate(..., gamma=…)` bakes a
  known detection factor into the tttrlib photon simulation (red-channel
  brightness scaled by `gamma`), recorded on `GroundTruth.gamma`, so calibration
  recovery is validated end-to-end (simulate → burst-select → correct → recover E).
- Tests: `test/fitting/test_fret_calibration.py` (unit: factors, priors, E-S
  recovery, gamma recovery, strong-vs-weak-data posterior) and
  `test/plugins/burst/test_calibration_simulation.py` (end-to-end on simulated
  bursts). Example notebook:
  `chisurf/plugins/burst/burst_analysis/examples/FRET_Calibration.ipynb`.

## What is missing (later phases)

- **Session-shared calibration for global analysis.** Expose
  `CalibrationParameters` as a dataset-free pseudo-fit in `cs.fits` so any fit's
  correction parameters can `.link` to it (appearing in the parameter-link
  widget), calibrating once across many datasets.
- **ndxplorer bridge.** Push the posterior calibration into the in-process
  ndxplorer constants (`NDXplorer.parameter_control` + `parameter_update`) so
  ndx's derived FRET columns use the data-optimized calibration.
- **`alpha`/`delta` from donor-only/acceptor-only** populations (data-driven,
  not just the light-path prior); a full ALEX `beta` for stoichiometry
  normalisation.
- Per-pixel/FLIM reuse; a GUI for the calibration workflow.

## Pointers

- Core: `chisurf/core/fluorescence/fret/calibration.py`,
  `chisurf/core/fluorescence/burst/es.py`,
  `chisurf/core/fluorescence/crosstalk.py`.
- Priors: `chisurf/core/fitting/priors.py`, `chisurf/core/fitting/fit.py`
  (`set_parameter_prior`, `_prior_residuals`, `lnprob`).
- Factor algebra reused from `chisurf/core/models/pda/nusiance.py::PdaFretNuisance`.
- Simulation: `chisurf/plugins/burst/burst_analysis/api/workflow.py`
  (`simulate`, `GroundTruth`, `select_bursts`).
