---
type: PRD
prd: "71"
title: "PRD-71: Fast 2D MFD Fitting — kinetic models fitted to E–⟨t⟩ and r–⟨t⟩ burst histograms"
description: Fit kinetic models to the two-dimensional multiparameter-fluorescence burst histograms by forward-modelling the raw per-burst observables over a PDA-style empirical nuisance measure of burst signal and green/red observation times, with the mean micro time replacing per-burst lifetime fitting and three composable scoring sources over one model core.
status: draft
phase: "unassigned"
resource: chisurf/core/fluorescence/mfd/
tags: [prd, fret, mfd, burst, kinetics, anisotropy, pda]
timestamp: '2026-07-29T00:00:00Z'
---

# Summary

**Objective: fit two-dimensional kinetic models against MFD burst histograms.**
The plots that define multiparameter-fluorescence detection — FRET efficiency
against donor lifetime, and anisotropy against lifetime — are today *read* (a
static line is drawn on top and the deviation discussed) rather than *fitted*.
This PRD makes them fittable at interactive speed. Four moves:

1. **The burst statistics come from the experiment, PDA-style.** The nuisance
   measure is the *empirical* joint distribution of the burst signal `S` and the
   green/red observation times `(t_G, t_R)` — call it **D12** — taken from the
   selected bursts exactly as photon-distribution analysis takes `P(S)` per time
   window, except the windows here are variable-length bursts, which is why the
   measure is resolved by time. No diffusion is simulated and no brightness law is
   assumed, so the optical nuisances (volume, diffusion coefficient, focal depth)
   never enter and the shot-noise width of the FRET axis comes out of the
   *measured* signal distribution with nothing to get wrong.
2. **The lifetime axis is the mean micro time, not a per-burst lifetime fit.**
   `⟨t⟩` is a linear statistic, so its conditional distribution given the photon
   number and the underlying pattern is analytic, and the pattern's first two
   moments follow from the decay parameters and the IRF moments in closed form. A
   per-burst maximum-likelihood lifetime is neither: expensive at evaluation time
   and biased at 50–500 photons, with a bias that moves with the parameters.
3. **Everything is fitted in raw observable space.** Bins are laid on the
   proximity ratio, the raw `⟨t⟩`, and the raw parallel/perpendicular ratio; all
   corrections and the background live in the forward model. The data histogram is
   therefore built once and never moves, and any correction may become a free
   parameter without the fit's target shifting underneath it.
4. **Three composable scoring sources over one model core** — individual bursts
   (the maximum-likelihood reference), marginalized 2D histograms (the fast path),
   and pooled per-bin decays (which recover the decay shape the mean micro time
   discards). Same parameters, same patterns, same occupation-time machinery;
   the sources are selectable and combinable, and their agreement is a test.

What remains to be computed per evaluation is the occupation-time distribution of
the rate matrix over a burst — done deterministically, not by simulation — and a
few matrix products over precomputed grids. Cost is independent of the number of
bursts under the histogram and decay sources, because the bursts enter only
through objects computed once.

# Status

Draft. Nothing implemented. The design below is settled; the staging is the
proposed order of work. The approach has precedent — a comparable scheme has
worked before — so the risk sits in *this* implementation, which is what the
two-step milestone in the Validation section is built to catch.

Parent: [PRD-49](prd-49.md). Related: [PRD-50](prd-50.md) (PDA — same nuisance
trick, one dimension lower), [PRD-65](prd-65.md) (three-colour PDA, same nested
background sum expressed as matrix products), [PRD-53](prd-53.md) (photon-level
simulation — the *code* test, never the physics test), [PRD-60](prd-60.md)
(H2MM), [PRD-61](prd-61.md)/[PRD-68](prd-68.md)/[PRD-69](prd-69.md)/[PRD-70](prd-70.md)
(priors, factor graph, sampling, posterior API).

# Motivation

Both axes of an MFD plot are per-burst estimators from few photons, so the cloud
is dominated by shot noise whose shape is set by the burst-size distribution —
itself a product of diffusion, brightness, and the burst-search threshold. The
spread perpendicular to the static line is where the dynamics information lives,
and it is confounded with that shot-noise spread. Predicting the shot-noise
contribution from first principles means a diffusion Monte Carlo inside every
likelihood evaluation, which is unfittable and drags in optical nuisance
parameters nobody wants. Producing the lifetime axis by fitting each burst's decay
is slow and biased, and its sampling distribution is not analytic, so the model
cannot say where the cloud should sit.

All three problems come from trying to *invert* per burst. Forward-modelling the
raw observables removes them together, and the one genuinely instrument-dependent
ingredient — how much signal a burst has, and over how long — was measured.

# Design

## Input and derived products

The fit's input is the **processed burst dataset**: the burst table and its
companion columns, plus the photon source. There is no separate 2D data file to
load; every 2D product is derived inside the fit and cached, with the binning
owned by the fit and changeable without re-deriving anything upstream. A 2D export
exists for figures and for handing results to collaborators, but it is never a fit
input — which removes an entire class of failure in which a histogram is fitted
against a nuisance measure computed from a different burst selection.

At setup the bursts' photons are read **once** into a packed array — the
`PhotonBursts` layout already in
`chisurf/core/fluorescence/burst/gopich_szabo.py`: concatenated channel and
micro-time with per-burst offsets (≈22 MB for 50 k bursts of 150 photons; ≈600 MB
for a million bursts of 200). D12, the observed histograms, and the pooled decay
cube are all derived from that one structure, so they cannot disagree about which
bursts they describe. Where the raw data is not reachable, the fit falls back to
the companion's per-burst summary columns and is then restricted to the histogram
source — stated loudly at fit construction, never degraded silently.

## The nuisance measure — PDA-style, resolved by time

**D12 holds times, not counts.** Per burst it records the green and red
*observation spans* `(t_G, t_R)`, and it is used jointly with the measured burst
signal `S`:

```
nuisance (empirical, from the data):   D12 = P(S, t_G, t_R)
modelled:                              the partition of S into channels
                                       + the micro-time patterns
```

This is photon-distribution analysis's treatment of `P(S)`, with the fixed time
window replaced by a per-burst pair of spans. Three consequences, all of them the
point:

* **No brightness law.** Brightness enters only through the measured `S`
  distribution, so the FRET axis's shot-noise width is set by data rather than by
  an assumption. A parametric `P(S)` remains available as a later refinement for
  the cases where the burst-size distribution is itself the question — it is not
  in the default path and not in the first milestone.
* **Selection is inherited, not modelled.** The empirical measure carries the
  burst-search threshold the same way PDA's `P(S)` carries its window criterion,
  so there is no separate truncation mechanism to get wrong. What survives as an
  assumption is that selection does not correlate with state; see *Known
  approximations*.
* **The spans do the work a fixed window cannot.** Background is Poisson with mean
  `bg_rate_c · t_c` per channel — PDA's `rate × window`, per channel and per burst
  — and the green/red span asymmetry additionally carries acceptor bleaching and
  blinking, which a single duration cannot express.

`t_c` is the **first-to-last photon span** in channel `c`. That is a biased
estimator of the true observation time, by a factor `(n−1)/(n+1)`, and the bias
depends on brightness — i.e. on something being fitted. The bias is therefore
**forward-modelled, never corrected**: the model predicts the *observed* span,
exactly as it predicts raw axes and background rather than corrected ones. Bursts
with fewer than two photons in a channel take a sentinel value; per the
[burst-companion contract](/subsystems/burst-companions.md) they are never a
missing row.

## States

A state `s` carries a mean distance `d_s` and a rotational correlation time
`ρ_s`. The distance is **distributed, and the distribution is not Gaussian**: with
both dye positions Gaussian-distributed in three dimensions, their separation
follows the non-central chi distribution,

```
p(R) = R / (d σ √(2π)) · [ exp(−(R−d)²/2σ²) − exp(−(R+d)²/2σ²) ],
σ² = σ_D² + σ_A²
```

`σ` is **free and shared across states**, with an informative prior centred on the
accessible-volume estimate for the labelling positions
([PRD-61](prd-61.md) priors). It is promoted to per-state only under the
burst-wise or pooled-decay sources, which are the ones that can resolve per-state
decay shape; under the histogram source alone the prior carries it.

**`p(R)` is static on the nanosecond scale and averaged on the millisecond
scale.** The excited-state lifetime is short compared with linker sampling, so the
decay is a genuine *lifetime distribution*; the burst is long compared with it, so
each burst's efficiency is the `p(R)`-average:

```
decay:   I(t | s) = ∫ dR p(R) exp( −t / τ(R) )      → distribution of lifetimes
burst:   E_s      = ∫ dR p(R) E(R)                   → one value per burst
```

This is what produces the familiar linker-broadened static line — and it means `σ`
is imprinted on the decay *shape*, so the sources that keep the decay can see it
instead of inferring it from a shift.

From `(d_s, σ, ρ_s)` follow, per detection channel `c ∈ {G∥, G⊥, R∥, R⊥}`, a
normalized micro-time pattern and a channel branching vector: donor components
quenched by the transfer rate at each `R`; sensitized acceptor as the quenched
donor convolved with the acceptor decay; leakage `α` of the donor pattern and
direct excitation `δ` of the acceptor-only pattern; the `∥/⊥` split by
`r(t) = r₀ exp(−t/ρ_s)` with the `G` factor and the `l₁/l₂` depolarization
factors; measured background pattern per channel; scatter as the IRF.

## The enabling identity: two moments

A photon's micro time is the IRF arrival plus an independent decay delay, so means
and variances **add under convolution**:

```
μ = μ_IRF + μ_decay          v = v_IRF + v_decay
μ_decay = Σ x_i τ_i          v_decay = 2 Σ x_i τ_i² − (Σ x_i τ_i)²
```

with the mixture weights `x_i` running over the `p(R)`-weighted lifetime
distribution and over background and scatter. The lifetime-axis model therefore
needs the IRF's first two moments and nothing else — no numerical convolution
inside the fit loop.

**Wrap-around trap.** The finite TAC window and pulse periodicity break the
additivity: a photon emitted late reappears at the start of the next period. Use
the wrapped moments — the wrapped exponential has a closed-form mean,
`μ = τ − T_rep / (exp(T_rep/τ) − 1)` — or take them numerically from the periodic
pattern once per parameter change. Silently using unwrapped moments biases every
long lifetime short, and the histogram will absorb that into a rate rather than
complain.

## Kinetics: occupation times

Given a state path, the channel counts and the micro-times depend on the path
**only** through the vector of occupation-time fractions `f`, `Σf = 1`. That is
exact, not an approximation: `f` is the path's sufficient statistic for the
histogram and decay sources. (The burst-wise source does not need `f` at all — it
marginalizes paths exactly by the matrix product already implemented in
`gopich_szabo.py`.)

`P(f | T, K)` is computed **deterministically**: discretize the burst into `n`
steps and propagate the joint distribution over (state, occupation counts) with a
transfer matrix built from the rate matrix `K` — the shared fittable rate-matrix
group in `chisurf/core/fitting/kinetics.py` (`K[target, source]`), not a private
one. No Monte-Carlo noise enters the objective, so the optimizer cannot chase it.
Cost is `~ n · n^(M−1) · M²`: trivial for two states, comfortable for three, and
sampled paths remain the fallback for `M ≥ 4` or for non-exponential dwells. The
closed-form two-state occupation-time density is the correctness test of the
propagator, not an alternative code path. The table is cached per duration bin and
recomputed only when `K` changes.

## Axes: raw, with corrections in the model

Bins are laid on the **proximity ratio** `N_R/(N_G+N_R)`, the **raw** `⟨t⟩`, and
the **raw** parallel/perpendicular ratio. `α, β, γ, δ`, `G`, `l₁/l₂` and the
background live entirely in the forward model. This is what allows a correction to
be a free parameter: on corrected axes, changing `γ` moves the *data* histogram,
and a deviance against a moving target is not a fit statistic — an optimizer can
lower it by reshuffling bursts rather than by explaining them. On raw axes the
data histogram is built once, the count→bin map is a fixed precomputed sparse
matrix, and corrected axes are produced for display and for the overlay lines
only.

## Scoring sources

One model core — patterns, `P(f|T,K)`, corrections, one parameter vector — and
three sources, selectable and combinable:

**Individual bursts (maximum-likelihood reference).** The joint probability of
each burst's channel counts *and* its individual micro times, marginalizing the
state path:

```
log L = Σ_bursts log ∫ df P(f | T_b, K) · [partition term] · Π_photons p_c(t_i | f)
```

No binning, no compression, full decay shape of every burst. Defines the
information bound the other two are measured against. Cost is
`O(bursts × photons)` — and worth *measuring* rather than assuming: with the inner
integral tabulated on an `f` grid and the per-photon term reduced to a lookup in a
precomputed pattern table, tens of millions of lookups is milliseconds.

**Marginalized 2D histograms (fast path).** The model histogram against the
observed one. Conditioned on `(S, t_G, t_R)` the background counts are Poisson
with known means and the remaining signal partitions binomially — PDA's nested sum
— while the lifetime-axis kernel is Gaussian with mean `μ_g(f)` and variance
`v_g(f)/N_g` for `N_g ≳ 20`, with exact self-convolution available for the
low-count wing. The `(S, N_G)`-to-bin scatter matrix is fixed and precomputed, so
a model evaluation rebuilds only a small `(N_G-grid × t-bins)` table and
multiplies through: a few matrix products of order 100×100, independent of the
burst count.

**Pooled per-bin decays.** Pool bursts into histogram bins and sum their photons
into a real decay histogram per bin, scored `(bin × micro-time channel)` with the
Poisson deviance. Recovers the decay shape the mean micro time discards — a bin
holding a within-burst mixture and a bin holding a single intermediate lifetime
have the same mean and different pooled decays — at a cost scaling with
`bins × channels` rather than with bursts × photons. **Selection trap:** pooling on
a coordinate conditions on that statistic; pool on coordinates the model predicts
exactly, and if the lifetime axis is a pooling coordinate the model must reproduce
the same conditioning, or every pooled decay tilts in a way that reads as a
lifetime shift.

## Fit targets and the statistic

The targets are a **set of 2D marginals sharing one parameter vector** —
`H[PR, ⟨t⟩_D]` and `H[r_D, ⟨t⟩_D]`, extensible to the acceptor side — with the
Poisson deviance / `2I*` already used by the PDA models. Never χ² on bins holding
single-digit counts. Bins where the model predicts zero and the data hold counts
are handled explicitly: either an impurity/background floor component, or masking
with **the masked fraction reported**, never silently dropped.

**The summed deviance is an M-estimator, not a likelihood.** The same bursts
appear in every marginal (and in every source, when sources are combined), so the
score double-counts the data and its curvature reports uncertainties that are too
small. The optimum comes from the summed score; **uncertainties come from the
burst-wise source or from a burst bootstrap**, and that is enforced in code rather
than documented in a footnote.

# Validation

Milestone 1 is **two steps, and both gate**. Passing 1a alone is compatible with a
broken duration/span lookup that only surfaces once kinetics rides on it.

* **1a — static, single state, real data.** Model core plus the histogram source,
  one state, no kinetics: the cloud's position *and* its width must be reproduced
  with **no free broadening parameter**. Any unexplained width will later be
  absorbed as exchange, so everything downstream is meaningless until this passes.
* **1b — known-rate kinetics recovered.** A system whose exchange rate is known
  independently must come back correct, which is what exercises the occupation-time
  propagator and the span/duration lookup together.

**The photon-level simulator is a code test, never a physics test.** It shares
every physical assumption with the model, so a shared error passes silently; it
proves the implementation matches its own assumptions and nothing more. Beyond the
milestone: cross-check the rates against the photon-by-photon likelihood in
`gopich_szabo.py` and against H2MM on the same bursts, and compare the parameter
uncertainty against the burst-wise bound so the price of compressing a burst to
two numbers is *quantified* rather than assumed negligible.

# Known approximations

* **Selection is assumed uncorrelated with state.** The empirical nuisance
  inherits the burst-search threshold automatically, but a molecule switching
  state mid-burst has a state-dependent selection probability. To be tested
  against the photon-level simulation, not waved through.
* **`γ` and the nuisance.** `S` must be the FRET-independent green-equivalent
  total; if `γ` is free, `S` is recomputed with it and the nuisance iterated to
  consistency — an explicit loop, not an accident.
* **Compression to `⟨t⟩`.** One number per burst per channel cannot separate a
  within-burst mixture from a single intermediate lifetime; the discrimination
  comes from the joint with the FRET axis, which is why the dynamic line curves.
  Quantify it, do not argue it — and the pooled-decay source exists precisely to
  buy the shape back.
* **The Gaussian `⟨t⟩` kernel** below ~20 photons per channel; the exact
  self-convolution path must exist for the low-count wing.
* **Transfer-matrix discretization** in `n`; convergence in `n` is a test, not an
  assumption.

# Staging

1. **Data side** — per-burst `⟨t⟩` per channel group, polarized counts, spans
   `(t_G, t_R)` with sentinels, `S`; D12 builder; `PhotonBursts` load path;
   companion columns under the contract. Headless first.
2. **Static forward model** — one state, no kinetics: non-central-chi `p(R)`,
   pattern moments with wrap-around, raw-axis histograms, PDA-style background and
   partition, Poisson deviance. **Gate: milestone 1a.**
3. **Kinetics** — transfer-matrix `P(f|T,K)` over the shared rate-matrix group,
   two-state closed form as its test. **Gate: milestone 1b.**
4. **Pooled-decay and burst-wise sources**, composable with the histogram source;
   bootstrap/burst-wise uncertainties wired in and enforced.
5. **Anisotropy axis** in full — `G`, `l₁/l₂`, per-state `ρ`, with the Perrin
   relation as a *prediction*.
6. **Surfacing** — fitting model plus view spec (PRD-38/40), 2D plots through
   chiplot with the analytic overlay lines, CLI, a theory page under
   `docs/concepts/` and a numbered guide under `docs/guides/` covering burst
   search through fit.
7. **Global fits** — link across measurements, titrations and species on the
   factor graph ([PRD-68](prd-68.md)); posteriors through the one posterior-query
   API ([PRD-70](prd-70.md)).
8. **Optional refinements** — parametric `P(S)` when the burst-size distribution
   is itself the question; per-state `σ`; acceptor-side marginals.

# Placement

* Compute core: `chisurf/core/fluorescence/mfd/` — Qt-free (`patterns.py`,
  `moments.py`, `occupation.py`, `histogram.py`, `sources.py`, `fit.py`), numba
  only where a measurement says it pays.
* Model and view spec under the model/UI split; plotted through chiplot, never
  pyqtgraph.
* Reuses rather than reimplements: the rate-matrix parameter group, the
  `PhotonBursts` layout and path marginalization, the FRET calibration
  corrections, the PDA Poisson-deviance statistic, the burst-companion writer, the
  prior/sampling stack.
