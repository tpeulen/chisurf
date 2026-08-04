---
type: PRD
prd: "77"
title: "PRD-77: One HMM — retire the in-tree Gaussian HMM onto the simulation library"
description: ChiSurf's binned-trace GaussianHMM is the last HMM in the tree that does not delegate to the TTTR library. Adopt a Gaussian emission added there (tttrlib PRD-013) so that both the photon-by-photon and the binned-trace models come from one implementation, and keep the in-tree one until a ground-truth recovery test and an honest benchmark both pass.
status: draft
phase: "unassigned"
resource: chisurf/core/math/hmm.py
tags: [prd, hmm, ebfret, kinetics, dedup, tttrlib]
timestamp: '2026-08-04T00:00:00Z'
---

# Summary

ChiSurf now has **one** HMM that implements its own inference: `core/math/hmm.py`'s
`GaussianHMM`, the binned-trace model behind `burst_ebfret` and `plugins/core/hmm`. The
photon-by-photon side already delegates — the EM engines go through `h2mm_tttrlib`, and
both of its samplers were retired onto the library.

This PRD closes the gap by adopting a Gaussian emission added to the library's existing
HMM core, and it is **paired with tttrlib PRD-013**
(`/Users/tpeulen/dev/tttrlib/PRDs/PRD-013-gaussian-emission-hmm.md`). Neither is useful
alone: PRD-013 has no consumer without this, and this removes a working capability without
that.

# Problem

The two HMMs are **different models**, which is why this is not a rename:

| | observation | emission |
|---|---|---|
| library (photon HMM, PRD-011) | one photon | categorical over detection streams |
| ChiSurf `GaussianHMM` | one time bin | Gaussian over a continuous value |

So the library cannot replace it today — there is no Gaussian emission there, and the
"Gaussian" names it does export are priors and a fitting result. That is the gap PRD-013
fills.

The reason to close it is the reason the rest of this work existed: the same physics
written twice drifts, and the drift is silent. This tree has already produced a
donor-weighting defect present in two scoring sources that agreed with each other
throughout, a window assumption shared by two forward models, and an entire compiled
backend disabled by a rename that no test noticed.

# What this is not

`GaussianHMM` is **not** a bad implementation to be swept away. It was written to drop
`hmmlearn` and is 1.1–18× faster per E-step than what it replaced. It is the faster
implementation of its model, and that is exactly the situation where a migration on
tidiness alone makes things worse — see the `_fast_simulate` case, where a second sampler
existed for a good stated reason that stopped being true, and only a benchmark settled it.

So this PRD does not begin by deleting anything.

# Goals

* **G1 — adopt.** `GaussianHMM`'s callers reach the library's Gaussian emission through
  the same gate pattern every other backend here uses, with the in-tree implementation as
  the fallback.
* **G2 — prove it on ground truth, not on agreement.** A known two-state Gaussian model
  recovered from simulated traces. Agreement between the two implementations is a weaker
  statement and is not sufficient on its own.
* **G3 — benchmark, and report it either way.** If the library's is not faster, say so in
  `docs/development/benchmarks.md` and **do not migrate**. A slower shared implementation
  is a real cost paid for an abstract benefit.
* **G4 — guardrail.** The new gate joins `test/architecture/test_optional_backends.py`, so
  a future rename cannot silently drop callers back to the fallback the way the H2MM
  backend was silently disabled.
* **G5 — retire only then.** `core/math/hmm.py` is removed once G2 and G3 both pass, and
  the OKF record says what it did, as was done for the retired simulators.

# Consumers to carry

* `chisurf/plugins/burst/burst_ebfret/` — including its VBEM path, which the library does
  **not** cover (PRD-013 explicitly excludes variational Bayes). If the VBEM path needs
  `GaussianHMM` internals, this PRD keeps them and narrows to the EM path.
* `chisurf/plugins/core/hmm/` — the shared plugin core.

# Acceptance

* Ground-truth recovery of means, covariances and transition matrix, including a
  poorly-separated case asserted as *uncertain* rather than as wrong.
* A benchmark in `docs/development/benchmarks.md` reporting quality next to time, per that
  page's convention.
* `test_optional_backends` covers the new gate.
* Both repositories' suites green, and the pairing recorded in `okf/log.md`.

# Sequencing

Implement tttrlib PRD-013 first, adopt here second, delete third — and only after the
benchmark. The two merge together; ChiSurf must never be between "removed its own" and
"has the library's".
