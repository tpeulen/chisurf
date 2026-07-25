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
  Qt-free `FittingParameterGroup` of bounded `FittingParameter`s in the
  **Hellenkamp 2018** nomenclature (`alpha` leakage α, `beta` excitation-flux
  ratio β, `gamma` detection/QY γ, `delta` direct excitation δ; backgrounds
  `Bg_dd`/`Bg_da`/`Bg_aa`, `R0`, `PhiA`/`PhiD`). Because they are ordinary fitting
  parameters, ChiSurf's priors machinery (`chisurf/core/fitting/priors.py`,
  `Fit.set_parameter_prior`, `_prior_residuals` for MAP and `lnprob` for MCMC)
  regularizes them automatically. Channels use the general numeric convention
  `I_ij` = emission of chromophore `j` under excitation of `i` (donor 1,
  acceptor 2, second acceptor 3, …) with friendly `i_dd`/`i_da`/`i_aa`
  (≡ `I_11`/`I_12`/`I_22`) aliases in the user-facing API.
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
- **General matrix correction (the non-special-case)** — the scalar
  `alpha`/`beta`/`gamma`/`delta` are only the *two-colour reduction*; the general
  problem is stated in terms of the light-path **excitation** (`X[l,k]`, laser→
  chromophore) and **emission** (`D[k,m]`, chromophore→detector) crosstalk
  matrices. `es.py::corrected_es_general(intensity, excitation, emission)`
  corrects straight from those two matrices in three steps: (1) un-mix emission
  `e[l,:] = I[l,:] @ D⁻¹` (removes *all* spectral crosstalk, including
  acceptor↔acceptor bleed, and folds `gamma` into the `D` diagonal so no explicit
  γ appears), (2) subtract direct excitation
  `F[l,k] = e[l,k] − (X[l,k]/X[k,k])·e[k,k]`, (3) coupled donor budget
  `E[l,k] = F[l,k] / (e[l,l] + Σ_a F[l,a])`. It reduces **algebraically** to
  `corrected_es` for the two-colour case (`D=[[1,α],[0,γ]]`, `X=[[1,δ],[0,1]]`)
  and recovers exact E for ≥3 chromophores with inter-acceptor leakage the scalar
  path cannot express. `calibration.py::crosstalk_matrices_from_lightpath` builds
  `X`,`D` (folding QY/detection efficiency into `D`) from a
  `get_crosstalk_matrices()` payload and `general_correction_from_lightpath`
  wraps the whole path. The emission un-mix (step 1) is selectable via
  `unmix="naive"` (fast vectorized pseudo-inverse; can return negative emissions
  and amplifies noise when `D` is ill-conditioned) vs `unmix="stable"`
  (**non-negative least squares** per burst — the physical `e≥0` constraint,
  robust to strong spectral overlap), plus an optional `ridge` (Tikhonov)
  damping; both share `crosstalk.invert_mixing(nonneg=…, ridge=…)`, which was
  extended with Tikhonov regularization (also serving the phasor-FLIM unmix).
- **Photon-statistics-preserving un-mixing (integer "shuffle")** —
  `crosstalk.photon_shuffle_unmix(counts, matrix, *, abundances=…, seed=…)`
  reassigns each detected photon to a source by a multinomial draw (`P(k|m) ∝
  a_k·B[k,m]`, `B` = row-normalised emission = spectral shape, `a_k` = NNLS
  abundance prior), yielding a non-negative **integer** per-source photon stream.
  It preserves the total photon count exactly, and because a multinomial thinning
  of a Poisson count is Poisson, it **preserves the shot-noise statistics** (for
  BVA / MLE / burst-variance downstream); its expectation equals the continuous
  Richardson–Lucy/EM unmix, so it is unbiased. Vectorised over bursts via a
  binomial chain. (`test_photon_shuffle.py`: integer + exact count preservation,
  identity-mixing lossless, mean == soft assignment, recovered stream is Poisson,
  seed-reproducible.)
- **ndxplorer stable/shuffle un-mixing injection** — ndx's native FRET pipeline is
  a scalar linear subtraction (string equations over columns, no matrix inverse /
  positivity); it has **no compute hook**, so
  `chisurf/plugins/ndxplorer/calibration_bridge.py::push_unmixed_columns_to_ndx`
  reads the measured per-channel photon-count columns from an open ndx window,
  un-mixes them (`unmix="stable"` NNLS default, or `"shuffle"` integer photons)
  with the light-path emission matrix, and injects the leakage-free per-source
  photon/rate columns back as **new** columns (ndx's native columns/equations
  untouched → no double-correction). Detector naming is **not hard-coded**: the
  caller supplies `emission`, `channel_columns` and `source_labels` (from the
  light-path calculator / `crosstalk_matrices_from_lightpath`), so it serves any
  N-colour setup. (`test_calibration_ndx_bridge.py`: stable injection with
  no-hardcoded-names, shuffle integer + total-count preservation, empty-when-absent.)
  **Headless real-engine coverage** — `test/fio/test_ndxplorer_unmix_headless.py`
  drives ndx's **actual** `DataSource` + real `mfd.equations.yaml`/
  `mfd.constants.json` (no Qt window, no display): it self-adds the in-tree
  `modules/ndxplorer` submodule to `sys.path`, forces `QT_QPA_PLATFORM=offscreen`,
  and `importorskip`s when absent. Asserts a pushed `gamma` genuinely changes the
  engine-computed `FRET efficiency` column, that injected unmixed columns are
  computable by ndx's own equation engine, and that the shuffle columns are
  integer + count-preserving through the real `DataSource`.
- **Per-pixel / FLIM imaging** — `chisurf/core/fluorescence/fret/pixel.py`:
  `corrected_es_image(intensity, excitation, emission, *, unmix, ridge, min_counts)`
  applies the general matrix correction to an `(n_laser, n_detector, H, W)` image
  tensor → per-pixel accurate FRET-efficiency maps, masking photon-starved pixels
  (`total < min_counts` → `NaN`); `pixel_source_photons(counts, emission, *,
  unmix="shuffle"|"stable", seed)` returns integer, Poisson-preserving (or NNLS)
  per-source photon images. Thin wrappers over the array-safe burst cores (which
  already broadcast over trailing axes). (`test_pixel_fret.py`: synthetic FLIM
  E-gradient recovered exactly, `min_counts` masks a starved border, stable
  un-mixing stays bounded on a noisy ill-conditioned image, shuffle per-pixel is
  integer + count-preserving.)
- **Scalar multi-chromophore (N-cube) correction** — `corrected_es_matrix(
  intensity, gamma, alpha, delta, ...)` generalises the three-cube to an N×N
  intensity matrix `I_ij` using the **coupled donor budget**
  `E_ij = (F_ij/γ_ij) / (F_ii + Σ_k F_ik/γ_ik)`, so each pairwise efficiency is
  recovered exactly when one donor is quenched by several acceptors (the naive
  pairwise formula would bias `E_ij → E_ij/(1−E_ik)`). Reduces exactly to
  `corrected_es` for two chromophores; when there is cross-leakage *between*
  acceptors use `corrected_es_general` (which un-mixes it) instead.
- **Layered calibration optimization** (`calibration.py`):
  - `global_es_correction(...)` — the data estimate of `gamma` from the E-S
    population linear fit `1/S = Ω + Σ·E` (Lee 2005 / Hellenkamp 2018;
    `gamma = (Ω−1)/(Ω+Σ−1)`), after leakage/direct-excitation correction.
  - `refine_calibration(...)` — the **posterior**: the precision-weighted
    (Bayesian) combination of that data estimate (uncertainty bootstrapped over
    bursts) and the light-path Gaussian prior. Strong data → posterior ≈ data;
    weak data → posterior ≈ prior.
  - `leakage_from_donor_only(...)` (α) and
    `direct_excitation_from_acceptor_only(...)` (δ) — the standard reference-sample
    estimators; `calibrate_from_samples(...)` orchestrates the full data-driven
    procedure (α from donor-only, δ from acceptor-only, γ/β from the FRET E-S fit,
    optional prior-regularized refine). Verified to recover known α/δ/γ.
- **Simulated ground truth** — `BurstWorkflow.simulate(..., gamma=…)` bakes a
  known detection factor into the tttrlib photon simulation (red-channel
  brightness scaled by `gamma`), recorded on `GroundTruth.gamma`, so calibration
  recovery is validated end-to-end (simulate → burst-select → correct → recover E).
- **Session-shared calibration for global analysis** —
  `CalibrationFit` + `register_calibration`/`unregister_calibration` expose the
  group as a dataset-free pseudo-fit in `cs.fits`, so it **already appears in the
  parameter-link UI** (verified: `ChiSurfAPI.list_fits()` serializes it with its
  factors — the same source the link menu reads, no extra GUI code) and any fit's
  correction parameter can `link_to_calibration` (chinet-port identity). Refining
  one calibration then updates every linked fit — calibration-shared global
  analysis.
- **ndxplorer bridge** — `calibration_to_ndx_constants` maps the posterior
  factors onto ndx's MFD constants (inverting ndx's effective
  `gamma = (PhiA/PhiD)/(gG/gR)`), and
  `chisurf/plugins/ndxplorer/calibration_bridge.py::push_calibration_to_ndx`
  writes them into an in-process ndxplorer window and recomputes, so ndx's
  derived FRET uses the data-optimized calibration.
- Tests: `test/fitting/test_fret_calibration.py` (unit), `test_calibration_shared.py`
  (pseudo-fit registration + linking), `test_calibration_ndx_bridge.py` (mapping +
  push), `test_multi_chromophore.py` (scalar N-cube), `test_general_correction.py`
  (general matrix form: 2-colour reduction, 3-colour with inter-acceptor bleed,
  light-path-payload path, naive-vs-stable un-mixing under ill-conditioning +
  ridge), `test_crosstalk.py`, and
  `test/plugins/burst/test_calibration_simulation.py`
  (end-to-end on simulated bursts). Example notebook:
  `chisurf/plugins/burst/burst_analysis/examples/FRET_Calibration.ipynb`.

- **Accurate FRET with error bars, and automatic factors** —
  `chisurf/core/fluorescence/fret/accurate.py` closes the loop from "apply the
  factors" to "find the factors":
  - `classify_es_populations` fits a **Gaussian mixture** (dependency-free 1-D EM,
    `gaussian_mixture_1d`, BIC-selected) to the stoichiometry and assigns each
    *component* to donor-only / acceptor-only / FRET by its centre, placing the
    cuts where neighbouring components meet — no hand-drawn gates;
    `split_fret_subpopulations` does the same over the efficiency, which is what
    makes `gamma` identifiable from one measurement.
  - `auto_calibrate(...)` iterates classification → `alpha` (donor-only) →
    `delta` (acceptor-only) → `gamma`/`beta` (E-S fit) to self-consistency
    (the gates depend on the factors and vice versa; 2–3 passes in practice),
    bootstraps a σ per factor with the split held fixed, and returns an
    `AutoCalibration` with a printable `report()` naming the route each factor
    came from.
  - **The optics are the prior for every factor, not just gamma.**
    `_combine_with_optics_priors` precision-weights `gamma`, `alpha` *and*
    `delta` against the light-path priors (`lightpath=` seeds them via
    `set_priors_from_lightpath`), and reports the posterior σ. A factor the data
    cannot identify (no donor-only bursts) falls back to the optical value **with
    the optical uncertainty** instead of to a fitted illusion.
  - `beta_from_stoichiometry` is the documented single-population fallback
    (centre a 1:1 species at `S = 0.5`); it never touches `E`.
  - `accurate_fret(...)` returns per-burst E/S/distance plus propagated errors
    (`efficiency_uncertainty`: `∂E/∂γ = −E(1−E)/γ`, `∂E/∂α = −(1−E)²/γ`,
    `∂E/∂δ = −(1−E)²·F_AA/(γ·F_DD)` — the δ term was derived wrong first and is
    pinned by a finite-difference test; `distance_from_efficiency`:
    `σ_R/R = √((σ_R0/R0)² + (σ_E/(6E(1−E)))²)`).
- **Analytic FRET lines (the lifetime route)** —
  `chisurf/core/fluorescence/fret/lines.py` is a model-free, Qt-free generator of
  the E–τ lines: `static_fret_line` (Gaussian linker distribution swept over the
  mean distance), `dynamic_fret_line` (two-state fast exchange), `no_linker_line`
  (the `E = 1 − τ/τ_D0` diagonal), each a `FretLine` with `efficiency_at`,
  `lifetime_at`, `deviation` and the shared `as_overlay()` contract. It agrees
  with the model-driven `fret_line.py` generator to |ΔE| < 0.002 **at matched
  τ_f** (`test/models/test_fret_lines_analytic.py`) — compare at matched lifetime,
  not matched mean distance, because the model discretizes P(R) on its own
  logarithmic axis. `gamma_from_lifetime(...)` reads the line backwards
  (`γ = (F_DA/F_DD)·(1−E_line)/E_line`), which identifies `gamma` from a **single**
  population and **without ALEX**; populations outside `efficiency_window`
  (default 0.05…0.95) are refused because the line is flat there. Same comparison
  after calibration = the sub-burst-dynamics test.
- **`accurate_fret` plugin** (`chisurf/plugins/burst/accurate_fret/`) — AutoForm
  tool (`accurate_fret.view.json` + `AccurateFretViewModel`) over the core:
  reads a burst table (delimited text/`.npz`, columns auto-mapped from the
  ndX/`.bur`/API naming conventions via `COLUMN_HINTS`) **or the live columns of
  an open ndXplorer window**, shows the factor/population tables and the E-S and
  E-τ scatter plots with the static and dynamic lines, and can share the
  calibration in the session (`register_calibration`) or push it to ndX. Headless
  `csc accurate-fret`, RPC `accurate_fret.calibrate{,_file}`. Light paths saved by
  the light-path simulator are listed as prior sources (`lightpath_prior` reads
  their stored `crosstalk_matrices` artifact).
- **Calibrating from inside ndX (the end of the workflow)** —
  `calibration_bridge.optimize_calibration_from_ndx(ndx)` is the one call that
  turns "ndX has a measurement open" into "ndX's constants follow from that
  measurement": it reads the burst columns out of the window, **seeds a
  `CalibrationParameters` from the window's own constants**
  (`calibration_from_ndx_constants`, the new inverse of
  `calibration_to_ndx_constants`, so backgrounds / QYs / R0 / `tauD0` stay the
  user's), runs `auto_calibrate`, pushes the posterior back and recomputes.
  Exposed as a **🎯 Optimize FRET calibration** toolbar action added to the ndX
  window by the ndxplorer plugin. It also injects the accurate per-burst columns
  (`FRET efficiency (accurate)`, `Stoichiometry (accurate)`, `R_DA (accurate)`,
  `Off static FRET line`, `Population`) — **not redundant**: ndX's own efficiency
  equation has *no direct-excitation term* (`Fr = Sr − Br − alpha·Sg`), so pushed
  constants alone cannot make its native column accurate. `refresh_column_selectors`
  makes injected columns appear in ndX's axis pickers (they were plottable only
  after a reload before). **Naming**: ndX's `beta` is δ and its `r` is `1/beta`
  (the `r` mapping was missing and is now written too). Covered by
  `test_calibration_ndx_bridge.py` (stub) and `test_ndxplorer_unmix_headless.py`
  (ndX's **real** DataSource + real equation/constant files: the factors are
  recovered from simulated bursts and ndX's own `FRET efficiency` column changes).
- **Shared burst-table conventions** — `chisurf/core/fluorescence/burst/table.py`
  (`COLUMN_HINTS`, `guess_columns`, `read_burst_table`, `columns_from_data`) is
  the single source of truth for which column is which channel (ndX / `.bur` /
  API spellings); the plugin and the ndX bridge both use it instead of guessing
  separately.
- **ndX window locator** — `calibration_bridge.find_ndx_windows()` finds the
  in-process ndXplorer windows among the top-level Qt widgets (empty head-less),
  which is what the tool's push/pull buttons use.
- **AutoForm plot ranges** — `PlotSection` gained `x_range`/`y_range`; without
  them one acceptor-only burst (no donor signal → unbounded "efficiency") squeezes
  an entire E-S plot into a pixel column.

## What is missing (later phases)

- **ndx toolbar push button** — resolved twice over: the `accurate_fret` tool's
  *📤 To ndXplorer* action, and ndX's own *🎯 Optimize FRET calibration* toolbar
  button (`optimize_calibration_from_ndx`). Editor-tree sync inside the push stays
  best-effort (derived columns already update via `ndx.constants`).
- **Multi-acceptor cross-leakage** — resolved: `corrected_es_general` un-mixes
  the emission crosstalk matrix (including acceptor↔acceptor bleed) as the first
  step of the correction. `corrected_es_matrix` remains the scalar fast path for
  the no-inter-acceptor-bleed case.

## Pointers

- Core: `chisurf/core/fluorescence/fret/accurate.py` (automatic factors,
  uncertainties), `chisurf/core/fluorescence/fret/lines.py` (analytic E–τ lines),
  `chisurf/core/fluorescence/fret/calibration.py`,
  `chisurf/core/fluorescence/burst/es.py`,
  `chisurf/core/fluorescence/crosstalk.py`.
- Priors: `chisurf/core/fitting/priors.py`, `chisurf/core/fitting/fit.py`
  (`set_parameter_prior`, `_prior_residuals`, `lnprob`).
- Factor algebra reused from `chisurf/core/models/pda/nusiance.py::PdaFretNuisance`.
- Simulation: `chisurf/plugins/burst/burst_analysis/api/workflow.py`
  (`simulate`, `GroundTruth`, `select_bursts`).
- Plugin: `chisurf/plugins/burst/accurate_fret/` (GUI + CLI + RPC).
- User-facing: theory in `docs/concepts/accurate_fret.md`, workflow in
  `docs/guides/41_accurate_fret.md`, API how-to in
  `docs/guides/fret_calibration.md`; runnable notebook
  `chisurf/plugins/burst/burst_analysis/examples/FRET_Calibration.ipynb`.
