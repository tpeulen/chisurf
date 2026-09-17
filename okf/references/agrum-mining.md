---
type: Reference
title: aGrUM/pyAgrum mining — what a mature graphical-model toolkit had for the stack's factor graph
description: Survey of the aGrUM/pyAgrum checkout. Its algorithms belong in imp.bff (owner ruling 2026-09-17), which now holds both harvests — exact linear-Gaussian inference through canonical forms (K, h, g) with variable elimination and aGrUM's triangulation (imp.bff PRD-151), and CTBN amalgamation for kinetic rate matrices (imp.bff PRD-150) — while ChiSurf consumes them. Records the correction that started it, what landed where, and every rejection with its reason.
tags: [reference, fitting, statistics, architecture, roadmap]
timestamp: '2026-09-17T18:00:00Z'
---

# aGrUM/pyAgrum mining — inference kernels, canonical forms, CTBN

aGrUM (Sorbonne Université / LIP6, dual `LGPL-3.0-or-later OR MIT`) is a C++
library for probabilistic graphical models with a Python wrapper, pyAgrum;
ChiSurf keeps a checkout at `junk/aGrUM` (version 3.0, commit 9f2905b60). It is
the mature toolkit the stack's factor-graph layer was architecturally modelled
on: a model object separate from the inference engine, moralisation plus
triangulation to expose blocks, relevance pruning per query.

**Home: imp.bff.** The owner ruled on 2026-09-17 that "agrum is bff domain, the
algos": whatever is harvested lands in imp.bff (C++, `IMP.bff.Inference*` and
`KineticNetwork`), and ChiSurf consumes it. This concept stays in the shared
bundle because the comparison spans both repositories; the design records are
imp.bff's `okf/prds/prd-150.md` (CTBN) and `okf/prds/prd-151.md` (linear-Gaussian
inference).

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

**Landed (2026-09-17), in imp.bff (PRD-151):**

- `IMP.bff.InferenceCanonicalForm` — aGrUM's `canonicalForm.py` in C++/Eigen
  under its meaning (product, divide, extend/augment, reduce ignoring
  out-of-scope evidence, marginalize, `fromCLG` as `from_linear_gaussian`), plus
  what ChiSurf's former `canonical.py` had and aGrUM lacks (`from_moments` with a
  mass, the log normaliser, log density, strict `condition`, ordered `marginal`,
  refusal of a repeated name), and multi-number variables.
- The trap in `toGaussian` is handled explicitly: a singular `K` is carried
  through product, conditioning and marginalisation; `get_rank` and
  `get_null_space` name the unconstrained directions; only the moments refuse,
  and integrating out an unconstrained block is refused as a divergent integral.
- `IMP.bff.InferenceGaussianElimination` — `CLGVariableElimination` over an
  `InferenceFactorGraph`, plus exact relevance pruning by evidence separation,
  which aGrUM's CLG code does not do.
- `InferenceFactorGraph::get_elimination_order("weighted")` — aGrUM's default
  triangulation (simplicial, almost simplicial under the treewidth bound, then
  Kjaerulff), with variable sizes as log domain sizes. Its quasi-simplicial phase
  turned out unreachable (an integer division in `_updateList_`).
- A/B against a pyagrum-free transcription (imp.bff
  `test/factorgraph/agrum_clg_reference.py`): algebra to 2.2e-16, posteriors to
  2.5e-14, orders identical; against the brute-force joint Gaussian, means
  3.6e-14, covariances 2.3e-13, log evidence 1.2e-14.

**The concrete gap, closed.** ChiSurf's `core/fitting/canonical.py` is deleted.
`GaussianEngine` holds the bff form; `LaplaceEngine.condition`
({src}`chisurf/core/fitting/engine.py#LaplaceEngine`) is a closed-form Schur
complement whenever one Jacobian at the conditional mode certifies it equals the
re-fit (inside the bounds, stationary, curvature unchanged), and re-fits with the
reason recorded otherwise; `profile` and `mcmc` re-optimise by design. The
certified answer matches a forced re-fit to 8e-9 sd on a linear model, and the
certificate refuses a weak second exponential held 2 sd out.

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

**Evaluated and landed (2026-09-17)** as `IMP.bff.KineticNetwork` (imp.bff
`include/KineticNetwork.h`, imp.bff PRD-150). Product schemes do occur, in three
places:

- the polarised smFRET simulator: conformation x emission mode, in
  `core/fluorescence/burst/simulate.py` `exchange_matrix_ms` /
  `photoselection_matrix`, with the index arithmetic and both transposes written by
  hand;
- conformation x photophysics for FCS saturation: PET/PIFE, the S1 decay conditioned
  on the conformation;
- donor x acceptor label kinetics, in imp.bff `fret_efficiency_exact_kinetic_pair`.

All three factor exactly. The tests reproduce the simulator's `k_nrad`/`k_rad` and a
6-state FCS dark/excitation pair from their factors, with 0.0 difference.

What does **not** factor:

- single-dye photophysics, where there is nothing to factor (Cy5's isomer and triplet
  both leave S1);
- energy transfer (imp.bff `PhotophysicsTransferKinetics`), because D*A -> DA* changes
  two variables in one event and amalgamation sets that to zero.

Conventions: bff is `K[target, source]`, C-order over the order the variables were
declared, with a derived diagonal. aGrUM's `toMatrix` is `Q[from, to]`, little-endian
over sorted names. `K = Q[perm][:, perm].T`, pinned by an A/B against a pyagrum-free
transcription: generators to 8.9e-16, `SimpleInference` posteriors to 1.6e-15.

## Not taken — re-evaluated for imp.bff (2026-09-17)

The list below was first written from ChiSurf's side; each item was re-checked
against what bff actually contains, and kept only with a bff-specific reason.

- **The discrete-table inference core** (`src/agrum/BN`, `MRF`). bff *does* have
  discrete latent states, so this was not dismissed on principle. Label and
  photophysical states are already exact as generators (`KineticNetwork`,
  `FRETExchange`), and the Ising chain is a transfer matrix. The one place an
  approximation stands where exact discrete inference could replace it is
  `rotamer_mean_field_weights_multi_probe`: labels on one structure form a
  pairwise MRF over conformers, solved by mean field. For two labels the exact
  joint is a single `n1 x n2` table and needs no library; whether it matters is
  a measurement, recorded under "Where to pick this up". Not a reason to keep
  aGrUM.
- **Credal networks** (`src/agrum/CN`): nothing in bff carries sets of
  distributions.
- **Bayes-ball** (`base/graphs/algorithms/generic/bayesBall*`): barren-node
  removal is exact only for normalised conditionals, and bff's factors are
  likelihoods; its graph is undirected. The exact undirected form — evidence
  separation — is in `InferenceGaussianElimination::get_relevant_factors`.
- **Structure learning** (`clg/learning.py`, the PC algorithm, Rademacher-bounded
  independence tests). Which parameters a factor couples is the fit's (which
  dataset reads which parameter), asserted by the user, never discovered — a fit
  whose shared parameters were discovered from the data is a much weaker claim
  than one where the sharing is a physical hypothesis.
- **CLG forward sampling, SEM text, notebooks**: bff samples posteriors, not
  generative networks; display is ChiSurf's.
- **`causal`, `causalEffectEstimation`**: bff models no interventions.
- **`explain`** (Shapley values over a Bayesian network): parameter influence in
  bff is curvature and profile likelihood (`BayesianLaplace`, `FitMinimizer`),
  and in ChiSurf the dependence view — the right tools for a continuous
  posterior.
- **The library as a dependency.** Never: take the *form*, write the code.

## Where to pick this up

1. **Per-dataset Gaussian factors for a global fit** (imp.bff PRD-151 Open 1).
   `GaussianEngine` builds one dense form over every parameter; a global fit's
   Laplace approximation factorises by dataset, and
   `IMP.bff.InferenceGaussianElimination` would condition and marginalise at the
   cost of the treewidth instead of the parameter count. Blocked on a
   per-local-fit curvature (the graph objective has the per-dataset residual
   blocks). Measure: conditional-query time against the dense form on a
   20-dataset star, answers equal to 1e-10. This is what gives the elimination a
   real caller; today it runs in tests only.
2. **Exact joint for multi-label rotamer weights** (PRD-151 Open 2). Compare
   `rotamer_mean_field_weights_multi_probe` with the exact `n1 x n2` joint on a
   shipped two-label structure — weights first, then `<R_DA>`/E. Decide on
   discrete exact or loopy inference only if the difference matters and three or
   more labels are common; either is textbook.
3. **CTBN adoption** (PRD-150 Open):
   - route `burst/simulate.py`'s `k_nrad`/`k_rad` through `KineticNetwork`;
   - offer "add a conformation" in the FCS kinetics model instead of a
     hand-written 2N-state matrix;
   - owner question, still open: should imp.bff's
     `fret_efficiency_exact_kinetic_pair` compose transition matrices (Kronecker
     product, today) or generators (Kronecker sum)? Behaviour unchanged until
     answered.
4. **`junk/aGrUM` can be deleted.** The CLG package and the triangulation are
   harvested, the CTBN package was earlier, the transcriptions and fixtures in
   imp.bff (`test/factorgraph/agrum_clg_reference.py`,
   `test/kinetics/agrum_ctbn_reference.py`) do not import it, and everything
   else is rejected above. Every file read carries its `CHISURF-*` header.
5. The structural half of the comparison was closed earlier: model/engine
   separation, junction tree, relevance pruning and the dependence view
   ([PRD-68](/prds/prd-68.md), [PRD-69](/prds/prd-69.md),
   [PRD-70](/prds/prd-70.md)); the algorithms themselves now run in
   `IMP.bff.InferenceFactorGraph`.
