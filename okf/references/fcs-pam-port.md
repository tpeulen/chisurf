---
type: Reference
title: "FCS model catalogue & FLCS filters: PAM port status and gaps"
description: What ChiSurf's FCS fit-model catalogue and FLCS lifetime-filter code gained from porting PAM as reference (A/B verified), and what is still missing.
tags: [reference, fcs, flcs, diffusion, roadmap]
timestamp: '2026-07-15T00:00:00Z'
---

# FCS model catalogue & FLCS filters — PAM port

PAM (Schrimpf et al. 2018) is used as the reference implementation for ChiSurf's
Fluorescence Correlation Spectroscopy (FCS) fit models and its filtered-FCS
(FLCS) lifetime-filter maths. Ports are **A/B-verified**: each PAM model's MATLAB
`fit` lambda (`junk/PAM/Models/fcs/*.m`) is transcribed verbatim as the reference
and asserted equal, over random parameters, to the ChiSurf implementation.

## What is there (implemented / ported)

### FCS fit-model catalogue (`chisurf/core/models/fcs/models.yaml`)
Thirteen physically-parametrised, **absolute-D** models ported from PAM (x in
seconds; D in µm²/s; w_r/w_z/diam in µm; tau in µs; v_flow in µm/s; freq in kHz;
k in 1/s). PAM's inline SI conversions (`4·D·1e-12·x/(w·1e-6)²`) cancel to the
reduced `4·D·x/w²`; the A/B test validates that simplification.

- `3D diffusion (D, triplet)` — PAM `FCS_D`
- `3D diffusion, 2 components (D, triplet)` — `FCS_D_2Component`
- `3D diffusion, 2 triplet (D)` — `FCS_D_2exp`
- `3D diffusion (tauD, triplet)` — `FCS_TauD`
- `3D anomalous diffusion (tauD, triplet)` — `FCS_TauD_anomalous`
- `3D diffusion + flow (D, triplet)` — `FCS_flow`
- `3D diffusion + background (D, triplet)` — `FCS_D_Background` (`(1-BG/Counts)²`)
- `3D diffusion + afterpulsing (D, triplet)` — `FCS_D_afterpulsing` (additive stretched-exp)
- `3D diffusion + bleaching (tauD)` — `FCS_TauD_Bleaching`
- `Two-focus 3D diffusion (D, triplet)` — `FCS_2Focus_D` (Dertinger absolute D; `diam` = known inter-focus distance; `diam=0` → single focus)
- `FRET-FCCS, 2-state (D)` — `FCS_FRETFCCS` (donor-auto / acceptor-auto / cross with shared 2-state exchange)
- `ns-FCS antibunching + bunching + triplet` — `nsFCS_ab_cd_triplet`
- `Scanning FCS (D, triplet)` — `FCS_Scanning` (periodic sin² term)

All carry the γ = 1/√8 prefactor and (where applicable) the triplet term
`1 + Trip/(1-Trip)·exp(-x/tau_T)`. Verified by `test/fitting/test_fcs_pam_ab.py`
(A/B against PAM + a catalogue-wide parse check) and the two-focus physics test
`test/fitting/test_fcs_2ffcs.py`.

Note: the **two-focus** model is the PAM `FCS_2Focus_D` Gaussian form — PAM
itself uses the Gaussian two-focus MDF, not the full non-Gaussian Dertinger MDF
(see gaps).

### FLCS lifetime filters (`chisurf/core/fluorescence/fcs/filtered.py`)
The core weighted-pseudo-inverse filter maths (`calc_ffcs_filters`,
`F = (Dₙᵀ W Dₙ)⁻¹ Dₙᵀ W`, `W = diag(1/I)`) was already a correct PAM
(`Calc_fFCS_Filters`) port. Added/fixed here:

- **Conditioning** — `calc_ffcs_filters` now takes `rcond` (truncated-SVD
  pseudo-inverse) and `tikhonov` (ridge `G + λI`) options to tame
  noise-amplifying filters when patterns are near-collinear (similar lifetimes);
  default behaviour is unchanged.
- **Diagnostics** — `filter_condition_number(...)` returns cond(`Dₙᵀ W Dₙ`) so
  collinear patterns can be detected before use.
- **Afterpulsing removal** — `uniform_pattern(n_bins)` provides the flat
  micro-time pattern to add as an extra "species", giving afterpulse/dark-count-
  free filters (the classic Enderlein trick).
- **Per-photon weighting** — `photon_filter_weights(filters, micro_times)` maps
  each photon's micro-time to its per-species filter weight, the input a weighted
  correlator needs (the core step for wiring filters into correlation).
- **Bug fix** — the legacy `calc_lifetime_filter` no longer divides by zero on
  empty total-decay bins, and its nonstandard global filter renormalisation
  (which broke the `Σ_t R_k(t)·p_j(t) = δ_kj` relation) was removed.

Verified by `test/fitting/test_fcs_filters.py` (orthogonality relation,
amplitude recovery, afterpulse removal, conditioning, zero-bin guard).

## What is missing (not implemented)

- **Filters not wired into the general correlator.** `fcs_filter_calculator`
  computes/exports filters; the `fcs_correlator` plugin still weights photons
  with binary channel/micro-time masks only. Only `flc_2d` consumes filters. The
  new `photon_filter_weights` helper is the building block; the remaining work is
  a lifetime-filter weight source in the correlator GUI that runs one
  `tttrlib.Correlator` per species auto/cross pair.
- **Channel-aware (par/perp / multi-PIE) weighting.** PAM stacks multiple
  detection channels onto one micro-time axis and applies separate par/perp
  filters per photon; ChiSurf's application path uses a single micro-time axis
  regardless of routing channel. Needs a 2-D `filters[channel, micro_time]`
  table and a stacked-axis builder.
- **Automatic scatter/IRF and donor-only pattern species.** PAM can auto-append a
  measured scatter/IRF column and a donor-only column; ChiSurf requires the user
  to add such a pattern manually as a generic species file.
- **Model-generated patterns.** Patterns are file-loaded empirical decays only;
  no option to build a species pattern from a fitted multi-exponential model
  reconvolved with the IRF.
- **Dertinger non-Gaussian MDF two-focus model.** The ported two-focus model is
  the Gaussian form (as in PAM). The fully accurate Dertinger model needs a
  numerically-integrated non-Gaussian detection function (`erf`/quadrature) and
  would be a coded FCS model, not a `models.yaml` string.
- **Remaining PAM models not yet ported:** pair-correlation distributions
  (`PCF_LogNormal`, `PCF_LogGaussian`, `PCF_GammaDistribution`), the
  space-cross-correlation anomalous family (`FCS_SCCF_*`), `fullFCS_*` pulsed
  models, and `nsFCS_PDA23_Gauss5` / MIA image-correlation. (ChiSurf already has
  RICS and 2D-FLCS natively.)
- **Guided global-fit preset for absolute-D two-focus.** Fitting the two-focus
  auto+cross curves with shared D/w_r/w_z (diam fixed) is possible through the
  existing global-fit machinery but has no dedicated GUI preset.

## Pointers

- Models: `chisurf/core/models/fcs/models.yaml`; parser
  `chisurf/core/models/parse/parse.py` (`ParseModel`).
- Filters: `chisurf/core/fluorescence/fcs/filtered.py`; plugin
  `chisurf/plugins/fcs/fcs_filter_calculator/`; 2D-FLC consumer
  `chisurf/plugins/fcs/flc_2d/fit/dynamics.py`.
- PAM reference: `junk/PAM/Models/fcs/*.m`,
  `junk/PAM/functions/BurstBrowser/Calc_fFCS_Filters.m`.
- Tests: `test/fitting/test_fcs_pam_ab.py`, `test_fcs_2ffcs.py`,
  `test_fcs_filters.py`.
- FCS plugin group overview: [/plugins/fcs.md](/plugins/fcs.md).
