---
type: Subsystem
title: Fitting Engine
description: Binds models to datasets over a range, computes weighted residuals and chi², and drives local/global least-squares optimization plus error analysis and sampling.
resource: chisurf/core/fitting/
tags: [core, fitting, optimization, global-analysis]
timestamp: '2026-07-05T00:00:00Z'
---

# What a Fit is

A `Fit` (`chisurf/core/fitting/fit.py`) pairs one `DataCurve` with one
`ModelCurve` and restricts the comparison to an index range `[xmin, xmax]`
(optionally narrowed by an arbitrary 1D `mask`/weight array). See
[data model](/subsystems/data-model.md), [models](/subsystems/models.md),
and [parameters](/subsystems/parameters.md).

| Object | Role |
| --- | --- |
| `Fit` | Single dataset ↔ single model over a range |
| `FitGroup(Fit)` | Many `Fit`s sharing a global model (`GlobalFitModel`) |
| `FittingParameter` | Free/fixed/linked model parameter (`fitting/parameter.py`) |
| `sample_fit` / `sample.py` | MCMC / emcee parameter sampling |
| `support_plane.py` | chi² scans + F-test confidence intervals |
| `factorgraph.py` | posterior factor structure: relevance, blocks, treewidth |

# Fitting flow

1. Evaluate model → `model.update_model()` produces model y-values.
2. Weighted residuals `wres = (data − model) / data_error` over the range
   (`calculate_weighted_residuals` in `fitting/__init__.py`; masked via
   `_apply_fit_mask`).
3. `chi2 = Σ wres²`; `chi2r = chi2 / (n_points − n_free − 1)` (`get_chi2`).
4. `Fit.run()` minimizes `get_wres` with `leastsqbound`
   (`chisurf/core/math/optimization/leastsqbound.py`) over the model's free
   parameters and their bounds, then updates error estimates and pushes model
   state onto a bounded `results` deque.

`leastsqbound` wraps `scipy.optimize` MINPACK `leastsq` (Levenberg–Marquardt),
adding box bounds via an internal↔external parameter transform and a
cancellable `progress_callback` (`OptimizationCancelled`).

# Noise model / estimator (`noise_model`)

Each `Fit` carries a `noise_model` selector controlling the objective:

- `"default"` — weighted least squares: `wres = (data − model) / data_error`.
  For photon-counting data whose error column is `sqrt(counts)` this is the
  Neyman chi², biased low at low counts.
- `"poisson"` (aliases `mle`, `2istar`) — Poisson maximum likelihood. The
  residuals become the **signed deviance residuals**
  `r_i = sign(μ−y)·sqrt(2·(μ − y + y·ln(y/μ)))`
  (`deviance_residuals` in `fitting/__init__.py`). Because `Σ r_i² = 2I*`
  (the Baker–Cousins / Maus `2I*` likelihood-ratio statistic), the *same*
  `leastsqbound` LM engine, `chi2`/`chi2r`, Jacobian covariance, F-test and
  residual plots all work unchanged — only the per-bin residual definition
  differs (Laurence & Chromy, *Nat. Methods* 2010). This is the correct
  estimator for low photon counts (TCSPC, FLIM, burst decays).

The selector is threaded `Fit.noise_model → Model.get_wres →
calculate_weighted_residuals(..., noise_model=…)`. Default preserves the
historical WLS behaviour exactly.

# Parameter priors (MAP + Bayesian)

Any free parameter may carry a **prior** (`chisurf/core/fitting/priors.py`),
generalising the fit from least squares to maximum-a-posteriori (MAP) and
proper Bayesian sampling. **Bounds are the degenerate uniform prior**: the box
constraint `lb ≤ θ ≤ ub` is a `UniformPrior` whose `support()` drives the
optimiser's hard bounds, so a hard bound and a soft prior are one concept
(`Parameter.prior`, see [parameters](/subsystems/parameters.md)).

- **Least squares → MAP.** `_prior_residuals` (in `fit.py`) appends each free
  parameter's `prior.residuals(value)` to the data-residual vector when
  `get_wres(..., include_priors=True)`. For a Gaussian prior this is the
  Tikhonov/ridge residual `(θ−μ)/σ`; the general case is a signed deviance
  `sign(θ−mode)·sqrt(−2·Δlnpdf)` — the same reduction used for the Poisson
  `2I*` residuals, so the LM engine minimises `χ² − 2·ln p(θ)` unchanged.
  `Fit.run`/`FitGroup.run` pass `include_priors=True`; `get_chi2` stays
  data-only so reported χ² remains the data misfit.
- **MCMC.** `lnprior` sums `prior.lnpdf` over the free parameters;
  `lnprob = lnprior − 0.5·chi2`. Its `bounds` argument is an *additional* cheap
  box rejection checked before any model evaluation, **not** a replacement for
  the priors — it used to short-circuit, which silently dropped every
  informative prior from the sampled posterior while MAP still honoured it
  ([PRD-68](/prds/prd-68.md)). `_smooth_prior` is the shared "more than a
  bound?" test that lets both the MAP and MCMC hot paths skip parameters
  carrying only a box.
- **Likelihood and prior stay separable.** `lnprob_parts` returns
  `(lnlike, lnprior, chi2)`; `walk_mcmc` and `sample_emcee` (via emcee blobs)
  record them apart, so a chain's `chi2r` is the data misfit alone and the
  stored posterior can be reweighted under a different prior without
  resampling. Chain files carry `chi2r`, `lnprior`, then the parameters.
- **Families.** `UniformPrior` (bounds), `NormalPrior`, `TruncatedNormalPrior`,
  `HalfNormalPrior`, `LogNormalPrior`, `ExponentialPrior`, `GammaPrior`,
  `BetaPrior`, plus `CallablePrior` — the most general form wrapping any
  `logpdf(x)` callback (runtime-only, not persisted). `as_prior` coerces a
  Prior / callable / state dict.
- **Combination / conjugacy.** `Prior.combine` (`*`) merges two priors: closed
  form for same-family conjugates (`Normal×Normal` precision-weighted,
  `Gamma×Gamma`, `Beta×Beta`, `Normal×Uniform → TruncatedNormal`) and a generic
  `ProductPrior` (summed log-densities, concatenated residuals) otherwise.

Distribution priors persist as a JSON spec on the parameter's `chinet.Port`
(`port.prior`); the GUI edits them through the per-parameter prior selector and
the `parameter.set_prior` RPC (see [parameters](/subsystems/parameters.md)). A
model author can also **declare default priors in a `.view.json`**: a
`parameter_group` section's `priors` map (parameter-name → prior-state dict) is
applied to the `FittingParameter`s when the AutoForm renderer builds the section
(`ParameterGroupSection.priors` in `chisurf/core/dataspec/`, applied by
`AutoModelWidget._apply_section_priors`); the single-parameter `fitting_parameter`
custom section accepts a `prior` option the same way. See the
[AutoForm subsystem](/subsystems/gui-autoform.md).

**Reporting.** `Fit.prior_summary()` lists each parameter's prior and whether it
is *informative* — a `UniformPrior` only restates the bounds and contributes
nothing to the objective. `Fit.posterior_summary()` gives each free parameter's
interval, preferring a chi² scan's (possibly asymmetric) profile crossings over
the covariance matrix's symmetric `value ± error` Laplace approximation, and
labels which one a row carries. `Fit.__str__` renders both, so they appear in the
fit-info panel; the heading says *posterior (MAP)* only when an informative prior
is attached, since with bounds alone the interval is an ordinary confidence
interval rather than a credible one.

The dedicated single-molecule / image MLE path (tttrlib `fit2x`:
`Fit23`/`Fit24`/`Fit25`) is wrapped by the Qt-free harness
`chisurf/core/fluorescence/mle/` (`Fit2x`, `Fit2xSettings`, `Fit2xResult`,
`assemble_vv_vh`), the single seam consumed by the burst-MLE and image-MLE
plugins in place of duplicated raw-tttrlib boilerplate.

# Global analysis / parameter linking

- `FittingParameter.link` ties a parameter to another parameter (across fits);
  linked and `fixed` params are excluded from the free set (`n_free`), so a
  linked param is optimized once but shared everywhere.
- `FitGroup` builds a `GlobalFitModel`
  (`chisurf/core/models/global_model/globalfit.py`) whose
  `weighted_residuals` is the `np.concatenate` of member residuals and whose
  `parameters` is the deduplicated union of member free params — one global
  least-squares problem.
- `FitGroup.run()` optionally fits each member locally first
  (`global_optimize_local_first`) then runs the joint `leastsqbound`.
- **`FitGroup.model` is the *selected member's* model; the global one is
  `FitGroup._model`.** Anything reasoning about the joint parameter vector must
  use `_model` (or `factorgraph.posterior_model`) — reaching for `.model`
  silently describes one dataset instead of the group.

# Posterior structure — the fit factor graph

`chisurf/core/fitting/factorgraph.py` makes the factorisation
`p(θ|D) ∝ ∏ₖ Lₖ(θ_Sₖ) · ∏ᵢ πᵢ(θᵢ)` explicit ([PRD-68](/prds/prd-68.md)).
Variables are the free parameters of the global parameter vector (indexed by
their position in it); factors are one likelihood per local fit plus one per
informative prior. A likelihood factor's scope is that fit's non-fixed
parameters resolved through their `link` chains (`resolve_root`), so linking is
what couples datasets in the graph. A bare box bound adds no factor — it is a
support constraint, not a coupling.

| Query | Answers |
| --- | --- |
| `affected_fits(keys)` | which local models a change must recompute |
| `connected_components()` | independent sub-problems |
| `cliques()` / `blocks()` | variables that must move jointly |
| `junction_tree()` / `separators()` | the parameters the datasets actually share |
| `treewidth` | structural difficulty; a star-shaped global fit stays small |
| `describe()` | the identifiability report, via `GlobalFitModel.structure_report()` |

Cliques come from a greedy `min_fill` (or `min_degree`) elimination order; the
clique tree is the maximum-weight spanning tree over shared-variable counts.
Only `numpy` and `networkx` are involved.

**Selective updates.** `GlobalFitModel.update_model` recomputes only the local
models a change reached. The dirty set is armed *solely* by the
`parameter_values` setter — the one moment the model knows exactly what moved —
and consumed by the very next `update_model`; anything else (a GUI edit of a
single value, a second update, a structure change) recomputes everything. A
`_current_at_version` stamp additionally forbids skipping until every local
model has been evaluated at least once since the last structural change, since
skipping past a never-evaluated model would leave stale residuals in the
objective. `optimization.global_structure_aware_update` is the escape hatch for
a custom global model whose datasets are coupled by something other than links;
`FactorGraph.unexplained_variables()` already forces the conservative path for
any free parameter the graph cannot connect to data.

`factorgraph.STRUCTURE_VERSION` invalidates cached graphs; it is bumped by
`Parameter.link`, `Parameter.fixed`, `FittingParameterGroup.find_parameters` and
the `GlobalFitModel` membership mutators.

# Posterior sampling and its diagnostics

`chisurf/core/fitting/diagnostics.py` ([PRD-69](/prds/prd-69.md)) supplies the
evidence a chain needs to be believed: FFT autocovariance, Stan-style multi-chain
ESS (Geyer initial-positive-sequence truncation), integrated autocorrelation
time, split Gelman–Rubin, Monte-Carlo standard error, a `2·τ` burn-in
suggestion, a per-parameter `summarize` and `convergence_warnings`. Pinned
against AR(1), whose `τ = (1+φ)/(1−φ)` is closed-form. Thresholds:
`RHAT_THRESHOLD = 1.01`, `ESS_THRESHOLD = 400`.

- All samplers return `chains` (per-chain, not only flattened) and
  `acceptance_rate`. `sample_fit` pools the `n_runs` **independent** runs, writes
  `diagnostics.json` beside `chains/`, logs the warnings and returns the report.
  Chain files keep every draw — the burn-in is reported, not applied to the data.
- An ensemble sampler's walkers are not independent chains, so a cross-walker
  R̂ is optimistic; the decisive one is cross-run.
- `Fit.posterior_summary` gained an `mcmc` method that outranks `profile` and
  `laplace`. A chain failing its own checks is **omitted**, not quoted.

| `method` | Proposal | ESS / 1000 evaluations, collinear posterior |
| --- | --- | --- |
| `mcmc` (`walk_mcmc`) | diagonal | 0.4 |
| `emcee` (`sample_emcee`) | affine-invariant ensemble | 26 |
| `blocked` (`walk_mcmc_blocked`) | per-block covariance | **64** |

`walk_mcmc_blocked` seeds each block's proposal covariance from
`Fit.covariance_matrix` (the curvature at the optimum — previously computed for
error bars and never used by the sampler), refines it from the empirical
covariance during warm-up, then **freezes** it so the recorded chain stays
time-homogeneous. Blocks come from `FactorGraph.sampling_blocks()`: variables
grouped by identical likelihood-factor neighbourhood — a true partition, cheapest
block first, degenerating to one block for a single `Fit`.

**Independent components are sampled apart and merged exactly.**
`sample_independent_components` (what `method='blocked'` routes through) checks
`FactorGraph.connected_components()`. Components share no factor, so the
posterior factorises exactly and each is sampled on its own from a common
reference state — the others' datasets then contribute a constant that cancels
in the Metropolis ratio. The merge needs no extra model evaluation:

- draws are shuffled independently per component before being stacked (without
  the shuffle, chain ordering shows up as a correlation the posterior lacks);
- `χ²(θ) = Σ_c χ²_run,c − (C−1)·χ²₀` and the same identity for the log-prior,
  since both are sums over datasets / parameters and the runs share `θ⁰`.

Measured on 8 unlinked datasets (16 parameters): 72.6 vs 5.6 effective samples
per 1000 model evaluations — 7.8× the ESS for 40% fewer evaluations. A group
whose datasets share a parameter is one component and falls back to a single
joint chain.

# One query API over the estimators

`chisurf/core/fitting/engine.py` ([PRD-70](/prds/prd-70.md)) puts the covariance,
the profile scan and the sampled posterior behind one protocol, so the estimator
is a choice of engine rather than different code at every call site.

| Call | Meaning |
| --- | --- |
| `condition(name, value)` | fix a parameter and re-optimise the rest — what a profile scan *is* |
| `add_target` / `add_joint_target` | declare what to compute; nothing else is |
| `run(**options)` | do the work |
| `marginal` / `joint` / `log_evidence` | read the answer |

Engines: `LaplaceEngine` (covariance at the optimum, always available, reports a
Laplace `log_evidence`), `ProfileEngine` (asymmetric intervals, one parameter at
a time, no joint and no evidence — it maximises rather than integrates),
`SamplingEngine` (the only real joint answers; **refuses** to return a marginal
from a chain that failed its own checks), `StoredEngine` (reports what has
already been computed, computing nothing — `Fit.posterior_summary` is a loop
over it), and `AutoEngine` (best available per parameter, still labelled).

Answers are `Marginal` / `Joint` dataclasses carrying the `method` that produced
them, so a report or a plot consumes one without knowing its origin.
`Joint.correlation` is what a global fit is usually really after: a pair at ±1 is
one measurement, not two.

**Reachable, not just importable.** `ChiSurfAPI.posterior(...)` and the
`fit.posterior` RPC (`fits.fit_posterior`) expose the whole query vocabulary --
`engine`, `targets`, `joint`, `condition`, `p_value`, `global_posterior` --
returning a JSON-safe payload. `stored`/`laplace` are immediate; `profile` and
`mcmc` block, so the existing `fit.sample.*` / `fit.parameter_scan.*` job
endpoints remain for polled progress.

**`condition` re-optimises.** Pinning a value and leaving the rest alone would
return the unconditioned answer with one parameter overwritten. The remaining
parameters are re-fitted given the conditioned value -- which is what a profile
scan does at each of its points -- and a conditioned parameter leaves the free
vector entirely, so it correctly has no marginal of its own.

`ProfileEngine` routes each scan to the *member* that owns the parameter — group
names are prefixed (`3:tau`) and a member only knows its own. `approx_grad`,
`covariance_matrix`, `lnprior`/`lnprob`/`lnprob_parts` and every sampler take an
optional `model=`, so an engine over a group's global model works throughout.

# Cost of an objective evaluation

Profiling a global-fit sweep found the model evaluation itself was **6 %** of
the time; the rest was Python overhead re-deriving things that cannot change
during a run. 2000 evaluations over 12 datasets went **1.46 s → 0.45 s (3.2×)** and
3.84 M → 0.95 M calls, after which the model evaluation is the top cost. A
two-exponential TCSPC fit runs in ~37 ms.

- **Frozen parameter flags.** Reading a parameter costs six property dispatches
  -- three at the `Parameter` level, three more into the port -- purely to decide
  *how* to read it (linked? callable? bounded?), and none of those answers can
  change during a run either. The freeze stamps them, so a read is one dict
  lookup and one port access: a further **1.36×** on decay model evaluations,
  with byte-identical residuals. Together with the value cache below this is
  **1.46-1.49x** on a decay evaluation. It matters because `Parameter.value`
  costs roughly ten times what the C++ convolution does in a 1024-channel decay
  -- see the [autodiff assessment](/references/autodiff-assessment.md).
- **`factorgraph.frozen_structure(...)`** — nothing about a fit's structure
  changes while it is optimised or sampled, so the free-parameter list, names,
  bounds and `n_free` are resolved once per run and served with no version check
  and no per-access allocation. Re-entrant (a sampler calling a sampler does not
  release the outer freeze) and self-checking: the structural and window
  counters are compared on exit and a violation is logged. Applied by `Fit.run`,
  `FitGroup.run` and every sampler (via the `@frozen` decorator).
- **Cached free-parameter lists** for the unfrozen path, keyed on
  `structure_version()`. Deciding freedom costs three attribute reads per
  parameter, two crossing into the chinet port; this was the single largest cost
  of a run. `redundant` became a property so it bumps the counter like `fixed`
  and `link` (backed by its public dict key, so the serialised form is
  unchanged).
- **`window_version()`** — a second counter bumped by the `xmin`/`xmax`/
  `fit_range`/`mask` setters. `n_points` and the residual cache key on it
  instead of reading every member's window back twice per evaluation.
- **Per-member residual cache** in `GlobalFitModel.weighted_residuals`, invalidated
  by exactly the members `update_model` recomputed. Selective updating was
  otherwise half an optimisation: the models were skipped but their residuals
  were recomputed anyway (24 000 → 7 054 calls).
- **`parameter_values` setter** skips writing a value a parameter already has,
  and `Parameter.value` tests the float compare before the port read.
- **Frozen parameter values.** Most of a model's parameters -- instrument
  response, detection geometry, background, everything not being optimised --
  hold the same value for a whole run and are re-read on every evaluation. Inside
  a freeze a read is memoised on the parameter and dropped by the value setter,
  which is the *single* point at which a value changes: models write through
  `Parameter.value`, never into the backing port, and there are no computed
  (chinet-node) ports in these models. Linked parameters are never cached -- a
  follower is written through its *port* when its master moves, which never
  reaches the follower object.
- **`Base.__setattr__` and `ParameterGroup.__setattr__`** memoise their class
  property lookup per `(class, attribute)`. Both ran on every attribute write,
  and for a key that is not a class attribute -- ordinary instance state, most
  writes -- `getattr` walked the whole MRO before failing.

**The verdict reaches the caller.** `fit.sample.start` merges its keyword
arguments over `optimization.sampling` (so `method` and `global_posterior` are
per-job selectable) and keeps the report `sample_fit` returns;
`fit.sample.status` exposes `converged`, `warnings` and the full `diagnostics`
alongside `status`/`progress`. The server used to discard the return value, so a
chain that never left its start reported `completed` exactly like one that
explored the posterior. The GUI forwards the configured method (it previously
assembled the settings and dropped them) and polls the job, logging the verdict.
Default backend is now `blocked`.

**Linking lowers the dimension and makes sampling harder.** Measured on six
datasets, linking one parameter took the dimension 12 → 7 and cost ~50× in ESS
per model evaluation (τ of the shared parameter 1 → 20). Dimension is the wrong
difficulty measure; coupling is. `sample_marginal_shared` (`method='collapsed'`)
integrates each dataset's *private* parameters out by Laplace at fixed shared
values — exact when they enter linearly, which covers amplitudes, offsets and
scatter fractions — and samples the separator only, drawing the privates
conditionally so the output is still a full joint sample.

The profile must be restricted to each local model's *private positions*: a link
master lives on one dataset, so optimising that model's whole free list would
re-optimise the shared parameter and flatten the target. With three private
parameters per dataset (25 dims): `collapsed` τ(shared) 4.9 / minESS 411 /
1.154 ESS per 1000 evals against `blocked` 589 / 3.4 / 0.045 — 26×, and
`blocked` there reported an error bar 5.6× too small. With a *single* private
parameter it is roughly a wash (3–4× the ESS per draw, ~3.5× the evaluations).

**Sampling a group samples one member.** `lnprior`/`lnprob`/`lnprob_parts`,
`walk_mcmc_blocked` and `sample_independent_components` take an optional
`model=`; without it they use `fit.model`, which for a `FitGroup` is the
*selected member's* model. `sample_fit(..., global_posterior=True)` (requires
`method='blocked'`) targets `factorgraph.posterior_model(fit)` instead; the
reported names are then the prefixed group ones.

# Fitting a bare array through the real models

`chisurf/core/fluorescence/decay_fit_model.py` builds a runnable `Fit` +
`LifetimeModel` from a plain numpy decay, bin width and IRF
(`build_lifetime_fit`), and runs it (`fit_lifetime_model`). It exists so callers
that only hold an array — plugins, the FCS Filter Calculator's auto-fit, scripts
— get `FittingParameter`s that can be **linked to other fits**, rather than the
plain floats a standalone optimiser returns. It is Qt-free.

Making a `LifetimeModel` compute from an in-memory array requires several
settings that **fail silently**, returning a flat background instead of a decay:
`convolve.stop` is in *time* units and defaults to 0 (no convolution);
`convolve.dt` defaults to 1.0; the IRF must be in *counts* because
`_process_irf` subtracts `lamp_background` and clips at zero; `_irf_start`/
`_irf_stop` must be written on the backing parameters (the public setters wrap
the value in `np.array` and are broken); autoscaling is enabled by *fixing*
`n0`; and lifetime bounds are off by default. `build_lifetime_fit` centralises
all of it.

`build_fret_fit` / `fit_fret_model` do the same for FRET, driving a
`GaussianModel`: each state is a Gaussian donor–acceptor distance with fitted
mean/width/fraction plus the donor-only fraction `xDOnly`, and efficiencies
follow from the fitted distances and R₀. **R₀ and τ_D0 are held fixed** —
calibration, not data, and badly conditioned against a distance distribution
because R₀ and R trade off through the same `(R/R₀)⁶`.

**Amplitude conventions differ between the two fitters and are not
interchangeable.** `decay_fit.fit_lifetime_components` builds its design matrix
from unit-sum decay columns, so its amplitudes are **photon fractions**;
`Lifetime.amplitudes` are **pre-exponential** amplitudes, the
`lifetime_spectrum` convention. They relate by `f_i = a_i·τ_i / Σ a_j·τ_j` — for
a 0.3/0.7 mixture at 1.2/4.0 ns that is 0.11/0.89, so reading one as the other
makes a real component look negligible.

# Error analysis & sampling

| Method | Entry point | Basis |
| --- | --- | --- |
| Covariance | `covariance_matrix`, `update_error_estimates` | `scipy.linalg.pinvh` of the curvature from `approx_grad` finite differences |
| chi² scan | `Fit.chi2_scan` | brute scan of one parameter (`support_plane.scan_parameter`) |
| Support plane | `Fit.adaptive_chi2_scan` | adaptive scan to the `scipy.stats` F-test threshold → CI crossings |
| MCMC | `sample.walk_mcmc` | Metropolis on `lnprob` (`−0.5·chi2` + `lnprior`) |
| Ensemble | `sample.sample_emcee`, `sample_fit` | `emcee.EnsembleSampler` over free params; chains saved to disk |

Per-parameter `error_estimate` records whether it came from `cov` or the
support plane (`sp`).

With `J = d(weighted residuals)/dp`, the curvature matrix is `α = JᵀJ` and the
parameter covariance is `α⁻¹` — the factor of ½ in textbook definitions relates
`α` to the χ² Hessian (`2α`) and must not be applied again when inverting.
`approx_grad` takes a **relative** finite-difference step
(`epsilon · max(|p|, 1)`, default `√(machine ε)`): an absolute step cannot work
across the parameter magnitudes fluorescence models span, since adding it to a
count amplitude of order 10⁶ is lost to rounding, the difference evaluates to
exactly zero, and the parameter is then indistinguishable from one that does not
influence the model at all. Verified against the analytic least-squares
covariance `σ²(XᵀX)⁻¹`, over parameter magnitudes 1 → 10⁹, and cross-checked
against the sampled posterior (`test/fitting/test_covariance_errors.py`).

`walk_mcmc` records the state of the chain every `thin` steps *including on
rejected proposals* — repeating the current state is what makes the samples
follow the posterior rather than an acceptance-filtered caricature of it — and
returns an `acceptance_rate` alongside the chain. Proposal widths start at
`step_size` relative to each parameter's value and are then tuned by a warm-up
phase (`n_adapt`) — re-derived from the spread of the warm-up states and
rescaled by a Robbins-Monro recursion towards `target_acceptance` — and
**frozen before recording**, so the returned chain remains time-homogeneous and
its stationary distribution is still the posterior. `sample_emcee` takes
`steps` as steps *per walker* and returns `steps // thin` states per walker
(the underlying ensemble sampler counts its own `nsteps` in stored states once
thinning is on, so the loop iterates in stored states).

Both routes are cross-validated headlessly: `test/fitting/test_mcmc_posterior.py`
checks the sampled width against the analytic posterior `σ²(XᵀX)⁻¹` of a linear
model, and the PDA suite checks that the MCMC credible interval and the
support-plane F-test interval agree.

# Exposure

- Active fits live in the `chisurf.fits` list (indexed via `find_fit_idx`) — a
  legacy [runtime global](/architecture/runtime-globals.md).
- The [action layer](/architecture/action-layer.md)
  (`chisurf/core/actions/fit_actions.py`) mediates `run_fit`.
- The [API facade](/architecture/api-facade.md) (`chisurf/core/api/`) exposes
  `run_fit(fit_index/fit_uid)` for GUI, macros, plugins, and the server.

See [Core](/subsystems/core.md) and the [Core target](/specs/core.md).
