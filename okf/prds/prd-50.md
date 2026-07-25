---
type: PRD
prd: "50"
title: "PRD-50: Photon Distribution Analysis (PDA) Family"
description: Wrap the existing PDA histogram engine in ChiSurf models and AutoForm view specs, covering static distance-distribution PDA, dynamic/N-state kinetic PDA, error surfaces, three-color PDA, and a kinetic consistency check.
status: in-progress
phase: "unassigned"
resource: chisurf/core/models/pda/
tags: [prd, fret]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
Photon Distribution Analysis fits the shot-noise-broadened FRET-efficiency histogram of single-molecule bursts to recover inter-dye distance distributions and, in its dynamic form, kinetic exchange between conformational states. The `tttrlib.Pda` C++ engine already computes the histograms, but no ChiSurf model, `view.json`, or plugin wraps it. This PRD adds the model + schema + AutoForm UI + fit integration in staged scope: static (single/multi-Gaussian, Lorentzian) PDA, dynamic/N-state kinetic PDA, Support-Plane/MCMC error surfaces, three-color PDA, and a kinetic consistency check. Dual-color models are already ported to the PRD-38 model/view-spec split with headless coverage, both error-surface routes (support-plane and MCMC) are validated against each other, and the dynamic two-state criterion is met end to end (exchange rate recovered, nested static model rejected by F-test); time-binned dynamic PDA and three-color tcPDA remain.

# Status
Draft / unassigned (STATUS TABLE authoritative). Dual-color static plus a dynamic
two-state model done under AutoForm; error surfaces work via both support-plane and
MCMC; the dynamic acceptance criterion (rate recovery + F-test rejection of the static
model) is met. Follow-ups (GUI light-path hook, time-binned dynamic PDA, tcPDA) open.

Parent: [PRD-49](prd-49.md) (Phase 1, first target). Related: PRD-38
(model/view-spec split), PRD-40 (declarative editors), PRD-04 (burst pipeline),
PRD-28 (ndxplorer).

# Motivation

PDA quantitatively fits the shot-noise-broadened FRET-efficiency histogram of
single-molecule bursts to recover **inter-dye distance distributions** and, in its
dynamic form, **kinetic exchange between conformational states** — resolving whether
histogram width is shot noise, static heterogeneity, or dynamics. The incumbent
suite's PDA and three-color PDA apps are mature; ChiSurf has the compute engine but
no analysis surface.

**Current state.** `tttrlib.Pda` (C++) already computes PDA 1D/2D histograms given
per-channel background, an amplitude/probability spectrum `pF`, and `hist2d_nmin/nmax`
bounds — but **no ChiSurf model, `view.json`, or plugin wraps it**, so PDA is
unavailable at the application level (PRD-49 status: ENGINE-ONLY). This is the
highest-reuse gap: the math exists; we need the model+UI+fit integration.

# Progress (updated)

**Done (dual-color, AutoForm + view.json):**
- Ported the three existing PDA models to the PRD-38 model/view-spec split — pure
  models + `*.view.json`, registered directly in `experiment_configs.yaml`, rendered
  by `build_model_editor` → AutoForm (no hand-built Qt): `PdaSimpleModel`
  (`simple.view.json`), `PdaGaussianDistanceModel` (`pdagauss.view.json`),
  `PdaAnisotropyModel` (`anisotropy.view.json`).
- Added a **dynamic two-state PDA model** (`dynamic.py` +
  `PdaDynamicTwoStateModel` + `dynamic.view.json`): exact two-state occupation-time
  distribution (Bessel form), reduces to static two-Gaussian (slow) and single
  averaged population (fast). Registered in the config.
- Added **γ / α / δ** as read-only computed output parameters on `PdaFretNuisance`
  (`update_correction_factors`), plus a **light-path connection**:
  `PdaFretNuisance.apply_lightpath_matrices(...)` and
  `common.apply_lightpath_to_nuisance(...)` ingest the light-path simulator's
  `crosstalk_matrices` (excitation → ExDG/ExAG, emission → cGD/cGA/cRD/cRA).
- Qt-free distribution plot accessor `common.get_pda_distribution` (string-keyed
  axis) + generalized `resolve_distribution_options` to import dotted/`module:func`
  accessors, so the PDA E-histogram plot is authorable in JSON.
- Added a **three-state Gillespie/MC dynamic model** (`dynamic_mc.py` +
  `PdaDynamicThreeStateModel` + `dynamic_mc.view.json`), verified against the
  analytic equilibrium populations.
- The **2D S1S2 weighted-residual image** is registered as a view-spec plot key:
  `common.get_pda_residual_image` + `gui.plots.residual_image.Residual2DPlot`,
  resolved from `pdagauss.view.json` (tested via `model_plot_specs`).
- Headless coverage: `test/gui/test_pda_model_editor.py` — renders + computes for
  all five PDA models; dynamic two-/three-state limit checks; correction-factor +
  light-path bridge; P(R) + 2D-residual plot resolution; and (2026-07-24) a
  **fit-recovery test** exercising the PRD's primary acceptance criterion:
  `test_pda_gaussian_fit_recovers_distance` uses the model's own S1S2 histogram at a
  known mean as the data, fixes all but the mean, perturbs it, and asserts
  `fit.run()` recovers the true distance.
- **1D-residual χ² fix + SPA error surfaces (2026-07-24).** Fixed two bugs in
  `common.pda_1d_residuals_from_s1s2`: (1) the model S1S2 histogram (a normalised
  probability distribution, sum ≈ 1) was **not scaled to the data's total counts**
  before the Poisson residual, so the model term was ≈ 0 and χ² collapsed to a
  flat, mean-independent `sum(data)` offset (χ²ᵣ ≈ 12 instead of ≈ 1); (2) the data
  1D-histogram cache keyed on `id(pda_meta)` + size, so it did not invalidate when
  the experimental S1S2 was replaced in place. With both fixed, PDA fits give a
  proper Poisson χ²ᵣ ≈ 1 and a sharp minimum — this improves **all five** PDA
  models (they share this residual), not just error surfaces. Support-plane error
  surfaces now work: `test_pda_error_surface_ci_brackets_truth` runs
  `Fit.adaptive_chi2_scan` on the mean and asserts the 99% F-test CI brackets the
  true value (previously the surface was flat and the CI came back `(None, None)`).

- **MCMC error surfaces + Metropolis sign fix (2026-07-24).** With SPA working,
  wiring MCMC to PDA exposed a sign error in the Metropolis acceptance test of
  `chisurf/core/fitting/sample.py::walk_mcmc`: it compared
  `(-lnp_next + lnp_prev)` against `log(u)`, i.e. it accepted moves that *lowered*
  the log-posterior and so sampled `exp(+chi2/2)`. A chain started at the optimum
  ran away from it (chi2r 1.0 → 3e6). The same function also skipped rejected
  proposals instead of re-recording the current state, which biases the chain, and
  ignored `thin`. All three are fixed, and the sampler now also reports its
  `acceptance_rate`. Validated two ways: against the analytic posterior
  `sigma^2 (X'X)^-1` of a linear model (widths agree to ~5%,
  `test/fitting/test_mcmc_posterior.py`), and on PDA itself
  (`test_pda_mcmc_posterior_brackets_truth_and_agrees_with_support_plane`), where
  the 99% credible interval brackets the true distance and its width agrees with
  the independent support-plane F-test interval to ~8%. Since `walk_mcmc` is the
  generic sampler, this fixes MCMC error surfaces for **every** ChiSurf model, not
  only PDA.
- **Adaptive MCMC proposals (2026-07-24).** `walk_mcmc` proposal widths were a
  fixed fraction of each parameter's *starting value*, so a well-determined
  parameter was proposed far outside its posterior and almost nothing was accepted
  (0.7% in the linear-model check) — correct but unusable. A warm-up phase now
  tunes the widths: they are re-derived once from the spread of the warm-up states
  and rescaled by a Robbins-Monro recursion towards a target acceptance rate, then
  **frozen** before recording, so the returned chain stays a time-homogeneous
  Markov chain. Acceptance went 0.7% → 30.7% at unchanged accuracy, and warm-up
  recovers a deliberately 50×-too-wide `step_size`
  (`test_walk_mcmc_warmup_tunes_a_badly_scaled_step_size`).
- **`sample_emcee` step accounting (2026-07-24).** The ensemble backend passed
  `nsteps=steps` together with `thin_by=thin`; the underlying sampler counts
  `nsteps` in *stored* states when thinning, so it silently ran `steps * thin`
  iterations and stored `steps` per walker instead of the documented `steps // thin`.
  The loop now iterates in stored states and reports progress in raw steps.

- **Dynamic-PDA recovery + F-test rejection of the static model (2026-07-25).** The
  remaining dynamic acceptance criterion is met by
  `test_dynamic_pda_recovers_exchange_and_rejects_the_static_model`: data is a Poisson
  realisation of the two-state model at `K_ex = 2`, and the fit recovers
  `K_ex = 1.99`, `R1 = 40.1`, `R2 = 62.0`, `x1 = 0.503` from a perturbed start at
  `chi2r = 1.04`. The static alternative is the *nested* `K_ex = 0` limit given the
  same freedom in both distances and the occupancy — it pulls the two distances
  together (40/62 → 42.6/56.9) to imitate dynamic averaging and still only reaches
  `chi2r = 150.9`, which the F-test rejects at confidence 1 − 2e-62.
- **F-test calculator fixed (2026-07-25, BUG-05).** Reaching for the `f_test` plugin to
  close the criterion above showed its two directions were not inverses: asking for 95%
  confidence returned a χ² the tool itself then scored at 0.09%, and the ratio was
  taken complex-over-simple so confidence *fell* as the added parameters became more
  justified. The statistics now live in `chisurf.core.math.statistics`
  (`f_test_confidence`, `f_test_chi2r`) and are shared by the plugin and the test
  above. See [assessment BUG-05](/specs/assessment.md#bug-05) for why the convention
  was determined rather than guessed.

**Follow-ups (not yet done):**
- GUI button wiring the live light-path plugin session to a selected PDA model
  (the pure bridge API is done and tested; only the one-click GUI hook remains).
- Full time-binned dynamic PDA (an N-vs-observation-time grid, the number-of-E-bins /
  number-of-time-bins scheme) — the current dynamic models use a single
  dimensionless exchange parameter `K_ex`.
- Three-color tcPDA (later stage).

# Scope (staged)

1. **Static distance-distribution PDA.** Model over `tttrlib.Pda`: single- and
   multi-Gaussian (and Lorentzian) P(R) → P(FRET) → shot-noise histogram; fit to a
   1D E (or S_g) histogram from a burst dataset with γ/crosstalk/direct-excitation/
   background corrections. Multi-file global fit.
2. **Dynamic / N-state kinetic PDA.** 2- and 3-state (extensible N-state) kinetic
   networks with exchange rates convolved over the burst-duration / time-window; fit
   rates + state distances/populations.
3. **Error surfaces.** Wire Support-Plane-Analysis, MCMC, and Hessian/covariance
   estimation to PDA parameters via `chisurf/core/fitting/sample.py`.
4. **Three-color tcPDA.** 1D/2D/3D three-color distance distributions, time-binned,
   with Bayesian priors — after (1)–(3) land.
5. **Kinetic consistency check.** Resample burst data from a fitted kinetic scheme and
   compare to the measured histogram (the incumbent's "consistency check"); reuses the
   dynamic-PDA simulator.

# Design

- **Compute core:** wrap `tttrlib.Pda` — do not reimplement histogram math. A thin
  `chisurf/core/fluorescence/pda/` module builds the `pF` spectrum from a P(R) model and
  drives `Pda.hist2d`/1D outputs; the fit objective compares model vs. measured
  histogram (MLE / χ²).
- **Model + schema:** `chisurf/core/models/pda/` model class(es) + `chisurf/core/dataspec/`
  schema, mirroring the structure of `chisurf/core/models/rics/` and `.../fcs/`.
- **UI = AutoForm + `view.json`** (PRD-49 AutoForm mandate): parameters (distances,
  widths, populations, corrections, kinetic rates) via `parameter_table`; histogram/fit
  overlay via an AutoForm plot section. No bespoke Qt. Add a section to
  `chisurf/gui/autoform/sections/` only if none fits (e.g. an overlay-histogram section),
  so other plugins reuse it.
- **Fit wiring:** register with the fitting stack so the model is selectable in the
  add-fit flow (the seam the `test-model-editor` skill exercises).
- **Data source:** consume burst tables / photon selections produced by
  `burst_selection` (E/S, corrections, PIE channels) and MMFDB-registered datasets via
  `ChiSurfAPI` — not globals.

# Reuse

- `tttrlib.Pda` — histogram engine (constructor: `hist2d_nmax, hist2d_nmin,
  background_ch1, background_ch2, pF, implementation=PDA_DEFAULT|PDA_OPTIMIZED`).
- `chisurf/core/models/rics/`, `.../fcs/` — model + view.json templates.
- `chisurf/core/fitting/sample.py` — SPA / MCMC / covariance error surfaces.
- `chisurf/gui/autoform/` + `sections/` — declarative UI.
- `burst_selection` / `ndxplorer` — burst tables, corrections, E/S histograms.
- PRD-49 structural-FRET stack — P(R) priors can come from AV models
  (`fps_json_editor`, `fret_line`), a differentiator over the incumbent.

# Acceptance

- **Headless (primary):** a test builds the static PDA model, generates a synthetic
  2-Gaussian E-histogram via `tttrlib.Pda`, fits it, and asserts recovered mean
  distances/widths/populations within tolerance — runnable through the
  `test-model-editor` skill pattern; added under `test/` or `chisurf/core/models/pda/test/`.
- **Dynamic PDA:** synthetic 2-state exchange at known rate is recovered; static-only
  fit is rejected by F-test (`f_test` plugin).
  *(Met — `K_ex` recovered to 0.4%, the nested static limit rejected at confidence ~1.)*
- **Error surface:** SPA/MCMC produces a confidence interval bracketing the true value.
  *(Met — both routes, and they agree on the interval width.)*
- **UI:** model appears in the add-fit combobox, renders parameter groups and the
  histogram-overlay from `view.json` with no empty groups or crashes (model-editor
  headless checks).
- **tcPDA (later stage):** synthetic three-color dataset recovers the three pairwise
  distances.

# Non-goals

- No new bespoke Qt widgets (PRD-49 AutoForm mandate).
- Not reimplementing PDA histogram math outside `tttrlib`.
- Antibunching/nsFCS and FCCS models are PRD-54, not here.

# Relationships
- Child of [PRD-49](prd-49.md) (Phase 1, first target).
- Wraps the `tttrlib.Pda` engine; consumes burst tables from the burst-selection pipeline.
- Renders via [GUI & AutoForm](/subsystems/gui-autoform.md); reads datasets through [Core target](/specs/core.md) rather than globals.
