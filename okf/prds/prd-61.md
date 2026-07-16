---
type: PRD
prd: "61"
title: "PRD-61: Generalized Fitting with Parameter Priors"
description: Generalize the fit objective from least squares to maximum-a-posteriori and Bayesian sampling by letting any parameter carry a prior, with hard bounds implemented as the uniform-prior special case.
status: done
phase: "unassigned"
resource: chisurf/core/fitting/priors.py
tags: [prd, fitting, priors, bayesian, parameters, gui]
timestamp: '2026-07-16T00:00:00Z'
---

# Summary

Generalize ChiSurf fitting so that **any parameter can carry a prior**, and
**implement bounds as priors**. A parameter's hard box constraint becomes the
degenerate `UniformPrior`; smooth priors (Gaussian, log-normal, …) add a
maximum-a-posteriori (MAP) penalty to the least-squares objective and a proper
log-density to the MCMC posterior. The most general prior is an arbitrary
callback; predefined distribution families are conveniences on top, and
conjugate families combine in closed form so prior beliefs merge easily.

# Motivation

Before this change, bounds were the only prior-like constraint, enforced two
disjoint ways (a clamp-on-read in `Parameter.value` and a reparameterization
transform inside `leastsqbound`), and the Bayesian scaffolding (`lnprior`) only
encoded a uniform box prior. Regularizing an ill-posed fit, injecting external
knowledge (a known lifetime, a positive amplitude, a measured fraction), or
merging prior belief from multiple sources all required ad-hoc code. A single
`prior` concept unifies bounds and soft priors and feeds both the optimizer and
the sampler.

# Design

- **`chisurf/core/fitting/priors.py`** — `Prior` ABC with `lnpdf`, `residuals`
  (least-squares/MAP contribution), `support` (hard optimiser bounds), `mode`,
  `get_state`, plus `combine`/`__mul__`. Families: `UniformPrior` (bounds),
  `NormalPrior`, `TruncatedNormalPrior`, `HalfNormalPrior`, `LogNormalPrior`,
  `ExponentialPrior`, `GammaPrior`, `BetaPrior`, and `CallablePrior` (the most
  general form, wrapping any `logpdf(x)`; runtime-only). `as_prior` coerces a
  Prior / callable / state dict; `prior_from_state` + `PRIOR_REGISTRY` handle
  deserialization.
- **Bounds are priors.** `UniformPrior.support()` supplies the optimiser's hard
  bounds; `Parameter.prior` folds a uniform prior back onto `bounds`/`bounds_on`
  and surfaces an active bound as a `UniformPrior`.
- **MAP objective.** `_prior_residuals` appends each free parameter's
  `prior.residuals(value)` to the residual vector when
  `get_wres(..., include_priors=True)`; `Fit.run`/`FitGroup.run` enable it.
  `get_chi2` stays data-only so reported χ² is unchanged. The general residual is
  a signed deviance `sign(θ−mode)·sqrt(−2·Δlnpdf)`; Gaussian reduces to
  `(θ−μ)/σ` — the same trick as the Poisson `2I*` deviance residuals.
- **MCMC.** `lnprior` sums `prior.lnpdf` over free parameters (uniform-box
  fallback); `lnprob = lnprior − 0.5·chi2`.
- **Conjugate combination.** `Prior.combine` returns closed-form conjugates
  (`Normal×Normal` precision-weighted, `Gamma×Gamma`, `Beta×Beta`,
  `Normal×Uniform → TruncatedNormal`) and a generic `ProductPrior` otherwise.
- **Persistence in chinet.** A distribution prior's spec is stored on the
  parameter's `chinet.Port` (`port.prior`, in the port document/JSON) so it
  travels with the port through pickle/JSON; callback priors stay in memory.
- **GUI + RPC.** The per-parameter popup (`parameter_widgets.py`) gains a
  prior-type radio selector (Box default, Gaussian, Log-normal, Custom…) with
  inline bounds for Box and a modal `PriorEditorDialog` for advanced
  distribution parameters. Edits flow through a new `parameter.set_prior` RPC
  (`fitting_client` → `protocol` → `services.parameters` → `Parameter.prior`).

# Definition of Done

- [x] Prior families + callback + conjugate combination in `priors.py`.
- [x] `Parameter.prior` unifies bounds and priors; spec persisted on `chinet.Port`.
- [x] MAP prior residuals in `get_wres`; `lnprior` sums per-parameter priors.
- [x] `parameter.set_prior` RPC threaded client→protocol→service, `Fit.set_parameter_prior`.
- [x] GUI prior selector + advanced modal; headless screenshot-verified.
- [x] AutoForm/view-spec path: `ParameterGroupSection.priors` (and the
  `fitting_parameter` custom section's `prior` option) apply declared default
  priors to parameters when the editor is built.
- [x] Tests: `test/fitting/test_priors.py`, `test/gui/test_parameter_prior_widget.py`, client + chinet port round-trip.

# Follow-ups

- Optionally register named callbacks so callback priors can persist.

See [fitting](/subsystems/fitting.md) and [parameters](/subsystems/parameters.md).
