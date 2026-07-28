---
type: Subsystem
title: "Hidden Markov models"
description: The in-tree Gaussian HMM in chisurf/core/math/hmm.py — Baum-Welch with a fused compiled E-step, data-driven initialisation and SQUAREM acceleration — and the shared analysis seam in the hmm plugin that every state-reporting tool calls.
resource: chisurf/core/math/hmm.py
tags: [subsystems, hmm, kinetics, math, plugins]
timestamp: '2026-07-28T00:00:00Z'
---

# Hidden Markov models

A binned trace that steps between levels is described by a hidden Markov model:
a chain of unobserved states, one multivariate normal emission per state. The
estimator lives in `chisurf/core/math/hmm.py`; the analysis built on it — state
ordering, dwell times, transition rates, model selection — lives in the `hmm`
plugin and is what every other tool calls.

## Two layers, and why

**`chisurf.core.math.hmm.GaussianHMM`** is the estimator: fit, score, decode,
sample, AIC/BIC. Its surface deliberately matches the vocabulary anyone coming
from a general HMM library expects (`n_components`, `covariance_type`,
`transmat_`, `predict`), because that is the vocabulary the literature uses.

**`chisurf.plugins.core.hmm.core`** is the *analysis*: it relabels states
dimmest-first, defines a dwell time (never continued across a sequence
boundary), converts a transition matrix into rates, and scans state counts. Two
tools that both drive the estimator directly would disagree on all four; that is
why the plugin core, not the estimator, is the seam. The GUI tool, the
`csg-hmm` CLI, the `hmm.fit`/`hmm.scan` RPC methods and the intensity-trace
tool all go through it.

## Why it is in-tree

It replaced an external HMM package (`hmmlearn`), and the replacement is
faster on every measured case — 1.1× to 18× per E-step, 2× to 10× end to end
(see [benchmarks](/references/benchmarks.md)) — while reaching an equal or
better optimum. Three decisions account for that:

1. **One fused backward sweep.** The backward lattice, the state posteriors and
   the expected transition counts all need
   `log a_ij + log b_j(x_{t+1}) + beta_{t+1}(j)`. The numba kernel
   (`_backward_posteriors_xi`) computes and exponentiates it once instead of
   making three passes, and keeps two rows of the backward lattice alive rather
   than the whole `(T, K)` array.
2. **Data-driven initialisation.** Every parameter starts from one k-means
   clustering read as a hard-assignment state path: centres → means,
   per-cluster scatter → covariances, label transitions → transition matrix.
   The textbook random Dirichlet draw ignores the data *and* can contain exact
   zeros, which the M-step then preserves forever — a state that can never be
   entered again. That was observed to merge two well-separated states into one
   wide blob.
3. **SQUAREM acceleration** (Varadhan & Roland scheme S3, the same accelerator
   as the photon-by-photon H2MM optimiser), on by default. It reaches the *same*
   fixed point in a fraction of the maps where EM crawls — overlapping states —
   and is abandoned automatically after several cycles that gain less than a
   plain EM step would.

## Invariants worth keeping

* **Log space throughout.** Forward, backward and Viterbi all run on
  log-probabilities, so trace length cannot underflow.
* **A frame no state can explain gets a uniform posterior.** All `-inf` minus
  its own maximum is `nan`, and one `nan` poisons every later iteration through
  the M-step. The `-inf` log-likelihood still reports the problem upstream.
* **A state with no posterior mass keeps its parameters.** Fitting more states
  than the data supports is normal; it must degrade, not produce `nan`.
* **Structural zeros are honoured, accidental ones are not.** A zero in the
  transition matrix is preserved by the M-step (that is how a constrained model
  stays constrained), so nothing in the initialisation or in SQUAREM's
  projection is allowed to *create* one.

## Related

* [Fitting engine](/subsystems/fitting.md) — the other estimator family.
* Photon-by-photon kinetics (H2MM, `burst_h2mm`) — no binning; the variational
  counterpart for many short traces is the ebFRET plugin.
* [Benchmarks](/references/benchmarks.md) — measured cost and the reasoning behind it.
