---
type: Reference
title: "Two-focus FCS (2fFCS): status and gaps"
description: What ChiSurf's two-focus FCS (absolute-diffusion) model support covers today and what a full Dertinger 2fFCS workflow still needs.
tags: [reference, fcs, diffusion, roadmap]
timestamp: '2026-07-15T00:00:00Z'
---

# Two-focus FCS (2fFCS)

Two-focus FCS (Dertinger et al., *ChemPhysChem* **8**, 433 (2007)) measures an
**absolute** diffusion coefficient without a separately calibrated detection
volume. Two overlapping laser foci are created a **known** lateral distance
`d` apart (typically by alternating two orthogonally polarised beams through a
Nomarski/DIC prism). One records the auto-correlation of each focus and the
cross-correlation between the two foci; because `d` sets a ruler in real
length units, a global fit of the auto- and cross-correlation curves recovers
`D` (and the beam waist `w0`) on an absolute scale, largely free of the
volume-calibration bias that limits single-focus FCS.

The characteristic signature is that the **cross-correlation peaks at a finite
lag** — a molecule needs time to diffuse from one focus to the other — rather
than decaying monotonically like an auto-correlation.

## What is there (implemented)

Two-focus FCS is now part of the PAM-derived FCS model catalogue (see
[FCS catalogue & FLCS filters: PAM port](fcs-pam-port.md) for the full family
and the A/B-verification methodology):

- **`Two-focus 3D diffusion (D, triplet)`** in
  [`chisurf/core/models/fcs/models.yaml`](/plugins/fcs.md) — ported from PAM's
  `FCS_2Focus_D` (Dertinger 2007) and A/B-verified against its exact formula.
  In the absolute parametrisation `D`, `w_r`, `w_z` (µm, µm²/s, x in s) plus a
  triplet term, the `exp(−diam²/(w_r² + 4·D·x))` cross-term (`diam` = known
  inter-focus distance) makes the correlation peak at a finite lag and yields an
  **absolute** `D`. Setting `diam = 0` recovers the single-focus
  `3D diffusion (D, triplet)` model, so the auto- and cross-correlation share
  the same parameters.
- **Absolute-`D` workflow via global fitting.** Load the auto- and
  cross-correlation curves as two datasets, share `D`/`w_r`/`w_z`, fix `diam` to
  the known distance, and keep `N` and `y_0` per curve; the known `diam`
  propagates the length scale into `D`. The correlation engine
  (`chisurf/core/fluorescence/fcs/correlate.py`) already produces the
  cross-correlation, with channel pairing in `channel_setups.py`.
- **Headless tests.** `test/fitting/test_fcs_2ffcs.py` asserts the physics
  (cross-correlation peaks at a non-zero lag; reduces exactly to the
  single-focus model at `diam = 0`), and `test/fitting/test_fcs_pam_ab.py`
  A/B-verifies the equation against PAM.

## What is missing (not implemented)

- **Dertinger's non-Gaussian modified detection function.** The accurate 2fFCS
  model replaces the 3D-Gaussian MDF with a Gaussian-Lorentzian /
  optical-saturation form whose closed correlation function contains the error
  function `erf` and extra shape parameters (`w0`, `a`, `κ`, `R`). The current
  catalogue models are the **Gaussian approximation**; the full model cannot be
  expressed as a `models.yaml` string because the equation evaluator exposes
  only the NumPy namespace (`exp`, `sqrt`, `abs`, …) and **not** `scipy.special`
  (`erf`). Adding it needs either an `erf` binding in the parser scope or a
  dedicated coded FCS model class rather than a string equation.
- **Focus-distance calibration.** `d` must be entered by hand as a known
  constant. There is no routine to calibrate `d` from a reference dye of known
  `D` (the usual bootstrap), nor to propagate its uncertainty into `D`.
- **Dedicated 2f acquisition/correlation wiring.** No preset ties the two
  polarisation/alternation channels to "focus 1 / focus 2" and emits the
  auto/auto/cross triple as a labelled 2fFCS dataset group; today the user must
  route channels and pair curves manually via `channel_setups.py`.
- **GUI preset / guided global fit.** No AutoForm view or wizard sets up the
  shared-`D`/`w0`/`s`, fixed-`d`, per-curve-`N` global fit; it must be assembled
  by hand in the fitting UI.
- **Model richness.** No triplet/blinking or multi-component variants of the
  two-focus form (the single-focus catalogue has many bunching variants; the 2f
  entries are single-component, no triplet).
- **Validation against real/simulated 2f data.** Tests cover the analytic
  properties only; there is no end-to-end absolute-`D` recovery test against a
  simulated or reference two-focus dataset (the tttrlib simulator could provide
  two laterally offset PSF grids to generate one).

## Pointers

- Models: `chisurf/core/models/fcs/models.yaml` (entries `2f-FCS *`).
- Parser: `chisurf/core/models/parse/parse.py` (`ParseModel`).
- Correlation engine / channel pairing:
  `chisurf/core/fluorescence/fcs/{correlate.py,channel_setups.py}`.
- Tests: `test/fitting/test_fcs_2ffcs.py`.
- FCS plugin group overview: [/plugins/fcs.md](/plugins/fcs.md).
