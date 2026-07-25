---
type: Reference
title: "Automatic differentiation for ChiSurf fitting — measured assessment"
description: Whether exposing tttrlib's forward-mode autodiff to ChiSurf would improve fitting or sampling. Measured answer: no, because the finite-difference Jacobian is already accurate and the differentiable C++ kernel is 5–15% of a model evaluation.
resource: modules/tttrlib/src/ImageLocalization.cpp
tags: [fitting, performance, gradients, assessment, tttrlib]
timestamp: '2026-07-25T00:00:00Z'
---

# The question

tttrlib already uses forward-mode automatic differentiation
(`autodiff/forward/dual.hpp`) in `ImageLocalization.cpp`, with
`Dual<double, Eigen::Array<N,1>>` carrying every partial derivative through a
single forward pass. The pattern works, is documented and is guarded by a unit
test. Should ChiSurf's fitting use the same technique — differentiating the
decay convolution in `DecayConvolution.cpp` — to get exact Jacobians for
Levenberg–Marquardt, or gradients for a gradient-based sampler?

**Measured answer: no.** Not because autodiff is wrong, but because neither of
the two things it would buy is a bottleneck here.

# What was measured

## 1. The finite-difference Jacobian is already accurate

The concern is real in principle: `DEFAULT_EPSFCN` in
[`fit.py`](/subsystems/fitting.md) carries a comment that MINPACK's
machine-epsilon step is below the noise floor of a recursive convolution, and
raising it to `1e-6` took fits reaching `chi2r < 1.1` from 60/88 to 83/88.

But the *current* Jacobian is fine. Comparing the forward-difference residual
Jacobian against a central-difference reference on a converged two-exponential
fit (1024 channels, 2×10⁶ photons, 6 free parameters):

| step | per-column relative error (median / worst) | cos(angle) of the LM step vs reference |
| --- | --- | --- |
| `1.5e-8` (machine eps) | 8.8e-7 / 7.6e-6 | 1.000000 |
| `1e-6` (`DEFAULT_EPSFCN`) | 6.2e-7 / 1.3e-6 | 1.000000 |

The same holds 20 % away from the optimum, where LM actually spends its time.
The LM step direction agrees with the reference to six decimal places. There is
no accuracy problem left for exact derivatives to fix — the `epsfcn` change
already fixed it.

## 2. Forward-mode autodiff would not make the Jacobian cheaper

A Jacobian of `m` residuals with respect to `n` parameters needs `n` directional
derivatives however it is computed. Forward-mode autodiff costs *O(n)* passes
just as finite differences cost *n* extra evaluations; it improves the constant
and the accuracy, not the scaling. In a fit, ~`n/(n+1)` of all model evaluations
go into the Jacobian (86 % at `n = 6`), so the ceiling on any Jacobian
improvement is the constant factor — and there is no accuracy to recover.

Reverse mode *would* be asymptotically better for the **gradient of a scalar**
(cost independent of `n`), which is what a gradient-based sampler needs. See
below for why that does not help either.

## 3. The differentiable kernel is a small share of an evaluation

`tttrlib.fconv_per_cs` — the function autodiff would differentiate — as a
fraction of one `LifetimeModel` evaluation:

| channels | exponentials | share of the evaluation |
| --- | --- | --- |
| 1024 | 2 | 4.5 % |
| 1024 | 4 | 7.5 % |
| 4096 | 2 | 12.9 % |
| 4096 | 4 | 15.1 % |
| 16384 | 2 | 21.8 % |
| 16384 | 4 | 39.6 % |

Typical TCSPC (1024–4096 channels) puts the C++ kernel at 5–15 % of an
evaluation. Even a *free* derivative of `fconv` leaves 85–95 % of the forward
pass untouched.

The rest is Python: parameter reads, amplitude normalisation, scaling,
background, convolution setup. In a 1024-channel profile, `Parameter.value`
alone cost roughly ten times what the convolution did.

# Why a gradient-based sampler does not rescue the case

HMC/NUTS is the one place a gradient changes the asymptotics, and it needs
`∇ log p` over the **whole** forward path — parameter assembly, amplitude
normalisation, scale, background, *and* the convolution. Only the last of those
is in tttrlib. Differentiating the C++ kernel gives a derivative of a middle
step in a chain whose other links are Python, so it cannot be composed into the
gradient the sampler needs.

Making the full path differentiable is a different project from adding dual
numbers to `fconv`: it would mean re-expressing ChiSurf's model layer in a
differentiable framework. That is a legitimate long-term direction, but it is
not "use the autodiff that is already in tttrlib".

# What to do instead

The measurements point at Python overhead, and that is where the work went:
`factorgraph.frozen_structure` (see the
[fitting subsystem](/subsystems/fitting.md)) removed the repeated re-derivation
of parameter structure and the per-read flag dispatches, giving 2.8× on a global
objective sweep and a further 1.36× on decay model evaluations.

# What replaced the gradient

Hamiltonian Monte Carlo and NUTS are the reason one would want a gradient at
all. Without one, the question becomes which *gradient-free* sampler to use, and
a systematic benchmark of them
([arXiv:2605.30412](https://arxiv.org/abs/2605.30412)) found **differential
evolution** at a ~25 % acceptance target to outperform every alternative tested,
including the affine-invariant stretch move. DE proposes from the differences
between a population of chains, so the proposal picks up the posterior's
correlation structure with no covariance estimated and no gradient taken.

Implemented as `sample_differential_evolution`
([ter Braak 2006](https://doi.org/10.1007/s11222-006-8769-1), with the
[snooker updater](https://doi.org/10.1007/s11222-008-9104-9)). Measured against
the covariance proposal: **36×** its effective samples per model evaluation on a
curved posterior started away from the optimum, 2.3× the stretch move on a
collinear one, and 0.77× where the covariance proposal is at its best (converged,
near-Gaussian). It is the robust choice precisely because it has nothing to
mis-estimate.

# What Stan has that is usable here

Stan is the reference implementation of NUTS, and every one of its *algorithms*
— NUTS, ADVI, Pathfinder, L-BFGS — needs the gradient ChiSurf cannot supply. Its
**post-processing**, though, needs nothing at all, and is better than what was
here:

- `analyze/mcmc/rank_normalization.hpp`, `split_rank_normalized_rhat.hpp`,
  `split_rank_normalized_ess.hpp` — rank-normalised split :math:`\hat R` with a
  folded variant, and bulk/tail effective sample sizes
  ([Vehtari et al. 2021](https://doi.org/10.1214/20-BA1221)). Harvested; see the
  [fitting subsystem](/subsystems/fitting.md).
- Windowed adaptation with dual averaging — applicable to the blocked sampler's
  warm-up, not yet taken.
- Pareto-smoothed importance sampling (in `loo`, not `stan` proper) — makes
  reweighting a stored chain under a different prior reliable, and reports a
  Pareto-`k` that says when it is not. **Harvested**, and it turned out to be the
  most valuable thing in the list: it buys a capability rather than a speed-up,
  because a finished chain can now answer for priors it was not run under, at no
  model evaluations at all. See the [fitting subsystem](/subsystems/fitting.md).

# Numerical gradients and HMC — tried, measured, not shipped

The obvious follow-up to "no autodiff" is "then use a numerical gradient", and
the folklore answer -- a gradient costing *d* extra evaluations makes HMC
pointless -- is an argument, not a measurement. So it was measured, on a
collinear polynomial posterior, with the mass matrix taken from the curvature at
the optimum (which makes the target isotropic for the integrator).

Effective samples per 1000 model evaluations:

| parameters | HMC (FD gradient) | `de` | `blocked` |
| --- | --- | --- | --- |
| 3 | **83** *(hand-tuned)* / 68 *(adapted)* | 73 | 53 |
| 5 | 19 → 0.25 *(adapted)* | 30 | **40** |
| 8 | 0.09, acceptance 0.00 | 4 | **18** |

**At three parameters it produced genuinely independent draws** — an
autocorrelation time of 1.0 — and with hand-tuning beat everything. That is a
real result and it contradicts the folklore. It is also not shippable, for three
reasons:

1. **Adaptation makes it worse.** Dual averaging (as Stan adapts its step size)
   reads finite-difference-induced rejections as "the step is too big" and
   shrinks ε — but shrinking ε does not reduce the *noise* contribution, so it
   shrinks without limit. Adapted, HMC reached 68 at three parameters, i.e.
   **below `de`**. The 83 came from an exhaustive sweep finding one lucky
   configuration (two leapfrog steps, ε ≈ 0.8) that no adaptive scheme
   reproduces.
2. **It collapses with dimension.** By five parameters it is behind both
   alternatives; by eight, acceptance is zero. Two compounding causes: the
   gradient's cost grows with *d* while no other sampler pays that, and
   finite-difference error accumulates along a trajectory until the leapfrog
   stops conserving energy, so every proposal is rejected.
3. **The failure is quiet.** Zero acceptance produces a chain that looks like a
   short converged one. Only the effective sample size gives it away.

Two leapfrog steps is barely Hamiltonian — it is essentially MALA. So the honest
summary is that a gradient buys, in the one regime where it works at all,
nothing that `de` does not already provide without one. The implementation was
written, measured and removed rather than kept as an option that could only
mislead.

**And the analytic gradient does not rescue it either.** The obvious candidate
was that a decay model is *linear in its amplitudes*, so those Jacobian columns
would be convolutions the forward pass already computes — exact and free rather
than *d* extra evaluations, with no new dependency. Tested by asking whether
``m(θ + t·e_k)`` is affine in ``t``:

| parameter | autoscale on (default) | autoscale off |
| --- | --- | --- |
| background | **linear** | **linear** |
| scatter | nonlinear | **linear** |
| ``n0`` | — (held) | **linear** |
| amplitude fraction | nonlinear | nonlinear |
| lifetimes, timeshift | nonlinear | nonlinear |

The premise is false for ChiSurf's parameterisation, and deliberately so.
Amplitudes are exposed as *normalised fractions*, which is a nonlinear map of
the amplitudes the convolution is linear in; and with autoscale the model is
scale-invariant in them, so the derivative is not the convolved component at
all. In the default configuration exactly one free parameter is linear — about
12 % of a fit for a per-model hook. Not worth it.

# When to revisit

- If a model's forward pass moves substantially into C++ (so the differentiable
  share rises well past 40 %).
- If ChiSurf gains genuinely high-dimensional posteriors — hundreds of
  parameters, e.g. a maximum-entropy lifetime distribution — where HMC's scaling
  advantage over a blocked random walk would outweigh the cost of making the
  path differentiable.
- If a model is found whose finite-difference Jacobian *is* noise-dominated. The
  measurement above is one model at one photon count; it is evidence, not a
  proof for every model.
