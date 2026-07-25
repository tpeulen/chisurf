---
type: PRD
prd: "70"
title: "PRD-70: One posterior-query API over every uncertainty estimator"
description: Put the covariance, profile-scan and MCMC uncertainty estimators behind a single engine protocol — condition, add_target, run, marginal, joint, log_evidence — so a caller asks the same question of any of them and the choice of estimator stops leaking into every call site.
status: done
phase: "unassigned"
resource: chisurf/core/fitting/engine.py
tags: [prd, fitting, sampling, bayesian, architecture, api]
timestamp: '2026-07-25T00:00:00Z'
---

# Summary

ChiSurf can answer "what does the data actually support for this parameter?"
three ways — the covariance at the optimum, a profile chi² scan, and a sampled
posterior. All three exist, all three are useful, and all three have a
completely different calling convention, return shape and storage location. A
caller must know which one it wants *before* it can ask anything.

This PRD puts them behind one **engine protocol**: declare what you want to
know, run, read the answer. The estimator becomes a choice of engine rather
than a different piece of code at every call site.

# Motivation

The three estimators are unrelated code paths that happen to answer the same
question:

| Estimator | How it is invoked | Where the answer lives |
| --- | --- | --- |
| Covariance | `Fit.covariance_matrix`, then `p.error_estimate` | on each parameter |
| Profile scan | `Fit.chi2_scan` / `adaptive_chi2_scan` | `p.scan_result` dict |
| MCMC | `sample_fit(...)` writing files | `fit.sampling_diagnostics` |

`Fit.posterior_summary` already tries to paper over this, and the seams show: it
reaches into three different stores, hard-codes the precedence, and cannot be
extended without editing it. Nothing can ask for a *joint* answer over two
parameters even though a chain contains one. Nothing can ask what a fit's
evidence is. And "fix this parameter and re-optimise the rest" — the operation a
profile scan *is* — has no name of its own, even though it is exactly the
`setEvidence` of a graphical-model engine.

The architecture to copy is the one probabilistic graphical-model toolkits
settled on: **one model, many inference engines, one query API**
(`setEvidence` / `addTarget` / `makeInference` / `posterior`). Their discrete
kernels do not transfer to a continuous fluorescence posterior, but the shape of
the interface does, and it is the last piece of that architecture ChiSurf has
not taken. [PRD-68](prd-68.md) took the model (the factor graph);
[PRD-69](prd-69.md) took the inference; this takes the query.

# Design

## `chisurf/core/fitting/engine.py`

```
class PosteriorEngine(Protocol):
    def condition(self, name, value)      # fix a parameter -- "evidence"
    def add_target(self, name)            # marginal to compute
    def add_joint_target(self, names)     # joint to compute
    def run(self, **options)              # do the work
    def marginal(self, name) -> Marginal
    def joint(self, names) -> Joint
    def log_evidence(self) -> float
```

`Marginal` is a frozen dataclass: `name`, `value`, `sd`, `interval(p)`,
`quantiles`, `method`, and the diagnostics where they exist. `Joint` adds
`covariance` and `correlation`. Both are engine-independent, so a plot or a
report consumes an answer without knowing where it came from.

Only declared targets are computed, which is the point of having targets at all:
a profile scan of one parameter should not scan the other nine, and a chain
already contains every marginal so declaring them is free.

## The three engines

- **`LaplaceEngine`** — the covariance at the optimum. Cheap, always available,
  Gaussian. `log_evidence` is the Laplace approximation.
- **`ProfileEngine`** — wraps `support_plane`. Asymmetric intervals, one
  parameter at a time; `condition` is native to it.
- **`SamplingEngine`** — wraps the PRD-69 samplers. The only one with real joint
  answers, and the only one that reports whether its answer is trustworthy; a
  marginal from an unconverged chain is refused rather than returned.

`condition` is uniform across all three: a conditioned parameter is fixed and
the rest re-optimised, which is what a profile scan does natively and what the
other two do by construction.

## What changes at the call sites

`Fit.posterior_summary` becomes a thin loop over an engine instead of three
hard-coded stores, and gains the `auto` engine — best available answer per
parameter, still labelled with which one produced it. Existing behaviour and
output shape are preserved; the estimators keep their current entry points.

# Definition of Done

- [x] `engine.py` with the protocol, `Marginal`/`Joint`, and the engines --
      four rather than three: `StoredEngine` was needed because reading a
      summary must compute nothing, which is a different operation from running
      an estimator.
- [x] `auto` selection preserving the `mcmc` > `profile` > `laplace` precedence;
      `Fit.posterior_summary` is now a loop over `StoredEngine` with its output
      shape unchanged.
- [x] Engines honour `frozen_structure`.
- [x] Tests: 16 in `test/fitting/test_posterior_engine.py`.
- [x] Docs + OKF + log.

Threading `model=` through `approx_grad`, `covariance_matrix` and `walk_mcmc`
fell out of this: an engine over a group's *global* model otherwise silently got
the selected member's 2x2 covariance and reported `nan` for every other
parameter.

Reachability landed with it, because the lesson from
[PRD-69](prd-69.md) was that machinery only Python can reach benefits nobody:
`ChiSurfAPI.posterior(...)` plus the `fit.posterior` RPC expose the full query
vocabulary with a JSON-safe payload.

`condition` also had to be made to mean what it says -- pinning a value and
leaving everything else alone returns the unconditioned answer with one
parameter overwritten. The remaining parameters are now re-fitted given the
conditioned value, as a profile scan does at each of its points.

# Non-goals

Expectation propagation, gradient-based samplers, and a GUI surface for the
engine choice. This is the API; the estimators behind it are the ones that
already exist.
