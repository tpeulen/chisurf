---
type: PRD
prd: "65"
title: "PRD-65: Three-Colour Photon Distribution Analysis (tcPDA)"
description: A burst-wise three-colour PDA model — trinomial/binomial photon-partition likelihood with Poisson background, correlated trivariate distance distributions, labelling and brightness corrections, and MAP + MCMC inference with per-parameter priors, implemented in Python/numba with algorithmic rather than language-level speedups.
status: in-progress
phase: "unassigned"
resource: chisurf/core/models/pda3c/
tags: [prd, fret, pda, three-colour, bayesian]
timestamp: '2026-07-25T00:00:00Z'
---

# Summary

Three-colour smFRET measures three distances in the *same molecule at the same
time*, which is the only way to tell a coordinated conformational change from
three independent ones. Three-colour PDA (tcPDA) extracts those distances from
the shot-noise-broadened photon-count statistics of individual bursts. This PRD
adds it to ChiSurf as a new model family with its own compute core: a
**burst-wise likelihood** in which blue-excitation photons follow a *trinomial*
partition over three detection channels and green-excitation photons a
*binomial* one, each convolved with per-channel Poisson background; species are
**trivariate Gaussians over (R_GR, R_BG, R_BR) with a full covariance matrix**,
so inter-distance correlation is a fitted quantity rather than an assumption.
Inference is maximum-a-posteriori plus MCMC over per-parameter priors, reusing
the prior framework from [PRD-61](prd-61.md) and the sampler in
`chisurf/core/fitting/sample.py`. The compute core is **Python/numba and stays
there**: the incumbent reaches for threaded C and CUDA because it evaluates the
likelihood by brute force, whereas the cost here is attacked algorithmically —
collapsing duplicate bursts, and expressing *both* the grid sweep and the nested
background sum as matrix products, with Gauss–Hermite quadrature to replace the
uniform distance grid still to come.
Staged: forward model and its two-colour reduction first, then the 3-D static
fit, then priors/posteriors, corrections, global two-plus-three-colour fits, and
finally dynamics.

# Status

In progress. Split out of [PRD-50](prd-50.md) scope item 4 because — see *Why
not inside PRD-50* — it shares neither the compute engine, the data object, nor
the fit objective with two-colour PDA.

**Stage 1 landed (2026-07-25):** `chisurf/core/fluorescence/pda3c/likelihood.py`
— the trinomial/binomial partition with Poisson background, as two matrix
products (see *Performance strategy*), with an untruncated per-burst convolution
and a literal nested sum kept beside it as independent references.
`test/models/test_pda3c_likelihood.py` (18 tests) covers the factorisation
against the nested sum, normalisation over the count lattice, burst collapsing,
memory chunking, and the stage-1 acceptance criterion: **marginalised over the
photon-number distribution, the two-channel case reproduces `tttrlib.Pda`'s S1S2
matrix to a total variation below 1e-6** — a different algorithm for the same
quantity. Levers 1–3 measured; see the table below.

**Stage 2 landed (2026-07-25):** `physics.py` (competing/cascading transfer
pathways → channel probabilities, with a single detection matrix carrying
quantum yield, crosstalk and detector efficiency, plus direct excitation),
`species.py` (trivariate Gaussian, Cholesky parameterisation, nearest-PD repair,
Gauss–Hermite quadrature), and `model.py` (species mixture, burst table,
simulator, total log likelihood). `test/models/test_pda3c_model.py` (15 tests).

The **stage-2 acceptance criterion is met**, including the part that matters:

| | R_GR | R_BG | R_BR | ρ(GR,BG) |
|---|---|---|---|---|
| truth | 52.0 | 46.0 | 68.0 | 0.8 |
| recovered | 52.09 | 46.04 | 67.23 | **+0.767** |
| uncorrelated control (truth ρ=0) | 52.16 | 46.28 | 67.19 | **−0.000** |

6000 simulated bursts, 40/35 photons per excitation period, Nelder–Mead from a
deliberately displaced start, 5 quadrature nodes per axis, ~17 s. The control
matters as much as the fit: a method sold on measuring joint motion must be
shown *not* inventing correlation when there is none.

**A/B-verified against the incumbent (2026-07-25):**
`test/models/test_pda3c_pam_ab.py` transcribes the incumbent's MATLAB
expressions verbatim and asserts equality over randomised distances and
correction sets — the precedent set by
[fcs-pam-port](/references/fcs-pam-port.md) and `test_fcs_pam_ab.py`.
Agreement is to 1e-12 on `PBB`/`PBG`/`PBR` and `PGR` across 500 random
parameter sets, and the burst likelihood matches the incumbent's C kernel
term for term.

- **It found a real bug.** ChiSurf added direct excitation of G and R as *extra*
  emission weight, leaving the blue dye's share at 1; the incumbent scales every
  blue-excitation pathway by `pe_b = 1 - de_bg - de_br`. A laser pulse excites
  exactly one dye, so the probabilities **partition** — they do not top up.
  Because channel probabilities are normalised afterwards the error was
  invisible at zero direct excitation and grew with it: a silent bias in exactly
  the correction meant to remove one. Fixed, with a regression test that also
  checks the un-partitioned variant gives a *different* answer, so the test
  discriminates.
- **Two parameterisations, one physics.** The incumbent builds pairwise Förster
  efficiencies and combines them as `E1(1-E2)/(1-E1·E2)`; ChiSurf goes straight
  to `x_bg/(1+x_bg+x_br)`. Substituting `E = x/(1+x)` collapses one onto the
  other — verified numerically as well, since the identity is not obvious by
  inspection and either side could drift.
- **Corrections map cleanly.** The incumbent's loose scalars (`cr_bg`, `cr_br`,
  `cr_gr`, `gamma_bg`, `gamma_br`, `gamma_gr`) are exactly a lower-triangular
  detection matrix, and ChiSurf's single-matrix form enforces
  `gamma_bg = gamma_br/gamma_gr` structurally rather than storing two and
  deriving the third.
- **The no-`P(n)` convention is confirmed from source**, not inferred: the
  incumbent's kernel carries no photon-number weight, which is what ChiSurf's
  default `photon_number_pmf=None` reproduces.
- **One difference that is not a bug:** the incumbent's *simulator* carves
  background out of a fixed total burst size, while ChiSurf's adds it on top of
  a drawn signal (matching `tttrlib`'s convention for two colours). The
  *likelihoods* agree; this only concerns what the burst-size distribution
  means, and each is self-consistent.

**The reference's own C kernel, executed (2026-07-25).** The surrounding MATLAB
is inline in a GUI reading a global struct and has no callable entry point, and
the shipped MEX binaries are x86_64 MATLAB-ABI objects — but the kernel itself is
a self-contained MEX function with a plain numeric signature, so Octave's
`mkoctfile` compiles it from source on arm64 and it can be driven directly.
`test/models/test_pda3c_octave_ab.py` does exactly that and finds ChiSurf's
factorised likelihood agrees with the reference's nested-sum C to a **maximum
relative difference of 1.7e-14** — machine precision, on two genuinely different
algorithms for the same quantity. It skips cleanly when Octave or the reference
checkout is absent, so it is a bonus check on a developer machine rather than a
suite dependency.

Together the two A/B files cover both halves: the transcription checks the
*expressions* (which is where the excitation-partition bug was), the compiled
kernel checks the *arithmetic* (which is where a shared transcription mistake
would have hidden).

## Three matrices, not a pile of scalars

The physics is expressed as a composition of three linear maps in the
`(sources, detectors)` orientation the rest of ChiSurf already uses
(`chisurf/core/fluorescence/crosstalk.py`):

| matrix | shape | meaning |
|---|---|---|
| `excitation` | (lasers, dyes) | how a laser pulse distributes its excitation over the dyes. **Rows sum to one** — direct excitation is an off-diagonal, and the partition that the A/B caught is now structural rather than a special case. |
| `transfer` | (dyes, dyes) | probability that an excitation on dye *i* is finally emitted by dye *j*; built from the distances, upper triangular, accumulating relays. |
| `emission` | (dyes, channels) | probability that a photon from dye *d* is counted in channel *c*; quantum yield, filters, detector efficiency and bleed-through in one object. |

`excitation` and `emission` are **exactly** the two matrices the light-path
simulator's `get_crosstalk_matrices()` already emits (`laser × dye` and
`dye × detector`), so `ThreeColorSetup.from_crosstalk_matrices()` ingests a
simulated optical path directly instead of asking for hand-entered factors —
the light-path bridge that PRD-50 built for two colours, reused rather than
re-invented. The two-colour nuisance group spells the same quantities as scalars
(`ExDG`/`ExAG` are one excitation row; `gG`/`gR` the emission diagonal;
`cGD`/`cGA`/`cRD`/`cRA` its off-diagonals), and `from_scalars()` keeps that
vocabulary available.

Writing the transfer step as a matrix also removes the three-colour hard-coding:
it is built by a downhill recursion over any number of dyes, so a four-colour
construct needs no new algebra. Verified by the A/B: the matrix form reproduces
the incumbent's scalar-correction model to 1e-12.

Remaining: the ChiSurf model + view spec, the burst-table reader, and stages
3–7 (priors/MCMC, labelling and brightness corrections, global 2c+3c fits,
dynamics).

Parent: [PRD-49](prd-49.md) (three-colour PDA row). Related: [PRD-50](prd-50.md)
(two-colour PDA family), [PRD-61](prd-61.md) (parameter priors — the enabler),
[PRD-38](prd-38.md) / [PRD-40](prd-40.md) (model/view-spec split),
[PRD-04](prd-04.md) (burst pipeline), [PRD-53](prd-53.md) (simulation, for
ground truth).

# Motivation

Two-colour FRET gives one distance per molecule. Repeat it on three labelled
pairs and you get three distance *distributions* from three different molecules
— which cannot distinguish "the molecule breathes along one coordinate" from
"three regions move independently", because the joint distribution was never
observed. Three-colour FRET observes all three at once, and its payload is
precisely the **correlation** between them.

Recovering that payload from burst data is hard for the reason PDA exists at
all: with tens to hundreds of photons per burst, the observed count ratios are
dominated by shot noise, and in three colours the noise is a *multivariate*
partition. tcPDA computes that partition exactly and fits the underlying
distance distribution through it.

**Current state.** ChiSurf has no three-colour analysis of any kind
([PRD-49](prd-49.md) marks the row ABSENT). It has a mature two-colour PDA family
([PRD-50](prd-50.md)), a burst pipeline that already produces per-burst photon
tables, a light-path simulator with a three-colour, three-detector template and a
crosstalk-matrix builder, a complete per-parameter prior framework
([PRD-61](prd-61.md)), and a validated MCMC sampler. What is missing is the
three-colour forward model and the model/UI around it.

## Why not inside PRD-50

PRD-50 wraps `tttrlib.Pda`, whose entire API is two-channel: `background_ch1` /
`background_ch2`, a `pF` photon-number distribution, `set_probability_spectrum_ch1`,
and an `S1S2` matrix. There is no three-channel path and no meaningful way to add
one — the S1S2 convolution *is* the two-channel assumption. Three things differ:

| | two-colour PDA (PRD-50) | tcPDA (this PRD) |
|---|---|---|
| compute core | probability convolution → S1S2 count matrix | per-burst likelihood over the photon counts |
| data object | S1S2 histogram + `pF` | burst table of five per-burst counts |
| fit objective | statistic on a 1-D histogram projection | log-likelihood summed over bursts (MAP / posterior) |

They share physics (Förster, the correction factors, Gaussian distance
distributions) and should share those modules — not an engine.

# The forward model

**Excitation and detection.** Alternating (PIE/ALEX) blue and green excitation
with three detectors, giving five per-burst photon counts:

| symbol | excitation → detection |
|---|---|
| `F_BB` | blue → blue |
| `F_BG` | blue → green |
| `F_BR` | blue → red |
| `F_GG` | green → green |
| `F_GR` | green → red |

**Partition.** Under blue excitation a photon lands in one of three channels, so
the counts follow a **trinomial** with per-photon probabilities
$(p_{BB}, p_{BG}, p_{BR})$, $p_{BR}=1-p_{BB}-p_{BG}$. Under green excitation only
two channels are open, so a **binomial** with $p_{GR}$. The burst likelihood is
the product of the two.

**Background.** Each channel carries uncorrelated Poisson background. Rather than
approximating, the incumbent sums explicitly over how many of the observed counts
were background, from 0 to $\min(F_\text{ch}, N_{BG,\text{ch}})$ — a triple sum
for the trinomial term and a double sum for the binomial. That nested sum over
every burst and every grid point is the hot loop and drives the whole performance
design below.

**Probabilities from distances.** The three efficiencies $E_{BG}$, $E_{BR}$,
$E_{GR}$ follow from three distances through Förster, coupled: a blue-excited
donor may transfer to green *or* red, and an excited green may then transfer to
red, so $p_{BB}$, $p_{BG}$ and $p_{BR}$ are not independent functions of one
distance each. Detection efficiencies, spectral crosstalk, direct excitation and
quantum yields enter per dye pair, exactly as
`common.green_probability_from_efficiency` does for two colours.

**Species.** Each species is a **trivariate Gaussian** over $(R_{GR}, R_{BG},
R_{BR})$: an amplitude, three means, three widths, and three covariances
$\mathrm{cov}(BG,BR)$, $\mathrm{cov}(BG,GR)$, $\mathrm{cov}(BR,GR)$ — ten
parameters per species. The covariances are the scientific point of the method,
and they are also what makes the fit awkward: an optimiser stepping the six
covariance-matrix entries freely will leave the positive-definite cone, so each
evaluation must project onto the nearest symmetric positive-definite matrix (or
be reparameterised through a Cholesky factor, which is the cleaner option and
what this PRD proposes).

**Labelling.** A three-colour sample is never fully labelled; the missing-dye
subpopulations are large and structured (a molecule lacking red still emits blue
and green). One global labelling fraction `F_labeling` weights the fully- and
partially-labelled species. This is not a refinement — it is the dominant
systematic in three-colour work.

**Brightness.** Species of different brightness contribute different photon
budgets, so the photon-number distribution $P(N)$ is rescaled per species by a
relative-brightness ratio against a measured reference.

# Scope (staged)

Each stage is independently useful and independently testable.

1. **Forward model + two-colour reduction.** Qt-free trinomial/binomial
   likelihood with background summation, plus the 1-D "GR only" mode. Acceptance
   is the reduction itself: with blue switched off, tcPDA and the existing
   two-colour PDA must agree on the same data.
2. **Static 3-D fit.** *(Landed.)* Trivariate-Gaussian species
   (Cholesky-parameterised), multi-species mixtures, MAP fit against the burst
   likelihood. The 2-D (BG/BR) mode falls out as a restriction.

   One structural point worth stating because it is easy to get wrong and hard
   to notice: a burst's blue and green counts come from the **same molecule at
   the same distances**, so the two periods must be multiplied *before*
   averaging over the distance distribution. Averaging each period separately
   and multiplying afterwards models a molecule that re-randomises its
   conformation between the two pulses — which discards exactly the joint
   information the experiment exists to collect. A test pins the distinction.
3. **Priors + posterior.** Per-parameter priors ([PRD-61](prd-61.md)) exposed in
   the parameter table; MCMC posterior with credible intervals via
   `fitting/sample.py`.
4. **Corrections.** Labelling fraction and brightness reference.
5. **Global two-plus-three-colour fits.** Two-colour datasets fitted jointly with
   the three-colour one, each carrying its own dye pair, γ, crosstalk, direct
   excitation, R0, backgrounds and time-bin, with optional likelihood
   normalisation so a large dataset does not swamp a small one.
6. **Dynamic tcPDA.** Two-state exchange within the burst, by Monte-Carlo
   simulation of the occupation times (the three-colour analogue of
   `dynamic_mc.py`).
7. **Performance.** Interleaved with the stages above rather than bolted on at
   the end, but always behind a correctness reference — see *Performance
   strategy*.

# Design

- **Compute core** — `chisurf/core/fluorescence/pda3c/`, Qt-free, **NumPy +
  numba**, and that is the intended long-term home. Migrating to a tttrlib C++
  kernel is explicitly *not* the plan: the dynamic stage is simulation-driven, so
  a port would carry the Monte-Carlo machinery across the language boundary for a
  constant factor, and a constant factor is not where the cost is. The incumbent
  ships hand-threaded C plus a CUDA kernel because it evaluates the likelihood
  the expensive way; the answer here is to evaluate it a cheaper way. See
  *Performance strategy*.
- **Model + view spec** — `chisurf/core/models/pda3c/` following the
  [PRD-38](prd-38.md) split: a pure model plus `*.view.json`, rendered by
  `build_model_editor` → AutoForm. Species are a `dynamic_group` in
  `"style": "table"` (ten columns per row); the covariance block gets a compact
  matrix editor, reusing the existing `rate_matrix` section pattern rather than a
  new bespoke widget.
- **Priors in the table.** The incumbent's parameter table is
  `Value | Fix | LB | UB | Prior? | Prior μ | Prior σ`. ChiSurf already has the
  priors ([PRD-61](prd-61.md), stored on the chinet Port with a per-parameter
  selector); what is missing is the *column*. Add prior columns to
  `parameter_table.COLUMN_META` as an opt-in set, so every model that wants a
  Bayesian workflow gets them — not just this one.
- **Data** — a `pda3c` experiment reader producing the five-count burst table
  from TTTR files given PIE micro-time windows and three detector channels,
  mirroring `chisurf/core/experiments/pda/reader.py` but emitting a burst table
  instead of an S1S2 matrix. Consume `burst_selection` tables and
  MMFDB-registered datasets through `ChiSurfAPI`, not globals.
- **Corrections from the light path.** The three-colour, three-detector
  light-path template and `get_crosstalk_matrices()` already produce the
  per-pair detection/crosstalk description; extend
  `common.apply_lightpath_to_nuisance` to the three-dye case rather than asking
  users to type nine correction factors.
- **Shared with two colours.** Förster conversion, the correction-factor
  algebra, the `FRETParameters` group, the distance-distribution plumbing and
  the burst readers are shared with [PRD-50](prd-50.md); factor upward into
  `models/pda/common.py` rather than copying.

# Performance strategy

The naive cost is (bursts) × (distance-grid points) × (nested background sum),
and the incumbent pays all three — hence its threaded C and CUDA kernels. Each
factor can be attacked algorithmically instead, in Python/numba. These are exact
reformulations, not approximations, except where noted.

1. **Collapse identical bursts.** The likelihood depends on a burst only through
   its five counts, so bursts sharing a count tuple share a value. Group by
   `(F_BB, F_BG, F_BR, F_GG, F_GR)` and evaluate once per *unique* tuple with a
   multiplicity weight. Exact and free.

   **How much it buys is entirely data-dependent, and the first estimate here
   was too optimistic.** On three channels at ~25 photons per burst it is
   26× at 100k bursts and still climbing, because the reachable count vectors
   saturate while the bursts do not. On the *full five-count* three-colour
   problem at 40+35 photons it is worth almost nothing — 6000 bursts collapsed
   to 5993 distinct vectors — because the count lattice is five-dimensional and
   far larger than the dataset. So: keep it (it costs one `np.unique` and can
   only help), rely on it for the small-count and two-colour paths, and do not
   count on it for realistic three-colour burst sizes.
2. **Make the grid evaluation a matrix product.** Ignoring background, the
   log-likelihood is $\sum_\text{ch} F_\text{ch}\log p_\text{ch}$ plus a
   burst-only multinomial coefficient. Over all tuples and all grid points that
   is one GEMM: `(n_tuples × 5) @ (5 × n_grid)`. Precompute the log-coefficients
   once (the incumbent's "binomial coefficient library", the same idea). This is
   the fast path and also the correctness reference for the general one.
3. **Background as a second matrix product, not a nested sum.** *(Landed — and
   it goes further than this PRD first claimed.)* Only one thing couples the
   channels in the nested sum: the multinomial's leading $n!$, which depends on
   the *total* background count $m$ and not on how it is distributed. Dividing
   through by the zero-background term and grouping by $m$ leaves a product of
   per-channel series $u_c(b)=\mathrm{Pois}(b;B_c)\frac{F_c!}{(F_c-b)!}p_c^{-b}$
   — a discrete convolution. But $u_c$ splits into a burst-determined factor
   times $p_c^{-b}$, so the whole box sum is a **GEMM** between a
   (bursts × box) and a (points × box) array. The background therefore costs the
   same *kind* of operation as the signal term, and the two compose: with no
   background the correction is exactly 1.

   **The truncation claim in the first draft of this PRD was wrong**, and it
   caused a real bug before the tests caught it. The series may *not* be cut on
   Poisson tail mass: after folding in the weight $w_m$ the terms behave like
   $\mathrm{Pois}(b;B_c)\,(F_c/(Np_c))^b$, and wherever a channel collected far
   more photons than the model allows, that ratio is large and the terms *grow*
   for many steps before the Poisson factor turns them over — precisely where
   the background explanation carries the entire likelihood. Cutting on
   $\mathrm{Pois}(b;B_c)$ moved one test burst's log-likelihood by 3. The cutoff
   now uses an **effective rate** $B_c \max(F_c/(N p_c))$, which is ~1 near the
   optimum and large exactly where it must be. This matters even though the
   absolute likelihood there is negligible: MCMC and support-plane scans read
   the *shape* of the surface away from the optimum.
4. **Quadrature instead of a uniform distance grid.** The species *is* a
   trivariate Gaussian, so integrating it on a uniform 3-D grid is the wrong
   quadrature: cost is $O(n^3)$ in the grid resolution. Transform by the
   Cholesky factor and use Gauss–Hermite nodes, which are built for exactly this
   weight — a handful of nodes per axis instead of tens, i.e. orders of magnitude
   fewer likelihood evaluations at equal or better accuracy. This is the single
   largest lever and has no counterpart in the incumbent. It is an approximation
   in the same sense the grid is, and must be validated against a dense grid at
   fixed parameters as part of stage 2.
5. **numba only where the shape resists vectorisation.** With (1)–(4) the hot
   loop is small and regular; `@njit(parallel=True)` over the tuple × node loop
   with precomputed log-coefficients is enough. Keep a plain-NumPy reference
   implementation beside it and test them against each other, so the JIT path is
   never the only definition of the model.

Order of work: correctness first via (2) as the no-background reference, then
(1) and (3), then (4) with its accuracy check, then numba. Record measured
timings in the PRD as each lands, so "it is too slow" is never an unmeasured
claim.

## Measured (2026-07-25, `chisurf/core/fluorescence/pda3c/`, levers 1–3)

Pure NumPy, no numba, one core, on synthetic three-colour bursts (mean 25
photons) against a 200-point model grid:

| | |
|---|---|
| burst collapsing, 10k / 100k bursts | 4.8× / **26× fewer evaluations**, and rising — distinct count vectors saturate near 3.9k while bursts do not |
| convolution vs. nested sum, one burst | 24 ms → 0.32 ms (**75×**), identical to 1e-10 |
| zero-background grid, 2.5k × 200 | **22 ms** (43 ns/cell) |
| with background, per-cell loop | 333 µs/cell → ~170 s extrapolated for 100k bursts |
| with background, GEMM factorisation | **2.3 s** for 100k bursts × 200 points (~70× the loop) |

The 2.3 s figure is *after* the truncation fix, which cost ~5× against the
earlier (wrong) 0.42 s, and it uses a deliberately pessimistic random grid
containing near-zero channel probabilities; a real distance grid is better
conditioned. The conclusion stands and is the premise of this PRD: **the
algorithm was the cost, not the language.** Numba (lever 5) and quadrature
(lever 4) are not yet needed, and the C/CUDA the incumbent requires is not on
the table.

# Reuse

- [PRD-61](prd-61.md) priors (`chisurf/core/fitting/priors.py`,
  `Parameter.prior`) — the Bayesian layer already exists.
- `chisurf/core/fitting/sample.py` — `walk_mcmc` (adaptive proposals, corrected
  Metropolis acceptance) and `sample_emcee`; validated against an analytic
  posterior and against two-colour PDA support-plane intervals.
- `chisurf/core/models/pda/` — correction factors, Förster conversion, Gaussian
  distance machinery, light-path bridge.
- `burst_selection` / `burst_analysis` — per-burst photon tables, PIE channels.
- `plugins/core/lightpath_simulator` — `3-color-3-detector` template and the
  crosstalk-matrix builder.
- `chisurf/gui/autoform/` + `sections/` — declarative UI; extend
  `parameter_table` with prior columns instead of writing a bespoke table.
- [PRD-53](prd-53.md) / `tttrlib.SimEngine` — synthetic three-colour burst data
  for the acceptance tests.

# Acceptance

Headless throughout, following the [PRD-50](prd-50.md) pattern.

- **Reduction (stage 1).** With the blue channel disabled, the tcPDA likelihood
  and the existing two-colour PDA agree on the same burst data to within
  numerical tolerance. This is the strongest available check on the forward
  model, because it tests it against an independently validated implementation.
- **Background.** The explicit background summation is validated against a
  direct Monte-Carlo draw of signal-plus-background bursts, converging as
  $1/\sqrt{n}$ (the convention `consistency.py` already uses).
- **Recovery (stage 2).** A synthetic three-colour burst set generated at known
  $(R_{GR}, R_{BG}, R_{BR})$ and a known covariance is fitted and recovers all
  three distances within tolerance — **and** recovers the sign and rough
  magnitude of the correlation, with an uncorrelated control fitting to
  covariances consistent with zero. A method whose whole point is correlation
  must be tested on correlation.
- **Posterior (stage 3).** MCMC credible intervals bracket the truth and agree
  with a support-plane scan where both apply.
- **Labelling (stage 4).** A synthetic set with a known labelling fraction
  recovers it, and the distances recovered with the correction applied are
  closer to truth than without it.
- **UI.** The model appears in the add-fit combobox and renders its parameter
  groups, covariance editor and plots from `view.json` with no empty groups or
  crashes (the `test-model-editor` seam).
- **Performance shortcuts are exact.** Every optimisation in *Performance
  strategy* is tested against the reference it replaces: burst grouping against
  ungrouped evaluation, the convolution background against the nested sum, the
  Gauss–Hermite quadrature against a dense grid, and the numba kernel against
  its NumPy twin. A speedup that changes the answer is a bug, and the tests are
  what say so.

# Non-goals

- No bespoke Qt widgets ([PRD-49](prd-49.md) AutoForm mandate).
- **No C++/CUDA port.** The compute core stays Python/numba. If it is too slow,
  the answer is a better algorithm, not a faster language — and the dynamic
  stage is simulation-driven, which a port would not help.
- Not reimplementing two-colour PDA; `tttrlib.Pda` stays the two-colour engine.
- Four-colour FRET and homo-FRET are out of scope.
- Time-binned dynamic PDA for *two* colours stays in [PRD-50](prd-50.md).

# Relationships

- Child of [PRD-49](prd-49.md); takes over its three-colour PDA row and
  [PRD-50](prd-50.md)'s scope item 4.
- Depends on [PRD-61](prd-61.md) for priors and on the corrected sampler
  recorded in [PRD-50](prd-50.md).
- Renders via [GUI & AutoForm](/subsystems/gui-autoform.md); reads datasets
  through the [core target](/specs/core.md) rather than globals.
- Physics background: [PDA theory](/references/pda-theory.md) covers the
  two-colour forward model this generalises.
