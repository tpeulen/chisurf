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

## What is missing (later phases)

- **ndx toolbar push button** — the headless `push_calibration_to_ndx` is done and
  the parameter-link surface auto-wires; a one-click GUI action (mirroring the
  MMFDB toolbar in the ndxplorer plugin) to push the session calibration is the
  only remaining Qt convenience. Editor-tree sync inside the push is best-effort
  (derived columns already update via `ndx.constants`).
- **Multi-acceptor cross-leakage** — resolved: `corrected_es_general` un-mixes
  the emission crosstalk matrix (including acceptor↔acceptor bleed) as the first
  step of the correction. `corrected_es_matrix` remains the scalar fast path for
  the no-inter-acceptor-bleed case.

## Pointers

- Core: `chisurf/core/fluorescence/fret/calibration.py`,
  `chisurf/core/fluorescence/burst/es.py`,
  `chisurf/core/fluorescence/crosstalk.py`.
- Priors: `chisurf/core/fitting/priors.py`, `chisurf/core/fitting/fit.py`
  (`set_parameter_prior`, `_prior_residuals`, `lnprob`).
- Factor algebra reused from `chisurf/core/models/pda/nusiance.py::PdaFretNuisance`.
- Simulation: `chisurf/plugins/burst/burst_analysis/api/workflow.py`
  (`simulate`, `GroundTruth`, `select_bursts`).
- User-facing guide: `docs/FRET calibration.md` (in the Sphinx toctree); runnable
  notebook `chisurf/plugins/burst/burst_analysis/examples/FRET_Calibration.ipynb`.
