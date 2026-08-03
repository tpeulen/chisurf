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

In progress. The static forward model is implemented and **milestone 1a has
passed** on a real measurement; kinetics and the photon-bearing sources are next.
The design below is settled; the staging is the order of work.

Both things this PRD recorded itself as blocked on are resolved:

* **The measurement.** `chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna/`
  is a real BH SPC-132 single-molecule DNA measurement — ten `.spc` files, 2980
  bursts, a clean donor-only population at `PR ≈ 0` and a FRET population at
  `PR ≈ 0.42`, separated on the lifetime axis exactly as an MFD plot should be
  (⟨t⟩ 5.04 ns against 4.20 ns). It carries no IRF file and no measured correction
  factors and needs neither: `chisurf/core/fluorescence/burst/irf_bg.py` takes both
  the per-detector instrument response *and* the background rate from the
  measurement's own **non-burst** photons.
* **The conventions.** The `G`/`l₁`/`l₂` authority is tttrlib
  (`include/DecayFit.h`, `DecayFit23/24/25.h`'s `corrections = [period, g, l1, l2,
  convolution_stop]`, and `SimEngine.h`'s Perrin depolarization), not a prior
  implementation to be reconstructed.

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

## Input: a burst folder and its photons

The fit's input is a **burst-analysis folder** plus the TTTR files it points back
into. There is no new on-disk format, no companion, and no separate 2D data file:
the nuisance measure is *already in the `.bur` tables*. Per detector `d`,
`chisurf/core/fluorescence/burst/table.py` writes

```
Duration (d) (ms)        = macro[last] − macro[first]   → the span t_c, exactly
Number of Photons (d)                                   → the counts, hence S
Mean Macrotime (d) (ms) ,  d Count Rate (KHz)
```

with `-1.0` / `0` already written for a detector a burst has nothing in — the
sentinel convention the companion contract asks for, present. `Duration (d)` is
the first-to-last photon span by construction, so the `(n−1)/(n+1)` shrinkage
discussed below applies to the column as written, with no new estimator. Where the
detector set is defined per polarization, the parallel/perpendicular counts are
there too.

What the folder does **not** yet carry is `⟨t⟩`: `.bur` is macro-time only, and
micro-times appear in the burst writer solely to select photons into detector
windows. `bg4` is not a substitute — it holds burst-wise *fitted* lifetimes, which
is the biased low-photon estimator this design exists to replace.

**So the burst writer is extended: `.bur` always carries the mean micro time per
detector, alongside the fitted values rather than instead of them.** A new
`Mean Microtime (d)` column per detector, computed over exactly the photon
selection the other per-detector columns use (detector window *and* micro-time
range, so a PIE-gated detector reports the mean within its own window), written
unconditionally by both writer paths — `write_bur_file_old` and the
`generate_burst_dataframe` / `write_bur_file_fast` path — with the same sentinel
as its neighbours for a detector a burst has nothing in. Two constraints on how it
lands: the column goes at the **end**, before the trailing blank column, so a
reader keying on leading positions rather than on header names is not shifted; and
the unit is fixed and documented (nanoseconds, not raw TAC channels) so the value
survives a change of micro-time resolution.

The mean micro time is a first moment — cheap to accumulate in the same pass that
already walks each burst's photons — so this costs essentially nothing at write
time and makes every burst folder carry its own lifetime axis from then on.

Photons are still read for the **pooled-decay and burst-wise sources**, which need
the individual micro times rather than their mean, and for legacy folders written
before the column existed. The fit reads them once at setup into the
`PhotonBursts` layout already in `chisurf/core/fluorescence/burst/gopich_szabo.py`
(concatenated channel and micro-time with per-burst offsets; ≈22 MB for 50 k
bursts of 150 photons, ≈600 MB for a million of 200). With the column present the
histogram source alone needs no photons at all; without it, the fit computes
`⟨t⟩` from the photon stream and says so, rather than degrading silently.

**Finding the TTTR files is a solved problem and must not be re-solved.**
`chisurf/core/fio/fluorescence/burst_manifest.py` records, per source file, the
container type, routing channels and macro/micro resolutions — captured while the
file was open, precisely so later consumers do not guess. The chain is
manifest (`Info/analysis.json`) → the legacy `Info/*.mti` sidecar → extension
sniffing, and the last step **must fail loudly**: that module documents the
failure it was written against, where `.spc` → `"SPC"` is not a container type
the reader accepts and the mistake surfaces not as an error but as *zero photons*,
so an analysis runs on nothing and looks like a measurement with no signal.

Everything binned — D12 as a histogram, the observed 2D histograms, the pooled
decay cube — is derived inside the fit and cached in memory, never persisted. The
binning belongs to the fit and is changeable without touching anything upstream; a
stored copy could only go stale against its own inputs.

## Preparation: one core, two surfaces

The pass that turns a burst folder into fit-ready arrays — resolve the TTTR
sources, read the `.bur` columns, load the photons, compute `⟨t⟩` per channel
group — lives in **core**, `chisurf/core/fluorescence/mfd/prepare.py`, Qt-free and
importing no plugin. Two thin surfaces sit over it:

* a **plugin tool** giving it the four standard surfaces — GUI, CLI, API and RPC —
  following the layered-plugin precedent of [PRD-09](prd-09.md), so a folder can be
  prepared and inspected on its own;
* the **experiment reader**, which calls the same core directly.

The reader deliberately does *not* shim through the plugin. It is data-loading
infrastructure on the path for every burst dataset, and routing it through plugin
discovery would let a disabled or broken plugin present as a data-loading failure.
One implementation, two callers, no dependency from core to plugin.

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

* **1a — static, single state, real data — ✅ passed.** Model core plus the
  histogram source, one state, no kinetics: the cloud's position *and* its width
  reproduced with **no free broadening parameter**. Any unexplained width will
  later be absorbed as exchange, so everything downstream is meaningless until this
  passes.

  What made it a real test rather than a self-consistency check is the **donor-only
  population**: it has no distance, no efficiency, and nothing fitted to its
  spread, so its width is shot noise and nothing else — and that width can be
  computed *from the photons themselves*, with no model at all. Against that
  model-free number, on `bh_spc132_sm_dna`:

  | quantity | model-free / measured | forward model |
  |---|---|---|
  | donor-only proximity-ratio width | 0.0215 (binomial estimate 0.0221) | 0.0208 |
  | donor-only ⟨t⟩ shot noise | 0.322 ns (from each burst's own photons) | 0.336 ns |
  | donor-only ⟨t⟩ *observed* | 0.464 ns | — |

  So the shot-noise contribution is reproduced to 3–4% on both axes with nothing
  tuned to it. The residual — 0.33 ns of excess on the lifetime axis, and a FRET
  population 1.3× broader in `PR` than shot noise — is **physical heterogeneity**,
  which is precisely the quantity this PRD exists to fit and which no shot-noise
  model should reproduce. The test therefore also asserts the model stays *below*
  the observed FRET width: a model that broadened itself to fit would absorb the
  structure everything downstream is meant to resolve.

  Fitted by least squares (position only — none of these is a width parameter):
  donor-only lifetime 1.57 ns, mean distance 54.4 Å at `R₀ = 52 Å`, donor-only
  fraction 0.394, donor leakage 0.030. `test/fluorescence/test_mfd_milestone.py`.
* **1b — known-rate kinetics recovered — ⏳ outstanding, no dataset.** A system
  whose exchange rate is known independently must come back correct, which is what
  exercises the occupation-time propagator and the span/duration lookup together.
  The tree contains no such measurement, so this gate stays open rather than
  quietly passing on simulated data. Until it can run, the propagator is held to
  its closed-form two-state limit and to convergence in the discretization — which
  tests the *implementation*, and explicitly not the physics.

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

# Open

One thing is still needed that the tree cannot supply:

* **A burst measurement whose exchange rate is known independently**, for milestone
  1b. Without it the occupation-time propagator is verified against its own
  closed-form limit and nothing more, and no fitted rate from this machinery should
  be reported as validated.

Two questions the static gate raised, both worth answering before rates are:

* **The instrument response taken from non-burst photons is contaminated.** Its
  mean sits at 3.44 ns, far later than a scatter prompt, because the non-burst
  stream also holds fluorescence from molecules below the burst threshold. The fit
  compensates with a donor-only lifetime of 1.57 ns, which is therefore an
  *effective* number and not the dye's. It does not affect milestone 1a, which is
  about width, but it will bias any absolute lifetime. A tighter prompt window, or
  a real scatter measurement, would settle it.
* **The excess width is unattributed.** It is real, and it is either a distribution
  of distances, acceptor photophysics, or exchange. Distinguishing them is what the
  pooled-decay and burst-wise sources exist for; until they are wired in, the
  static model should not be asked which it is.

# Staging

1. **Data side** — ✅ *landed*: the `.bur` writer emits
   `Mean Microtime (<detector>) (ns)` from both writer paths, appended after every
   pre-existing column and before the trailing blank, in nanoseconds, with the
   same `-1.0` sentinel as its neighbours when a detector has no photons or the
   header cannot supply a resolution (`test/fio/test_burst_mean_microtime.py`
   pins the values, the sentinels, the positional non-breakage, and that both the
   ChiSurf and companion readers still behave).
   Remaining: `prepare.py` in core with the TTTR-resolution chain and its
   fail-loudly-on-sniff behaviour; D12 straight from the `.bur` columns;
   `PhotonBursts` load path for the decay-bearing sources. Headless first, then
   the plugin's four surfaces.
2. **Static forward model** — ✅ *landed*, **milestone 1a passed**. `moments.py`
   (wrapped-exponential moments in closed form, plus the exact channel
   discretization — a TAC records a channel's *left edge*, and because an
   exponential is memoryless that offset subtracts exactly rather than as a
   half-channel approximation), `patterns.py` (non-central-chi `p(R)`, verified
   against a Monte-Carlo of two 3-D Gaussian clouds; per-state channel branching;
   sensitized-acceptor spectra), `histogram.py` (raw axes, the
   per-burst-conditioned nested background/partition sum), `sources.py`, `fit.py`.

   Three things learned in the doing, each of which would have been silent:
   - **The convolution is circular, not linear.** The TAC window *is* the period, so
     a pattern shifted later moves its mean by *less* than the shift — exactly
     `k·dt − T·(mass that wrapped)`. A linear convolution loses that mass outright.
   - **Components are photon-weighted, not amplitude-weighted.** A component's share
     of the photons is `aᵢτᵢ`; using `aᵢ` drags every distance distribution towards
     its high-FRET tail.
   - **Binning the nuisance measure costs no width.** Checked against the fully
     unbinned per-burst evaluation: identical to 1%, for a ~30× saving. It matters
     because that speed would otherwise have been bought with the very quantity
     milestone 1a tests.

   A model evaluation is 128 ms on this measurement (439 ms before caching the log
   factorials the nested sum asks for tens of thousands of times per evaluation).
3. **Kinetics** — transfer-matrix `P(f|T,K)` over the shared rate-matrix group,
   two-state closed form as its test. **Gate: milestone 1b — no dataset yet.**
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

* Compute core: `chisurf/core/fluorescence/mfd/` — Qt-free (`prepare.py`,
  `patterns.py`, `moments.py`, `occupation.py`, `histogram.py`, `sources.py`,
  `fit.py`), numba only where a measurement says it pays.
* Preparation surfaces: a layered plugin (GUI, CLI, API, RPC) and the experiment
  reader, both calling `prepare.py`; no dependency from core to plugin.
* Burst writer: `Mean Microtime (d)` added in
  `chisurf/core/fio/fluorescence/burst.py` (both writer paths).
* Model and view spec under the model/UI split; plotted through chiplot, never
  pyqtgraph.
* Reuses rather than reimplements: the rate-matrix parameter group, the
  `PhotonBursts` layout and path marginalization, the FRET calibration
  corrections, the PDA Poisson-deviance statistic, the burst-companion writer, the
  prior/sampling stack.
