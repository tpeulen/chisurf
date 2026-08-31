---
type: Reference
title: aGrUM/pyAgrum mining — what a mature graphical-model toolkit has that ChiSurf's factor graph does not
description: Survey of the aGrUM/pyAgrum checkout against chisurf's factor-graph layer. Records the correction that matters most — continuous linear-Gaussian inference through canonical forms (K, h, g) is exact and does transfer, contradicting a claim that had propagated from a PRD into the shipped source and the docs — plus the CTBN amalgamation lead for kinetic rate matrices, and what was deliberately skipped.
tags: [reference, fitting, statistics, architecture, roadmap]
timestamp: '2026-08-31T00:00:00Z'
---

# aGrUM/pyAgrum mining — inference kernels, canonical forms, CTBN

aGrUM (Sorbonne Université / LIP6, dual `LGPL-3.0-or-later OR MIT`) is a C++
library for probabilistic graphical models with a Python wrapper, pyAgrum;
ChiSurf keeps a checkout at `junk/aGrUM` (version 3.0). It is the mature
toolkit that ChiSurf's own factor-graph layer,
{src}`chisurf/core/fitting/factorgraph.py`, was architecturally modelled on:
a model object separate from the inference engine, moralisation plus
triangulation to expose blocks, relevance pruning per query.

**This concept exists because the comparison had no home.** It was referenced
from `okf/log.md` as "the aGrUM comparison" by later entries that closed gaps it
had named, but the comparison itself was never written down anywhere a session
could read it. A dated log bullet records *that something happened*; it does not
tell the next session what the finding was.

## The correction: continuous inference does transfer

The claim, as it stood in [PRD-68](/prds/prd-68.md), in the module docstring of
`factorgraph.py`, and (briefly) in `docs/concepts/factor_graphs.md`:

> Those toolkits' inference kernels are discrete-table sum-product and do not
> transfer to a continuous fluorescence posterior; the structural machinery
> transfers exactly.

The second half is right. The first half is **wrong without the "discrete-table"
qualifier**, and the qualifier is doing all the work. pyAgrum ships a
Conditional Linear Gaussian package (`wrappers/pyagrum/pyLibs/clg/`) that does
**exact inference on continuous variables**, and its kernel is sum-product
variable elimination over a junction tree — the same structural machinery
ChiSurf already builds.

The representation is the *canonical form* (`clg/canonicalForm.py`), a factor
written in the precision/information parameterisation

$$\phi(x) = \exp\bigl(-\tfrac12 x^\top K x + h^\top x + g\bigr),$$

carried as `CanonicalForm(scope, K, h, g)`. The three operations sum-product
needs are then linear algebra, and the source is worth reading for how little
code they are:

| operation | method | what it computes |
| --- | --- | --- |
| product of factors | `__mul__` | add `K`, `h`, `g` on aligned scopes |
| condition on evidence | `reduce` | slice out the observed block |
| marginalise `y` out | `marginalize` | Schur complement `K_xx − K_xy K_yy⁻¹ K_yx` |
| back to moments | `toGaussian` | only defined when `K` is invertible |

`clg/variableElimination.py` runs elimination over these. Nothing is sampled and
nothing is re-fitted.

**Why this applies to ChiSurf rather than being a curiosity.** A fluorescence
posterior is linear-Gaussian near its optimum, and *exactly* Gaussian in the
parameters that enter linearly — amplitudes, offsets, scatter fractions. In that
form, conditioning and marginalisation are closed-form matrix operations.

**The concrete gap.** `PosteriorEngine.condition`
({src}`chisurf/core/fitting/engine.py#PosteriorEngine`) fixes a parameter and
**re-optimises the rest**, so every conditioning query costs a full fit. In
canonical form the same answer is a Schur complement. That is the single
highest-value thing to take from this checkout, and it is not taken yet.

Note the trap in `toGaussian`: the canonical form is closed under product and
marginalisation even when `K` is singular, but converting back to a mean and
covariance is not. A factor over a parameter the data does not constrain has a
singular `K` — which is the *informative* case, not an error to guard away.

## The second lead: CTBN amalgamation for rate matrices

`wrappers/pyagrum/pyLibs/ctbn/` implements continuous-time Bayesian networks.
Its unit is the **conditional intensity matrix** (`CIM.py`), and its composition
operator is `amalgamate` (spelled `*`), which merges per-variable CIMs into the
joint generator of the whole system.

ChiSurf writes kinetic rate matrices by hand in
{src}`chisurf/core/fitting/kinetics.py` (`K[target, source]`). Where a scheme is
a *product* of weakly-coupled processes — a conformational state crossed with a
photophysical one, say — amalgamation is the factored construction of the joint
generator instead of writing the full matrix out. Worth evaluating against the
schemes that actually occur before building anything: the win is only real if
schemes in practice factor, and a hand-written matrix for a 3-state system is
not a problem worth solving.

## Deliberately not taken

- **The discrete-table inference core** (`src/agrum/BN`, `MRF`, `CN`). This is
  the part that genuinely does not transfer: tensors over finite domains.
- **Structure learning** (`clg/learning.py`, the PC algorithm, Rademacher-bounded
  independence tests). ChiSurf's linking scheme is *asserted by the user*, and it
  should stay that way — a fit whose shared parameters were discovered from the
  data is a different and much weaker claim than one where the sharing is a
  physical hypothesis. Recorded as a rejection, not an oversight.
- **`causal`, `causalEffectEstimation`** — do-calculus and treatment effects have
  no counterpart here.
- **`explain`** (Shapley values over a Bayesian network). Parameter influence in
  ChiSurf is already answered by the profile likelihood and the dependence view,
  which are the right tools for a continuous posterior.
- **The library as a dependency.** The MIT half of the dual licence would permit
  it, but the structural layer ChiSurf needed was ~150 lines over the in-tree
  graph primitives, and taking a C++ PGM toolkit to get a Schur complement would
  be the wrong trade. Take the *form*, write the code.

## Where to pick this up

1. **Canonical-form conditioning.** Implement `(K, h, g)` factors and make
   `PosteriorEngine.condition` a Schur complement in the linear-Gaussian case,
   falling back to the current re-optimisation otherwise. The measurement is
   query cost against the existing re-fit path, and the correctness check is
   that a conditioned marginal differs from the unconditioned one for a
   correlated pair — the exact bug that was found in `condition` before, where
   it pinned the value and reported the unconditioned answer.
2. **Decide the CTBN question** by looking at real schemes, not in the abstract.
3. The structural half of the comparison is **closed**: model/engine separation,
   junction tree, relevance pruning and the dependence view all landed
   ([PRD-68](/prds/prd-68.md), [PRD-69](/prds/prd-69.md),
   [PRD-70](/prds/prd-70.md)).
