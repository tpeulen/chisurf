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
Only `numpy` and the in-tree graph layer `chinet.graph` are involved.

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

- **Rank-normalised statistics decide the verdict**
  ([Vehtari et al. 2021](https://doi.org/10.1214/20-BA1221), as Stan computes
  them). `rank_normalize` maps draws onto normal scores of their pooled average
  ranks, which is what makes both statistics defined on a heavy-tailed or
  infinite-variance target — they are built from variances, so on a Cauchy the
  plain versions are not merely imprecise but undefined, and report a
  comfortable number anyway. `rank_normalized_rhat` returns `max(bulk, tail)`
  where *tail* is the statistic of `|x − median|`: two chains with the same
  centre and different spread agree perfectly on their mean, so a location-based
  R̂ cannot see them. `bulk_tail_ess` separates the effective sample size that
  governs the posterior *mean* from the one that governs the *quantiles a
  credible interval is made of* — a chain can be trustworthy about the first and
  not the second. Both the robust and the plain values are reported, so a
  disagreement is visible rather than silently resolved.
- **A non-finite draw makes the sample size undefined, not maximal.** Every
  estimator gates on `np.all(np.isfinite(...))` and returns `nan` — `ess`, `τ`
  and the MCSE alike — because one `nan`/`inf` contaminates the FFT
  autocovariance of the whole chain. Reporting the raw draw count instead would
  read as perfectly independent draws sitting beside a refused R̂.
- **A parameter that never moved is refused and named.** The frozen case is
  detected on the *range* (`np.ptp == 0`), never on a variance: the FFT
  autocovariance centres the draws, so a bit-identical chain comes back with a
  ~1e-31 rounding residual rather than an exact zero, and whether that residual
  happens to cancel would otherwise decide between the best verdict and the
  worst for the same input. `ess`, `τ` and the MCSE are `nan` — undefined, not
  perfect — and because R̂ is a comfortable `1.0` here, `summarize` carries a
  `frozen` flag and `convergence_warnings` says so out loud. A parameter pinned
  at a bound, or one the proposal never reaches, is exactly this case.
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
| `de` (`sample_differential_evolution`) | chain-difference population | 60 |

`walk_mcmc_blocked` seeds each block's proposal covariance from
`Fit.covariance_matrix` (the curvature at the optimum — previously computed for
error bars and never used by the sampler), tunes it during a warm-up, then
**freezes** it so the recorded chain stays time-homogeneous. Blocks come from
`FactorGraph.sampling_blocks()`: variables grouped by identical
likelihood-factor neighbourhood — a true partition, cheapest block first,
degenerating to one block for a single `Fit`.

**What the warm-up may and may not touch.** The curvature at the optimum *is*
the posterior covariance for a near-Gaussian posterior, and a short chain cannot
improve on it. A warm-up chain that has not mixed spreads *less* than the
posterior it explores, so its empirical covariance is biased low — measured at
10× too narrow in every direction at once, i.e. almost purely a scale error with
the correlations intact. Replacing a curvature seed with it cost **40–80×** the
effective samples per evaluation. So the warm-up adapts:

| block seeded from | shape | scale |
| --- | --- | --- |
| the curvature | left alone | dual averaging |
| the fallback diagonal (e.g. a group's global model, where the curvature indices do not apply) | empirical, rescaled to preserve the current size | dual averaging |

The second row is not optional: a global model's blocks start from a diagonal
that knows nothing about correlations, and without shape adaptation the chain
reaches **zero** acceptance.

Three transplants from Stan needed changing to work here, each measured:

- **Dual averaging replaces Robbins-Monro** for the scale, because it reports the
  running average of the iterates rather than wherever the last few random
  acceptances left it. (This is the same technique measured to *degrade* a
  finite-difference HMC; the difference is that there the rejections came from
  gradient noise a smaller step could not reduce, whereas a random-walk
  acceptance rate responds to the scale monotonically.) Stan centres the search
  at `log(10·ε₀)` because its initial step size comes from a crude heuristic;
  here the initial scale is already the theoretical optimum `2.38/√d`, so that
  inflation just starts a decade too wide and is dropped.
- **Windows grow, they do not slide.** Stan estimates each window's metric from
  that window alone, which is sound for NUTS because it moves nearly
  independently every iteration. A random walk moves by one proposal, so a short
  window measures how far the chain *travelled*, not how wide the target *is*:
  a sliding second window estimated the scale **600× too small**, and since a
  narrower proposal then travels even less, every later window shrank again.
- **Shrinkage is towards `diag(cov)`, not the identity.** Stan samples in a
  standardised space where every coordinate is O(1), so a `1e-3·I` ridge is
  negligible. ChiSurf parameters carry physical units, so the same absolute
  ridge dominates any finely-scaled parameter and inflates its proposal until
  nothing is accepted.

The warm-up is also **short** — `clip(steps/20, 100, 500)` rather than half the
chain. Warm-up draws are discarded, so their cost comes straight out of the
effective sample size, and one scale per block settles in ~100 sweeps. Together
these gave **1.5×/5.0×/1.1×/1.8×** the effective samples per evaluation on a
collinear, an off-optimum, a two-exponential and a badly-conditioned quartic
posterior — better on every one, and ~2× in the geometric mean.

**`de` needs neither a gradient nor a covariance.** Differential-Evolution MCMC
(ter Braak) proposes `x_i + γ(x_j − x_k) + ε` with `γ = 2.38/√(2d)`, so the
proposal acquires the posterior's correlation structure from the population
itself. Every tenth generation uses `γ = 1` (a direct mode-to-mode jump) and a
fraction of moves are *snooker* updates, which is what lets the population be
smaller than the ~`2d` plain DE wants.

This is the practical answer to "why not HMC/NUTS": those need `∇ log p`, which
ChiSurf cannot supply (see the
[autodiff assessment](/references/autodiff-assessment.md)), and a systematic
benchmark of gradient-free samplers puts DE ahead of every alternative tested.
Measured here: **36×** the covariance proposal's effective samples per model
evaluation on a curved posterior started *away* from the optimum, 2.3× the
stretch move on a collinear one, and 0.77× where the covariance proposal is at
its best (converged, near-Gaussian). Use `blocked` when you have converged and
the posterior is near-Gaussian; `de` when you have not, or it is not.

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

# Gaussians in canonical form

`chisurf/core/fitting/canonical.py` holds a Gaussian as `(K, h, g)` with
`K = Σ⁻¹` and `h = Kμ` — the information parameterisation — because the two
operations an engine performs are linear in it:

- **conditioning** on `x_B = v` drops those rows/columns and shifts
  `h_A ↦ h_A − K_AB v`. Nothing is inverted, nothing is re-optimised: for a
  Gaussian this *is* the answer that fixing those parameters and re-minimising
  gives, because the constrained minimum of a quadratic is its conditional mode;
- **marginalising** `x_B` out is the Schur complement `K_A − K_AB K_BB⁻¹ K_BA`,
  and it preserves `log_mass`, so a form built with the evidence as its mass
  keeps reporting the evidence;
- **multiplying** two forms adds `(K, h, g)` on the union scope, which is what
  makes a factorised posterior composable — a global fit's form is the *sum* of
  its per-dataset ones and eliminating a variable touches only the factors it
  appears in.

All three address the scope **by name**, so the name is the identity of the
variable and a form refuses a scope that repeats one: a duplicate would resolve
to its last occurrence and quietly report another variable's moments.

`GaussianEngine` builds the form once and answers every marginal, joint and
conditional from it. `LaplaceEngine.condition` costs a full re-fit *per query*;
`GaussianEngine.conditional` costs a matrix update, so 25 conditional queries
add **zero** model evaluations. The approximation is the Gaussian, not the
algebra: the two engines now disagree only about the model, never the
arithmetic, and there is a test pinning that the closed-form conditional matches
the re-fit it replaces.

This is the representation graphical-model toolkits use for continuous
linear-Gaussian networks. [PRD-68](/prds/prd-68.md) claimed their inference
kernels "do not transfer to a continuous fluorescence posterior"; that was wrong,
and this is the part that does.

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

# The what-if sweep, for free

`GaussianEngine.conditional_scan(name, points, span)` sweeps one parameter over
±*span*·σ and reports what every other parameter becomes. This is what a profile
scan answers by re-fitting at each point; in canonical form each answer is a
matrix update, so the whole sweep costs **one** curvature evaluation however many
points it has — which is what makes it a slider (`chisurf/gui/plots/conditional_scan.py`,
the *What-if* plot) rather than a batch job. There is a test asserting a
101-point sweep over every parameter evaluates the model exactly zero times.

The closed form is used rather than one `condition()` call per point, and a test
pins that the two agree exactly. Results are also given in standardised units,
where the display reads best: for a Gaussian,
`mean(Y | X=x) = μ_Y + ρ σ_Y (x − μ_X)/σ_X`, so plotting the standardised shift
against the standardised held value gives a line **whose slope is the
correlation**. The conditional width `σ_Y √(1 − ρ²)` does not depend on where the
sweep is, so it is reported once per target: it is what the data still does not
know once the swept parameter is pinned down. A parameter that goes 90 % narrower
was never independently measured — the same statement the correlation view of the
[posterior graph](#seeing-the-structure-not-only-reading-it) makes, in numbers.

**And the approximation is checked, not assumed.** Those lines are exact only for
a Gaussian posterior, which a fluorescence posterior frequently is not: lifetimes,
amplitudes, distances and FRET efficiencies are bounded below, and a weak
component sits near its bound. `exact_conditional_scan` redoes the sweep by
re-fitting at every point — one fit per point, so it is a separate call — and
`gaussian_validity` reports the range over which the two agree. Measured on a
two-exponential with a weak second component: the straight lines hold to about
**1.5 σ** and are wrong by **4 σ** beyond that, while on the same model with a
well-determined second component they hold everywhere to within 0.12 σ.

The answer is deliberately a *range* rather than a yes/no. A posterior is almost
always near-Gaussian close to the optimum and stops being so somewhere further
out; what a user needs to know is whether that region covers the interval they
mean to quote. The two scans need not share a grid — the Gaussian curve has a
closed form, so it is evaluated wherever the re-fit actually happened, which lets
the cheap sweep stay fine-grained and the expensive one coarse.

**Every symmetric interval now says so when it is wrong.** A `laplace` or
`gaussian` marginal is `value ± sd` by construction; whenever a chain is on the
fit, `marginal_asymmetry` reads the two arms of the interval straight out of it
for nothing, and the engines attach a `warning` and the measured asymmetry to
`Marginal.diagnostics` — which the RPC payload and `Fit.posterior_summary`
already carry. Absence of a chain returns `None`, never "symmetric": absence of
evidence must not read as evidence of absence.

The cut is calibrated rather than fixed, for the same reason the rank plot's is.
Measured against true Gaussians (autocorrelated included), the 99th percentile of
the observed asymmetry ratio tracks `1 + 2.4/√n_eff`: **1.17** at 200 effective
draws, **1.04** at 3000. A single number therefore either fires on honest
Gaussians when the chain is short or misses real skew when it is long — a fixed
1.25 missed a parameter at ratio 1.20 with skew +0.57. The reported cut is the
larger of that noise floor and a 10 % floor below which the asymmetry, however
well established, is smaller than the width of a plotted error bar.

# Showing whether a chain can be believed

The convergence *numbers* were harvested from Stan earlier; the matching
*pictures* are `chisurf/gui/plots/sampling_diagnostics.py`, over headless
builders in `diagnostics.py`.

**Rank plot** (`rank_histogram`) — draws ranked across all chains together and
histogrammed per chain. Converged chains are flat; one that lingers where the
others do not shows as a slope or a spike. This is the recommended replacement
for a trace plot, because a trace plot's resolution collapses as the chain
lengthens, so it turns into a black smear exactly when there are finally enough
draws to judge. With more than five chains it is drawn as a **heatmap** (chains
× rank bins, colour = departure from flat) rather than overlaid outlines:
differential evolution runs a *population*, and twenty overlaid histograms are a
solid block of colour.

**ESS growth** (`ess_evolution`) — effective sample size against draws taken.
Converged, it grows linearly: twice the effort buys twice the information.
Flattening means the extra draws are adding nothing, and it is visible long
before any single number crosses a threshold — which a final ESS cannot show,
being one point on this curve with the shape thrown away.

**The verdict is calibrated, not a fixed percentage** (`rank_uniformity`). A
rank histogram is never exactly flat: under the null each bin count is
Binomial(*n*, 1/*b*), and the largest of *N* standardised deviations is about
`sqrt(2 ln N)` even when nothing is wrong. Judging by a fixed percentage flags
every converged run with enough bins in it, and a warning that fires on healthy
chains is worse than none — it teaches the reader to skip it.

Two corrections were needed to make that honest:

- **Autocorrelation inflates the null.** The binomial variance assumes
  independent draws, which no chain produces. Without the correction a perfectly
  converged but slowly-mixing run reports several sigma of structure that is
  nothing but its own memory (measured: 6.2σ against 3.2σ expected, on a chain
  whose heatmap is visibly clean; corrected, 1.9σ).
- **The correction must use the *within-chain* autocorrelation**
  (`within_chain_tau`), never the pooled effective sample size. The pooled
  figure collapses when chains disagree — which is the very failure the plot
  exists to detect — so using it lets every badly split run explain itself away.
  A chain's own autocorrelation does not care where the other chains sat. There
  is a test asserting exactly this trap.

# Seeing the structure, not only reading it

`FactorGraph.describe()` reports the structure as text, and the questions it
answers are the ones text answers worst: *which* dataset constrains *which*
parameter, whether the fit separates, and which parameters are really one
measurement. `chisurf/core/fitting/graphview.py` turns the same graph into
drawable data (`GraphNode`/`GraphEdge` with coordinates — Qt-free, so the layout
is testable headlessly), and `chisurf/gui/plots/posterior_graph.py` paints it.
The vocabulary is borrowed from probabilistic-graphical-model toolkits:

| their idea | here |
| --- | --- |
| the network | **Structure** — parameters against the datasets that constrain them |
| node shaded by entropy | node shaded by *relative uncertainty* (`sd/\|value\|`, scale-free) |
| arc weighted by mutual information | **Correlation** — edge weighted by `\|r\|`, which for a Gaussian posterior *is* the mutual information up to a monotone transform |
| the junction tree | **Junction tree** — cliques, with each edge labelled by the separator |

Correlation comes from a stored chain when there is one and the curvature
otherwise, so it reuses `sampling_chain` and `covariance_matrix` rather than
computing anything new. Findings are stated in words under the plot, not left
for the reader to infer: a pair above 0.95 is reported as *"one measurement, not
two"*, a graph in several components as *"this is N separate fits"*, and a
parameter with no error estimate as one the model may not respond to at all —
which the factor graph cannot see by itself, because a likelihood factor's scope
is the model's whole parameter list rather than the subset it depends on.

**Layout is semantic, not generic.** Three columns — private parameters |
datasets | shared parameters — with each private parameter on its own dataset's
row. A generic bipartite layout orders each side by whatever the graph dict
yields, which drew `c(2), c(1), a, c(3)` against `data 2, data 3, data 1`, every
edge crossing every other. Datasets go in the *middle* so that no edge ever
crosses a column of nodes; with parameters on one side only, every shared-parameter
edge is drawn straight through the private parameters' labels. Shared parameters
sit half a row off, because on a row their edge passes through that row's private
parameter and reads as a chain. These are not cosmetic: an edge through an
unrelated node asserts a connection that does not exist.

Two general rules fell out and are worth reusing: labels drop the group's
`fit:` prefix **only where the short form is unique** (three nodes all called
`c` say the fit has one parameter three times over), and layouts are rotated so
their widest direction is horizontal (a junction tree is often a chain, which a
force layout will happily draw down the middle of a wide canvas).

# Reusing a chain under a different prior

`chisurf/core/fitting/reweight.py` answers "what would this look like under a
different prior?" from a run that has already finished, instead of sampling
again. A prior changes the posterior but not the likelihood, so draws from one
transfer to the other by

$$w_s \propto \exp[\ln\pi_\text{new}(\theta_s) - \ln\pi_\text{old}(\theta_s)],$$

in which the likelihood cancels exactly. Only the parameters whose prior changed
enter the ratio — every other prior cancels too — so this is a difference of two
scalar densities per draw and evaluates **no model at all**: milliseconds against
the minutes a fresh chain costs. `sample_fit` therefore keeps the pooled
post-burn-in draws on the fit as `sampling_chain`, not only their summary; a
summary cannot be reweighted at any price.

The danger is the one every importance sampler has: if the new prior favours
somewhere the chain did not go, a few draws carry all the weight and the answer
is noise that still looks like a number. **Pareto-smoothed importance sampling**
([Vehtari et al.](https://doi.org/10.48550/arXiv.1507.02646)) fits a generalised
Pareto distribution to the largest weights and replaces them by its order
statistics, and — the reason to prefer it — returns the fitted shape $\hat k$ as
a verdict. Above 0.7 the weight variance is infinite and the result is refused
rather than reported. Measured on a known truth, the smoothing cuts the error of
the reweighted expectation by ~35 % where $\hat k \approx 0.6$, and changes
nothing where the weights are already well behaved.

Two implementation points matter. The shape estimator is
[Zhang & Stephens](https://doi.org/10.1198/tech.2009.08017)' empirical-Bayes
grid average rather than a maximisation, shrunk towards 1/2 by a prior worth ten
observations so a short tail cannot report an implausibly heavy one. And the
exceedances are computed as `expm1(lw - cutoff)` rather than
`exp(lw) - exp(cutoff)`: the latter underflows to zero once the weights span more
than ~700 log units, i.e. the diagnostic would go blind exactly where the weights
are most concentrated. Factoring the cutoff out keeps the shape (which is
scale-invariant) and turns that case into a verdict instead of a shrug.

Reachable as `ChiSurfAPI.reweight_prior(...)` and the `fit.reweight_prior` RPC,
taking priors as `get_state` dicts. `pareto_k` is reported as `null` over RPC
when it is non-finite, since that is deliberate and JSON has no spelling for it;
`reliable` and `warnings` carry the verdict either way.

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
- **Magic-angle detection skips the anisotropy path.**
  `Anisotropy.get_decay` built the rotation spectrum and handed it to
  `calculcate_spectrum`, which returns the lifetime spectrum unchanged for any
  polarization that is not VV/VH/VV-VH. Not cheap waste either: reading
  `Anisotropy.b` normalises the rotational amplitudes and *writes them back*, so
  a discarded spectrum still cost a read and a write per component per
  evaluation -- 21 % of a VM decay evaluation. Only `get_decay` short-circuits;
  reading `b` or `rotation_spectrum` directly (GUI, plots) still normalises, so
  visible values are unchanged.
- **`frozen_epoch()`** is a token identifying one uninterrupted run. Anything a
  run cannot change may be memoised against it, in particular inputs that are
  expensive to *check* rather than to compute: `Convolve._array_fingerprint`
  hashes the instrument-response bytes (a summary like `sum()` is blind to an
  in-place `np.roll`, which would serve a stale curve), which cost **14 %** of a
  decay evaluation to decide that nothing had changed. Neither the IRF nor the
  data is a fit parameter, so inside a run it is hashed once; the array's
  *identity* is still checked, and outside a run the full hash is taken as
  before.
- **Autoscale no longer announces a structure change.** `Convolve.scale` wrote
  the autoscaled amplitude by toggling `_n0.fixed` off and on -- twice per model
  evaluation, invalidating every cached free-parameter list in the program for a
  free set that does not change (`_n0` is fixed before and after).
  `Parameter.value` already writes past the port's fixed guard, so the toggles
  were redundant as well as expensive.
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
rescaled towards `target_acceptance` (`walk_mcmc_blocked` uses dual averaging
for this; see above) — and
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
  legacy [runtime global](/architecture/runtime-globals.md). Only groups are
  listed there, so a member of a grouped fit resolves to the index of the group
  holding it; a fit that is in no list resolves to `None` (`find_fit_idx` and
  `Fit.fit_idx` are `int | None`), never to a positional sentinel that would
  address a different fit.
- The [action layer](/architecture/action-layer.md)
  (`chisurf/core/actions/fit_actions.py`) mediates `run_fit`.
- The [API facade](/architecture/api-facade.md) (`chisurf/core/api/`) exposes
  `run_fit(fit_index/fit_uid)` for GUI, macros, plugins, and the server.

See [Core](/subsystems/core.md) and the [Core target](/specs/core.md).
