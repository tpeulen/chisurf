---
type: PRD
prd: "68"
title: "PRD-68: Fit Factor Graph — structure-aware objectives and posteriors"
description: Materialise the factor structure of a fit's posterior (variables = free parameters, factors = per-dataset likelihoods and per-parameter priors) so global fits stop recomputing every dataset per evaluation, and so blocks, separators, treewidth and identifiability become queryable; plus the prior fix that makes MCMC target the same posterior as MAP.
status: done
phase: "unassigned"
resource: chisurf/core/fitting/factorgraph.py
tags: [prd, fitting, sampling, bayesian, global-analysis, performance, priors]
timestamp: '2026-07-25T00:00:00Z'
---

# Summary

A ChiSurf posterior already factorises exactly

```
p(θ | D)  ∝   ∏_k L_k(θ_{S_k})   ·   ∏_i π_i(θ_i)
```

where `S_k` is the set of free parameters that dataset *k*'s model actually
reads, and `π_i` is parameter *i*'s prior ([PRD-61](prd-61.md)). Nothing in the
fitting engine represents that factorisation. `GlobalFitModel` flattens every
local model's free parameters plus the globals into one dense vector and
recomputes **all** local models on **every** objective evaluation, so a
proposal that perturbs one parameter of one dataset costs N model evaluations
instead of one.

This PRD makes the factorisation a first-class object — a **factor graph** over
the fit — and uses it for three things: relevance (recompute only what changed),
structure (cliques, separators, treewidth, connected components), and reporting
(which parameters are conditionally independent of which, i.e. an
identifiability statement). It also repairs the prior/MCMC discrepancy that
makes the sampler target a different distribution than the optimiser.

# Motivation

## The sampler ignores informative priors

`lnprior` (`chisurf/core/fitting/fit.py`) has two branches: given `bounds` it
returns the flat box prior and never consults the parameters; only with
`bounds=None` does it sum `prior.lnpdf`. Both samplers pass `bounds`
unconditionally (`sample.py`, `walk_mcmc` and `sample_emcee`), and they are the
only two call sites of `lnprob` in the tree. The informative branch is therefore
dead code: every `NormalPrior` / `LogNormalPrior` / `GammaPrior` / `BetaPrior` a
user attaches is **silently dropped from the MCMC posterior**. MAP
(`_prior_residuals`) *does* honour priors, so the optimiser and the sampler
target different distributions — which contradicts both `priors.py` and the
[fitting subsystem](/subsystems/fitting.md) concept.

A second, related defect: chains record `chi2r = -2·lnp/dof` where `lnp` is the
log-*posterior*. Once priors work this conflates data misfit with prior
contribution and drags in prior normalisation constants. Likelihood and prior
must be stored as separate columns — which additionally makes prior-sensitivity
analysis a free post-hoc reweighting of an existing chain rather than a rerun.

## The global fit is flat where it is structured

`GlobalFitModel.parameters` is the concatenation of every local model's free
parameters and the global parameters; `update_model` loops over all local fits
(optionally threaded). Consequences:

- **Objective.** Every `get_wres` call re-evaluates N models. For a global fit
  the wasted fraction is `(N-1)/N` whenever a proposal or finite-difference step
  touches one dataset's local parameter — which is the overwhelming majority of
  steps, since local parameters outnumber globals.
- **Jacobian.** `approx_grad` takes D full *global* evaluations per Jacobian,
  though the true Jacobian is block-arrow: block-diagonal in the locals with
  dense columns only for the shared globals.
- **Sampling.** An isotropic diagonal random walk over the full D-dimensional
  vector, when the target decomposes into near-independent low-dimensional
  blocks given the separator.
- **Reporting.** Nothing can answer "which parameters are coupled?", which is
  the identifiability question a global fit exists to answer.

The information needed is already present — `FittingParameter.is_linked` /
`.link`, the local/global split, `parameters_all` — it is simply never assembled
into a graph.

## Why a graph, and why not a PGM library

The design is deliberately modelled on the architecture of mature probabilistic
graphical-model toolkits: a **model object separate from the inference engine**,
moralisation + triangulation + junction tree to expose blocks and separators,
relevance/barren-node pruning per query, and incremental invalidation of only
what a change touches. Those toolkits' *inference kernels* are discrete-table
sum-product and do not transfer to a continuous fluorescence posterior; the
*structural* machinery transfers exactly and is ~150 lines over the graph
primitives already available in the environment.

**No external dependency.** Implementation uses only `numpy`, `numba` and the
in-tree graph layer `chinet.graph` (containers, connected components, spanning
trees, layouts, GraphML). The external graph library this originally leaned on
was removed from the environment; the same vocabulary now lives in the
application's own runtime, alongside the globalview plugin and the node editor
that share it.

# Design

## `chisurf/core/fitting/factorgraph.py`

Two frozen dataclasses and one container. Everything is keyed by a stable
string, so a graph can be serialised, diffed and logged.

```
VariableNode(key, name, index, fit_index)      # a free parameter
FactorNode(key, kind, scope, fit_index, size)  # kind ∈ {likelihood, prior}
```

- `key` — the parameter's `unique_identifier` (falls back to a stable
  `id()`-derived key). `index` is its position in the flat free-parameter
  vector, so the graph and `model.parameter_values` stay aligned.
- `scope` — the variable keys a factor depends on. A likelihood factor's scope
  is resolved by walking each of the local model's `parameters_all` through the
  `link` chain to its free root; a prior factor has scope of one.
- `size` — the number of residuals the factor contributes (`n_points` for a
  likelihood, 1 for a prior). Used to weight cost estimates.

`FactorGraph` API:

| Method | Purpose |
| --- | --- |
| `factors_of(var)` / `variables_of(factor)` | incidence |
| `markov_graph()` | moralised undirected graph: a clique per factor scope |
| `connected_components()` | independent sub-problems (separable fits) |
| `elimination_order(heuristic)` | greedy `min_fill` (default) or `min_degree`; cached |
| `cliques(order)` | maximal cliques induced by elimination; cached |
| `junction_tree()` | clique tree via max-weight spanning tree on \|separator\| |
| `treewidth` | `max clique size − 1` — the fit's structural difficulty |
| `blocks()` | clique-derived sampling/scan blocks |
| `affected_factors(changed_keys)` | relevance: factors whose scope intersects |
| `affected_fits(changed_keys)` | the local fits that must be recomputed |

`markov_graph()`, `elimination_order()` and `cliques()` are memoised for the
lifetime of an unmutated graph and dropped together by `invalidate()`, because
every other structural query is a wrapper over them: `treewidth`, `blocks`,
`junction_tree`, `separators`, `describe` and `__repr__` would otherwise each
re-run the greedy elimination. A *complete* Markov graph — every single-`Fit`
graph — short-circuits both: with every node costing the same at every step the
elimination has nothing to decide, so the order is the tie-break (variables by
vector index) and there is a single maximal clique.

`build_factor_graph(fit)` handles both `Fit` (one likelihood factor over all
free variables — a single clique; single fits have no exploitable structure at
this level, and the API says so honestly) and `FitGroup` (one likelihood factor
per local fit, plus prior factors).

## Structure invalidation

A module-level `STRUCTURE_VERSION` counter, bumped by `bump_structure_version()`
from the seams that can change the graph: `Parameter.link` set/clear,
`Parameter.fixed`, `GlobalFitModel.append_fit` / `remove_local_fit` /
`clear_local_fits` / `append_global_parameter`, and
`FittingParameterGroup.find_parameters`. A cached graph carries the version it
was built at and rebuilds when it differs. Rebuilds are O(parameters) and rare.

## Structure-aware `update_model`

The selective path is **armed only by a complete parameter-vector assignment and
consumed once**:

1. `GlobalFitModel.parameter_values` setter diffs the incoming vector against
   the current values — comparing the *readback*, since a bound or transform can
   leave the effective value where it was — maps the changed indices to variable
   keys, and stores `_pending_dirty_fits = graph.affected_fits(changed)`.
2. `update_model` consumes and clears `_pending_dirty_fits`; if it is `None` it
   recomputes **all** local fits.

Any `update_model()` not immediately preceded by a full vector assignment — a
GUI edit of a single `p.value`, a direct model poke, a structure change — falls
back to a full recompute. The optimiser and both samplers already use exactly
the `parameter_values = v; update_model()` pattern (`get_wres`), so they get the
speedup for free with no call-site changes and no way to silently desynchronise.

Two further guards, both found by the equivalence test rather than by design:

- **Nothing may be skipped until everything is current.** Skipping a local model
  that has *never* been evaluated leaves its stale residuals in the objective. A
  `_current_at_version` stamp records the structure version at which the last
  full pass ran; selective updating is admissible only while it matches
  `structure_version()`. So the first evaluation of a fresh or restructured
  group is always a full one.
- **An unexplained variable forces the conservative path.**
  `FactorGraph.unexplained_variables()` reports free parameters no likelihood
  factor depends on. Either they genuinely do nothing, or a model couples them
  to its data by a route the graph does not model; an empty `affected_fits`
  answer must not be mistaken for the former, so a change to one of them
  recomputes everything.

`optimization.global_structure_aware_update` (default true) disables the whole
selective path for custom global models coupled by something other than links.

## Prior fix

`lnprior(parameter_values, fit, bounds=None)` stops short-circuiting: `bounds`
becomes an *additional* cheap box rejection evaluated before any model call, and
the per-parameter priors are always summed when `fit` is given. Parameters whose
only prior is the box are skipped when `bounds` already enforced it (the same
`_prior`/`_port.prior` presence check `_prior_residuals` uses), so the hot path
does not allocate a `UniformPrior` per parameter per step.

A new `lnprob_parts(...) -> (lnlike, lnprior, chi2)` lets samplers store the
data and prior terms separately; `lnprob` remains their sum. Chains gain
`lnprior` as its own column and `chi2r` reverts to the data-only misfit.

# Definition of Done

- [x] `lnprior` honours smooth priors even when `bounds` is passed; both
      samplers verified to reproduce a known Gaussian-prior posterior.
- [x] `lnprob_parts` exists; `walk_mcmc` / `sample_emcee` return `lnprior`
      separately and `chi2r` is data-only; chain files carry the extra column.
- [x] `factorgraph.py` with variable/factor nodes, builder, Markov graph,
      min-fill elimination, junction tree, treewidth, blocks, relevance queries.
- [x] Graph primitives come from the in-tree `chinet.graph`; no external graph
      library is declared in `pyproject.toml`, `pixi.toml` or the conda recipe.
- [x] `GlobalFitModel` caches a factor graph, arms dirty fits from the
      `parameter_values` setter, and recomputes only affected local fits.
- [x] `STRUCTURE_VERSION` bumped from every seam that changes the graph.
- [x] Tests: prior round-trip, graph structure for a star-shaped global fit
      (treewidth, blocks, separators), relevance correctness, and an
      equivalence test showing selective and full updates give identical
      residuals. 30 tests across three files.
- [x] `okf/subsystems/fitting.md` updated; `okf/log.md` appended.

Measured on a 16-dataset star-linked group (512 points each, 300 one-parameter
moves through `get_wres`): **4800 → 555 local-model evaluations**, exactly the
predicted `300·(16/17·1 + 1/17·16)`. Wall time fell 158 ms → 101 ms only because
the toy model's evaluation is trivial and fixed per-call overhead dominates; for
a real convolution model the wall-clock ratio approaches the evaluation-count
ratio.

**Least squares gets this for free too.** MINPACK builds its Jacobian by
forward differences, perturbing one parameter per call to `func` — and each such
call assigns the complete vector, so it lands on the selective path with a
single changed entry. A 12-dataset star-linked `FitGroup.run()` needs
**387 → 141 local-model evaluations** (2.74×) and reaches a bit-identical
optimum (`Δa = 0`, `Δchi2r = 0`). No separate block-arrow Jacobian assembly is
needed to get most of that benefit.

# Non-goals (deferred)

Blocked / Rao-Blackwellised samplers over the junction tree, expectation
propagation over the separator, a unified `PosteriorEngine` protocol covering
Laplace / profile / MCMC behind one query API, block-arrow Jacobian assembly,
and experiment design from posterior entropy. All are enabled by this PRD's
graph and are intentionally out of its scope.
