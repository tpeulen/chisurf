---
type: PRD
prd: "69"
title: "PRD-69: Trustworthy and structure-aware posterior sampling"
description: Make a ChiSurf MCMC run report whether it converged (R-hat, ESS, autocorrelation time, Monte-Carlo error, burn-in) instead of silently returning a chain, and replace the isotropic full-dimensional random walk with a blocked sampler whose blocks and per-block covariance come from the fit's factor graph.
status: in-progress
phase: "unassigned"
resource: chisurf/core/fitting/diagnostics.py
tags: [prd, fitting, sampling, bayesian, mcmc, diagnostics, global-analysis]
timestamp: '2026-07-25T00:00:00Z'
---

# Summary

[PRD-68](prd-68.md) made a fit's posterior factorisation explicit and fixed the
prior that the sampler was discarding. What remains is the sampler itself. Today
a ChiSurf MCMC run returns a chain and says nothing about whether that chain is
worth anything, and it explores the posterior with an isotropic diagonal random
walk over the full parameter vector — the worst available proposal for the
strongly correlated posteriors that multi-exponential decays and global fits
produce.

This PRD adds the two missing halves: **diagnostics**, so a run reports its own
trustworthiness, and **blocking**, so the proposal follows the structure the
factor graph already knows about.

# Motivation

## A chain arrives with no evidence that it converged

- No R̂, no effective sample size, no integrated autocorrelation time, no
  Monte-Carlo standard error. `emcee.EnsembleSampler.get_autocorr_time()` exists
  and is never called.
- No burn-in handling: `sample_emcee` flattens `get_chain(flat=True)` including
  the initial transient, so the walkers' start-up drift is reported as posterior.
- `sample_fit` runs `n_runs` independent chains and writes each to its own file.
  Independent runs are precisely what a cross-chain R̂ is computed from, and that
  information is thrown away.
- `walk_mcmc` returns `acceptance_rate`; `sample_emcee` returns nothing
  comparable. Neither is surfaced.
- `Fit.posterior_summary` reports `profile` and `laplace` intervals and is
  structurally unable to consult a chain, so the most expensive uncertainty
  estimate available is also the one least visible.

The user-visible consequence is that an under-converged chain and a converged
one are indistinguishable in the output.

## The proposal ignores everything the fit knows about itself

- `walk_mcmc` proposes from a **diagonal** Gaussian. Amplitude/lifetime pairs in
  multi-exponential decays are strongly correlated by construction; a diagonal
  proposal in those coordinates has an acceptance-vs-step-size curve with no
  good operating point.
- Adaptation freezes after warm-up (correctly, to keep the chain homogeneous)
  but only ever adapts per-parameter widths, never a covariance.
- `Fit.covariance_matrix` — the curvature at the optimum, i.e. very nearly the
  ideal preconditioner — is computed for error bars and never used by the
  sampler.
- Bounds are enforced by rejection, so parameters that sit near a bound (amplitude
  fractions on `[0, 1]`) waste a large share of proposals.
- Every move perturbs all D parameters at once, which in a global fit means every
  proposal is a full-cost evaluation touching every dataset — the one case where
  [PRD-68](prd-68.md)'s selective update buys nothing.

# Design

## `chisurf/core/fitting/diagnostics.py`

Pure numpy; no new dependency. Chains are `(n_chains, n_draws, n_parameters)`.

| Function | Definition |
| --- | --- |
| `autocovariance(x)` | FFT autocovariance, lags `0 … n-1` |
| `effective_sample_size(chains)` | Stan-style multi-chain ESS with Geyer initial-positive-sequence truncation |
| `autocorrelation_time(chains)` | `n_chains · n_draws / ESS` |
| `split_rhat(chains)` | Gelman–Rubin on split half-chains |
| `mcse(chains)` | `sd / sqrt(ESS)` |
| `suggest_burn_in(chains)` | `min(n/2, ceil(2·τ))` |
| `summarize(chains, names)` | per-parameter mean, sd, quantiles, ESS, R̂, MCSE, τ |
| `convergence_warnings(summary)` | the human-readable "do not trust this" list |

Correctness is pinned against an AR(1) process, whose autocorrelation time
`(1+φ)/(1−φ)` is known in closed form.

**Honesty about emcee walkers.** An ensemble sampler's walkers are *not*
independent chains, so a cross-walker R̂ is optimistic. It is still reported (a
large value is conclusive evidence of failure even if a small one is not), and
`sample_fit`'s cross-*run* R̂ — over genuinely independent runs — is the one the
warnings key off.

## Sampler outputs

Both samplers additionally return `chains` with the per-chain structure intact
(`walk_mcmc`: one chain; `sample_emcee`: one per walker) plus `acceptance_rate`
and a `diagnostics` block. `sample_fit` pools the `n_runs` runs, computes the
cross-run diagnostics, writes `diagnostics.json` beside `chains/`, and logs the
warnings. Raw chain files stay untruncated — the suggested burn-in is *reported*
and applied to the summary statistics, never silently removed from the data.

## Blocked Metropolis

Blocks come from the factor graph, by grouping variables that share an identical
**likelihood-factor neighbourhood** (`FactorGraph.sampling_blocks()`). This is a
genuine partition and it is exactly the right one:

- In a star-shaped global fit, each dataset's private parameters form one block
  (cost: one local model) and the shared parameters form another (cost: all of
  them). Sweeping the cheap blocks is nearly free under PRD-68's selective
  update.
- Variables in one block are those coupled to the same data, i.e. the ones that
  are actually correlated and should move together.
- For a single `Fit` every variable has the same neighbourhood, so there is one
  block and the sampler degenerates gracefully to the present behaviour.

Each block gets its own proposal covariance, seeded from `Fit.covariance_matrix`
at the optimum where available and otherwise from the parameter scale, then
adapted during warm-up (empirical block covariance plus a Robbins–Monro scalar
towards the dimension-appropriate acceptance target) and **frozen** before
recording, so the recorded chain stays a homogeneous Markov chain.

# Definition of Done

- [x] `diagnostics.py` with the estimators above, validated against AR(1).
- [x] Both samplers return `chains` and `acceptance_rate`.
- [x] `sample_fit` pools runs, writes `diagnostics.json`, logs warnings, and
      returns the report.
- [x] `Fit.posterior_summary` reports an `mcmc` interval from a converged
      chain, and refuses to quote one from a chain that failed its checks.
- [x] `FactorGraph.sampling_blocks()` — partition by likelihood neighbourhood,
      plus `block_cost()`.
- [x] Blocked Metropolis with per-block adapted covariance, reachable as
      `sample_fit(method='blocked')`, measured in ESS per model evaluation.
- [x] Tests (28 across three files), `docs/concepts/parameter_uncertainty.md` +
      `docs/guides/39_parameter_uncertainty.md`, `okf/subsystems/fitting.md`
      updated, `okf/log.md` appended.

## Measured

A deliberately collinear three-parameter fit (parameter correlations ≈ 0.99),
effective samples per 1000 local-model evaluations:

| Sampler | Proposal | τ | ESS / 1000 evaluations |
| --- | --- | --- | --- |
| `mcmc` | diagonal | 2024 | 0.4 |
| `emcee` | affine-invariant ensemble | 39 | 26 |
| `blocked` | per-block covariance | 12 | **64** |

The historical diagonal walker returned **4** effective samples out of 8000
draws — the case this PRD exists for. The win is the *covariance*, not the
blocking: on a 6-dataset star-linked global fit the block partition gave 2.6×
the ESS for 2.9× the evaluations, i.e. a wash on a model whose evaluation is
cheap. Blocking pays where a local model is expensive relative to the
bookkeeping, and it is what lets a shared parameter be scaled separately from
the private ones.

# Non-goals

A unified `PosteriorEngine` protocol over Laplace / profile / MCMC, expectation
propagation over the separator, gradient-based samplers (HMC/NUTS), and
transformation to an unconstrained space for bounded parameters. The first is
the natural successor once this PRD's outputs have a stable shape.
