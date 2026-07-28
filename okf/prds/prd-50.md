---
type: PRD
prd: "50"
title: "PRD-50: Photon Distribution Analysis (PDA) Family"
description: Wrap the existing PDA histogram engine in ChiSurf models and AutoForm view specs, covering static distance-distribution PDA, dynamic/N-state kinetic PDA, error surfaces, and a kinetic consistency check (three-color PDA is PRD-65).
status: in-progress
phase: "unassigned"
resource: chisurf/core/models/pda/
tags: [prd, fret]
timestamp: '2026-07-05T00:00:00Z'
---

# Summary
Photon Distribution Analysis fits the shot-noise-broadened FRET-efficiency histogram of single-molecule bursts to recover inter-dye distance distributions and, in its dynamic form, kinetic exchange between conformational states. The `tttrlib.Pda` C++ engine already computes the histograms, but no ChiSurf model, `view.json`, or plugin wraps it. This PRD adds the model + schema + AutoForm UI + fit integration in staged scope: static (single/multi-Gaussian, Lorentzian) PDA, dynamic/N-state kinetic PDA, Support-Plane/MCMC error surfaces, and a kinetic consistency check; three-color PDA is split out into PRD-65. Dual-color models are already ported to the PRD-38 model/view-spec split with headless coverage, both error-surface routes (support-plane and MCMC) are validated against each other, the dynamic two-state criterion is met end to end (exchange rate recovered, nested static model rejected by F-test), and time-binned dynamic PDA is in: the reader can cut fixed-width bins, the models take their observation time from the data, and the exchange parameter is an absolute rate that a global fit shares across bin widths. Three-color c3PDA is now [PRD-65](prd-65.md).

# Status
Draft / unassigned (STATUS TABLE authoritative). Dual-color static plus a dynamic
two-state model done under AutoForm; error surfaces work via both support-plane and
MCMC; the dynamic acceptance criterion (rate recovery + F-test rejection of the static
model) is met. Follow-ups closed: light-path hook and the consistency-check GUI surface both
land on a shared Diagnostics panel. c3PDA split out into [PRD-65](prd-65.md).

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

- **Kinetic consistency check (2026-07-25, scope item 5).** New
  `chisurf/core/models/pda/consistency.py`. A PDA fit only ever answers "which
  parameters fit best", never "could this scheme have produced the histogram at
  all" — and χ²ᵣ cannot answer the second question either, because the 1D
  E-histogram bins are projections of a sparse S1S2 matrix and so are neither
  independent nor Gaussian. `kinetic_consistency_check` answers it by
  **parametric bootstrap**: `resample_s1s2` draws synthetic bursts from the
  *fitted* spectrum, each resample is scored with the same Poisson statistic the
  fit minimises, and the measured score is placed in that empirical
  distribution. The resulting p-value needs no distributional assumption because
  the reference distribution is simulated. On the dynamic model above: the
  correct scheme gives p = 0.46 (measured 78.7 against a resample median of
  76.7) and the static one p = 1/101, the bootstrap floor.
  Building the resampler pinned down a convention that is not obvious from the
  engine API: **`pF` is the *signal* photon-number distribution and background
  is added on top of it**, not carved out — the engine's mean burst size is
  `mean(pF) + background_ch1 + background_ch2`. Getting it backwards leaves a
  total-variation discrepancy of ~0.29 against the engine that no amount of
  sampling removes, so the test asserts `1/sqrt(n)` convergence rather than a
  single tolerance.

- **Fitted projection + counting statistic made explicit (2026-07-25).** The 1D
  residual hard-coded both halves of what it compares: it always projected onto the
  raw proximity ratio with 81 bins over [0,1] (each model's `kw_hist` — including
  the Gaussian model's log `S0/S1` range — was stored and then never read), and it
  always weighted by `1/sqrt(max(d,1))`, i.e. a Neyman chi-square. Both now live in
  `common.py::PdaFitSettings` on every PDA model and are edited from a new
  "Fit histogram / statistic" panel in all six `*.view.json`. The axis
  (`S1/(S0+S1)` / `E` / `S0/S1` / `R`) is built by one shared
  `build_pda_histogram_function`, which the distribution plot also uses, so the
  plotted and the fitted histogram can no longer diverge; corrected axes bin
  through gamma/R0 and are part of the data-histogram cache key. The statistic
  defaults to the **Poisson deviance** (`pda_weighted_residuals`), which matters
  because a PDA histogram is a projection of a sparse S1S2 matrix: over twenty
  Poisson realisations of an 800-count histogram the recovered Gaussian mean is
  biased by -0.02 A under the deviance versus +0.28 A under Neyman and -0.17 A
  under Pearson, against a 0.27 A per-fit scatter
  (`test/models/test_pda_statistics.py`, 25 tests).
- **Component groups render as modern paired tables (2026-07-25).** Every PDA
  `dynamic_group` now sets `"style": "table"`, so species / Gaussian components
  are one row each with their value, fix and bounds columns side by side (the
  layout the lifetime editor already used) rather than a spin-box grid.

- **The two-state occupation-time density is wrong away from equal populations
  (2026-07-25).** Found while building three-colour dynamics on the same law.
  `dynamic.py::two_state_time_fraction_pdf`, combined with the standard boundary
  masses, is not a probability distribution unless `x1 = 0.5`: the total reaches
  1.36 at `x1 = 0.2`, `K_ex = 8`, and its shape disagrees with a direct
  simulation of the telegraph process with a tilt that mirrors under
  `x1 -> 1 - x1`. Both errors vanish exactly at `x1 = 0.5` — which is very
  likely why it was not caught, since this PRD's own dynamic acceptance test
  recovered `x1 = 0.503`. **`PdaDynamicTwoStateModel` is therefore biased for
  unequal state populations**, and its reported `K_ex` at unequal occupancy
  should not be trusted until it is switched over.
  A correct replacement is available and verified:
  `two_state_occupation_quadrature` computes the law exactly from the
  Feynman–Kac characteristic function (no closed form required), agrees with
  simulation to a total variation of 0.002, gives `sum(w) = 1` and `E[f] = x1`
  to ~1e-5 for every population and exchange rate tested, and costs 0.11 ms.
  **Switched (2026-07-25, on request).** `PdaDynamicTwoStateModel` now
  integrates the exact law, and the broken density has been **deleted** rather
  than left available to be picked up again. `n_grid` went from 41 to 512: it is
  now the Fourier grid of the inversion, and the old value was sized for a direct
  density evaluation.

  **What the defect cost.** Fitting one synthetic dataset generated at
  `x1 = 0.25`, `K_ex = 2.0` *both ways*: the exact law recovers
  `x1 = 0.249`, `K_ex = 1.997`; the old closed form returns `x1 = 0.175` and
  `K_ex = 1.639` — the occupancy 30% low and the exchange rate 18% low. Any
  dynamic two-colour result at unequal occupancy should be re-run.
  `test_dynamic_pda_recovers_exchange_at_unequal_populations` now covers that
  regime, which the original acceptance test (at `x1 = 0.503`) could not.

- **Szabo–Gopich multistate dynamics (2026-07-25).** Beyond two states there is
  no closed occupation-time law, so `PdaDynamicThreeStateModel` had only
  Gillespie sampling — which makes the fit objective itself stochastic. New
  shared `chisurf/core/fluorescence/kinetics.py` implements Gopich & Szabo's
  route (JPC B 2010): the first two moments of the time-averaged observable are
  exact for any rate matrix via the spectral decomposition of the generator, and
  a bounded (beta) shape is matched to them. The model gains a `method` choice
  and defaults to the analytic route. A beta rather than the original's
  Gaussian because the observable is a probability that piles up against both
  ends in the slow limit, where a clipped Gaussian would distort exactly the
  comparison against a static fit.
  **Validity is measured:** total variation against exact sampling is
  0.19 / 0.11 / 0.010 / 0.0012 at `k·T` = 0.002 / 0.2 / 2 / 20 — ~1% from about
  two transitions per window upward, degrading as exchange slows because three
  separated states are trimodal and no two-parameter shape has three peaks.
  Inherent, and not a practical limit: slow exchange means resolved states,
  which a static multi-species fit describes exactly.
  A cross-check against the exact two-state law caught a transposition — the
  correlation function carries the equilibrium weight on the *initial* state and
  `exp(Qt)` is not symmetric, so the wrong placement understated the variance by
  26%; the three-state simulation check had passed with it.

- **One occupancy sampler, in the simulation engine (2026-07-25).** Where the
  moment match is not valid — slow exchange, where the distribution is multimodal
  and no two-parameter shape has three peaks — the answer is to sample the
  kinetics. That sampling now runs in the photon simulator rather than in a
  Python loop here: `tttrlib`'s `SimEngine` gained a **state-trajectory log**
  (one row per transition, plus births and deaths, so it is self-contained) and a
  `state_occupancy()` reducer, and
  `chisurf.core.fluorescence.kinetics.occupation_time_fractions` drives it —
  one immobile, dark molecule per observation window, started from the
  equilibrium populations, which is PAM's independent-window scheme. It replaces
  the Gillespie loop in `dynamic_mc.py` **and** the copy the c3PDA multistate path
  was using, and absorbs the duplicate `equilibrium_populations` that had grown in
  `dynamic_mc.py` alongside the one in `kinetics.py`.
  The Python loop survives as `occupation_time_fractions_reference`: the readable
  definition, the fallback for an engine that predates the state log, and the
  thing the engine is tested against (KS agreement at 1e2/1e3/1e4 Hz). The engine
  is 8x faster at 6 transitions per observation window, 13x at 60 and 11x at 600 —
  the regime where sampling is needed at all. The event log matters rather than
  the engine's existing strided reporter because a stride cannot represent a state
  entered and left between two samples, which is exactly fast exchange.

- **Time-binned dynamic PDA (2026-07-25).** The dynamic models carried a
  dimensionless `K_ex`, so a fit reported transitions-per-observation and nothing
  more. Three things changed.
  *The reader can cut fixed bins.* `PdaReader(segmentation="time-bins")` splits
  the whole stream into abutting windows of exactly the requested length
  (`time_binned_histograms`), instead of the burst search whose durations vary
  with the local flux — a dynamic model needs a known constant observation time,
  and a burst search only bounds it below. The payload gains `observation_time`
  and `segmentation`; a fixed-bin dataset's mean photon count is the count rate
  times the bin width, by construction.
  *The models read the observation time from the data.* Shared helper
  `common.pda_observation_time`, with `model.observation_time` and
  `model.transitions_per_window` on the two-state model. The three-state model's
  free-floating `T_win` **spinner is gone** — it was a setting that could silently
  disagree with how the data was segmented and rescale every rate.
  *The fitted parameter is a rate.* `k_ex` is now `k1 + k2` in Hz and the model
  forms `K = k_ex * T` itself, so a global fit over several bin widths shares one
  absolute rate.
  **What that buys is a test, not just a number.** A single histogram is fit by
  *some* `K` whether or not two-state exchange is right, so one time window cannot
  falsify a kinetic model. Measured on synthetic data: one rate across bin widths
  differing by 4x is recovered at chi2r < 1; windows generated from *different*
  rates each fit alone (chi2r 0.92 and 1.01) and are rejected jointly at
  chi2r ≈ 490. Covered by `test/models/test_pda_time_binned.py` (9 tests,
  including the degeneracy itself and the reader's binning), and the acceptance
  test now asserts `transitions_per_window` since that is what one dataset
  determines.

- **Both diagnostics are reachable from the editor (2026-07-25).** The kinetic
  consistency check and the light-path bridge were headless APIs with no way to
  reach them from a model editor. Both are now methods on a shared
  `common.Pda2cModelMixin` that all five PDA models (plus SAW-ν) inherit, so a
  `button_row` in each view spec is the entire user interface and the scripted and
  clicked paths are the same code.
  `run_consistency_check()` bootstraps from the fitted spectrum and reports the
  p-value and verdict; `get_pda_consistency` exposes `hist_measured` /
  `hist_expected` as a plot accessor and returns nothing before the check has run,
  so the panel is blank rather than misleading.
  `apply_light_path()` reads a light-path graph — or the plugin's last easy-mode
  session when the field is empty, which is what makes it one click — simulates it
  and maps the excitation/emission matrices onto the crosstalk terms. **Dye and
  detector labels come from the matrices**; anything other than two dyes and two
  detectors is refused *with its labels listed* rather than guessed at, because a
  wrong donor/acceptor assignment silently rescales every corrected quantity.
  Neither button can propagate an exception into the editor: every failure path
  lands in the status line instead.
  Two things the implementation had to get right and did not at first: an `info`
  section's `source` is **called**, so the status accessors are methods, not
  properties — as properties they rendered as two blank boxes, which is what the
  headless screenshot showed. And the light-path matrix payload keys are
  `rows`/`columns`, not the `row_labels`/`column_labels` of the builder's local
  variables. `test/models/test_pda_diagnostics.py` (18 tests) covers both actions
  on every model, including that each view spec's button actions and info sources
  name attributes that exist.
  Deliberate scope call: the hook takes a light-path **graph** rather than a
  handle on a live plugin widget. A model reaching into a running GUI instance is
  untestable headlessly and would put Qt in the Qt-free model layer; a graph path
  defaulting to the plugin's last session gives the same one-click result.

- **Arbitrary N-state schemes, and the rates are now actually fittable
  (2026-07-26).** Asked whether PDA could fit an arbitrary transition-rate
  matrix, the honest answer was no, and for a worse reason than a hardcoded state
  count: `PdaDynamicThreeStates` kept its six rate parameters in a **dict**, and
  `base.find_objects` recurses into lists only. None of them was ever discovered
  by `find_parameters`, so no rate was ever offered to the optimiser regardless of
  its `fixed` flag — the scheme was a set of constants that looked like
  parameters. `PdaDynamicNStates` replaces it: rates live in a list, `n_states` is
  settable (>= 2) and resizing preserves the rates that survive.
  Every off-diagonal `k_ij` is an ordinary fitting parameter, so topology is data
  rather than code — a linear chain is the fully-connected scheme with `k13`/`k31`
  at zero, and a linked pair imposes detailed balance. `rates_by_name()` is the
  scripting handle. The model gained delegating `n_states` / `rate_values` /
  `state_names` so the general `rate_matrix` AutoForm section (its first real
  consumer) renders an editable n×n grid with the diagonal disabled, above the
  parameter table that controls which entries are free.
  Renamed to `PdaDynamicNStateModel` ("PDA-dynamic-N-state"); registration, view
  spec, tests and docs follow.
  **Validated against the one case with an exact answer.** At N=2 the two-state
  occupation law is closed-form, so the general path can be checked against truth
  rather than against another approximation. Total variation, N-state route
  against the exact law:

  ======  =============  ==========  ===========
  K       szabo-gopich   sampled     atom mass
  ======  =============  ==========  ===========
  0.4     0.242          0.012       0.819
  1.6     0.121          0.017       0.450
  8       0.013          0.009       0.018
  40      0.001          0.003       0.000
  ======  =============  ==========  ===========

  The moment-match error tracks the **boundary-atom mass** almost exactly, which
  is the mechanism: a beta density cannot represent the point masses at f=0 and
  f=1 that a molecule which never switched sits on. So "use monte-carlo in slow
  exchange" stops being a rule of thumb and becomes a measured criterion — sample
  when molecules survive the window without switching.
  Also fixed the general rate-matrix widget's hard 78 px cell cap, which silently
  clipped any value wider than it: cells are now sized from the configured range
  and decimals. Found by rendering a 4-state scheme and reading the screenshot.

  The shared half of this lives in `chisurf/core/fitting/kinetics.py`
  (`RateMatrixMixin`, `RateMatrixParameters`) — a **general** facility, not a PDA
  one, since a rate scheme is the same object for burst likelihoods, lifetime-FCS
  and the acquisition simulator. See [PRD-65](prd-65.md) for the three-colour
  side and [subsystems/fitting.md](/subsystems/fitting.md) for the module.

- **The moment match was matched on the wrong support (2026-07-26).** Review
  finding RF-258, and it revises the bullet above: the slow-exchange error of the
  `szabo-gopich` route was **the support, not the boundary atoms**.
  `szabo_gopich_quadrature` matched its beta on `[0, 1]` — the interval a green
  probability is *defined* on — where a time average of a piecewise-constant
  observable is a convex combination of the state values and can only reach
  `[min(pG), max(pG)]`. Matched on that reachable interval instead (the new
  default; an explicit `lower`/`upper` still wins), the `concentration -> 0`
  limit *is* two atoms at the state values, i.e. the static mixture, and the same
  two moments give:

  ======  ==============  ==================  =======  =========
  K       beta on [0, 1]  beta on [min, max]  sampled  atom mass
  ======  ==============  ==================  =======  =========
  0.4     0.242           0.010               0.012    0.819
  1.6     0.121           0.022               0.017    0.450
  8       0.013           0.010               0.009    0.018
  40      0.001           0.000               0.003    0.000
  ======  ==============  ==================  =======  =========

  At `K = 0.4` the old route put **30 % of the weight outside `[0.35, 0.65]`**
  for two states at those values, including spikes at `pG = 0` and `pG = 1` — so
  the modelled S1S2 histogram carried donor-only-like and acceptor-only-like
  populations the scheme never contains. Two slow states are therefore now
  covered by the analytic route; the guidance to switch to `monte-carlo`
  survives for **three or more** resolved states, where the time average is
  genuinely trimodal (three-state total variation against sampling, after the
  fix: 0.138 / 0.110 / 0.016 / 0.003 at `k·T` = 0.004 / 0.4 / 4 / 40). Pinned by
  `test_szabo_gopich.py::test_the_quadrature_stays_on_the_support_the_states_can_reach`
  and `::test_slow_two_state_exchange_follows_the_exact_occupation_law`;
  `test_pda_time_binned.py`'s moment-match test now asserts the agreement it used
  to assert the absence of.

**Follow-ups (not yet done):**
- ~~c3PDA's rate matrix is a plain array attribute, not fitting parameters.~~
  Done — see [PRD-65](prd-65.md).
- Three-color c3PDA — **split out into [PRD-65](prd-65.md)**; it shares neither
  the engine (`tttrlib.Pda` is two-channel by construction) nor the data object
  (burst table, not S1S2 matrix) nor the fit objective (burst likelihood, not a
  histogram statistic) with this PRD.

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
4. ~~**Three-color c3PDA.**~~ Moved to [PRD-65](prd-65.md).
5. **Kinetic consistency check.** Resample burst data from a fitted kinetic scheme and
   compare to the measured histogram (the incumbent's "consistency check"); reuses the
   dynamic-PDA simulator. *(Done — `consistency.py`, parametric bootstrap p-value.)*

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
- c3PDA acceptance now lives in [PRD-65](prd-65.md).

# Non-goals

- No new bespoke Qt widgets (PRD-49 AutoForm mandate).
- Not reimplementing PDA histogram math outside `tttrlib`.
- Antibunching/nsFCS and FCCS models are PRD-54, not here.
- Three-color c3PDA is [PRD-65](prd-65.md), not here.

# Relationships
- Child of [PRD-49](prd-49.md) (Phase 1, first target).
- Wraps the `tttrlib.Pda` engine; consumes burst tables from the burst-selection pipeline.
- Renders via [GUI & AutoForm](/subsystems/gui-autoform.md); reads datasets through [Core target](/specs/core.md) rather than globals.
