---
type: Architecture
title: The compute/display line — what may cross into Python
description: The standing rule across tttrlib, imp.bff and chisurf. Computation lives in C++ and the data stay there; only what a human looks at crosses into Python. The decision procedure, where it is enforced, and the measured distance from it today.
resource: chisurf/core/fitting/, imp.bff/include/, tttrlib/modules/
tags: [architecture, scope, layering, imp.bff, tttrlib, chisurf, fitting]
timestamp: '2026-09-01T00:00:00Z'
---

# Where to pick this up

The sequenced worklist for closing the remaining distance from this rule is
[PRD-105](../prds/prd-105.md) (2026-09-02): phase 0 is the seam's own defects
(the `Node` director-lifetime segfault `T-20260901-13`, BUG-10, one
expression engine), then the two gaps below, then the sampler loop, graph
eligibility per model family, the duplication register, and the chatty burst
paths. Work it through the board tickets it names.

# The rule

> **Keep it all in bff and tttrlib. Only the things that get displayed move
> into chisurf/Python — so that the data stay local.**

Stated by the owner on 2026-09-01, generalising what the fit graph had been
converging on model family by model family. It is one rule with two halves,
and the second half is the one that gets forgotten:

1. **Computation is C++.** A kernel, a curve, an objective, an optimiser, a
   graph algorithm belongs in `tttrlib` or `imp.bff`.
2. **The data stay where the computation is.** It is not enough for the
   arithmetic to be in C++ if the arrays are marshalled back and forth to
   drive it. A value crosses the boundary when a human is going to look at
   it, and at no other time.

This sits *on top of* the placement rule in
[`imp-ecosystem`](../references/imp-ecosystem.md) rather than replacing it.
That rule says **which** of the two C++ repositories a thing belongs to
(photons and curves → `tttrlib`, coordinates → `imp.bff`, neither →
`chisurf`). This one says **how much** may be in `chisurf` at all: the
application, not the arithmetic.

# The decision procedure

"Displayed" is doing a lot of work in the sentence, so it needs a test that
two people apply the same way. Ask **who consumes the value**:

| The consumer is… | Then it… | Examples |
|---|---|---|
| a human — a plot, a table, a label, a saved report | **crosses** | the fitted parameters, `chi2r`, the model curve a plot draws, an error bar |
| another computation | **must not cross** | residuals inside an objective, a Jacobian, a lifetime spectrum feeding a convolution, a covariance matrix, a distance distribution |
| a *decision* the application makes | **crosses, as the decision** | "did it converge", "which parameters are free", "which fit is selected" |

Two corollaries that decide most real cases:

* **A value that crosses once per `run()` is fine; the same value crossing
  once per iteration is the thing this rule exists to prevent.** The measured
  reason is in `imp.bff` `okf/log.md` 2026-09-01 (9): replacing the optimiser
  alone bought **1.02x**, because MINPACK's arithmetic is ~4% of a fit and
  the callback was 57%. Wrapping a Python callback in a C++ loop is a
  *regression* (0.99x). Only removing the crossing entirely helps.
* **Displaying a value is not licence to recompute it.** If the graph already
  produced the model curve, the plot reads it off the output port. Computing
  it a second time in Python is not a display step; it is a second
  implementation, and *two implementations of one algorithm do not average
  out, they disagree, and the disagreement is silent* — see the wrong
  `is_complete` that cost a treewidth of 3 where the answer is 1
  (`imp.bff` `okf/log.md` 2026-09-01 (13)).

# What stays in chisurf, legitimately

The rule is not "chisurf becomes empty". What the application owns is
**identity and intent**, which are not arithmetic:

* what a fit is, what a dataset is, which experiment produced it;
* which parameter belongs to which model, at which position of which flat
  vector, and what it is *called* (bff keys parameters, chisurf names them);
* discovery — walking models, resolving links, deciding which prior is more
  than its bounds;
* the run policy: selection, history, undo, when to fit and what to fit next;
* everything a view does with a number once it has one.

The line has a worked precedent in `pycmc`: `ARCHITECTURE.md` states it,
`check_split.py` enforces it mechanically and exits non-zero naming what
broke. The equivalent here is a test rather than a script —
`chisurf/test/architecture/test_bff_is_the_backend.py` — because the
provenance is checkable at runtime.

# Where it is enforced today

`test/architecture/test_bff_is_the_backend.py` pins the *provenance* of each
place a second implementation would be easy to grow back. None of it pins an
answer; the value tests live next to each subsystem.

| Asserted | Meaning |
|---|---|
| `Parameter._port` is a `bff.Port` | a parameter's value is not a Python float |
| a parameter link is `Port::set_link` | sharing a parameter is a graph edge |
| `FactorGraph.engine` is `bff.FactorGraph` | moralisation, cliques, treewidth are bff's |
| `F._bff_weighted_residuals is bff.weighted_residuals` | the residual kernel is bff's |
| `M.have_minimizer()` | `fit.run()` optimises in C++ |
| a representable fit builds one `bff.Minimizer` | and says so if it silently stops |
| `bff.Session.load` in `project.py` | the session format is bff's |
| `TcspcDecay` exists and `_lifetime_objective` survives | the decay curve is a node |
| the four spectrum producers exist and `_spectrum_chain` survives | the photophysics upstream of the decay is bff's |
| `MaxEntLifetimeModel` is refused | **being representable is not being represented** |

That last one is the sharpest and the newest. A graph that builds is only
good news if it is the *same model*: two lifetime subclasses were building
the plain multi-exponential graph while computing their spectrum elsewhere,
and the curves were 793.8 counts apart with nothing to say so. The scoreboard
is `imp.bff/test/minimizer/census_models.py`, which asks every ChiSurf model
class whether it builds a graph **and** whether that graph's curve is the one
`update_model()` returns.

# How far the code is from the rule, measured

Not an impression — `fit.run()` timed, and the Python model evaluations
inside it counted (2026-09-01, `arm64` env, 512 channels):

| fit | total | optimise | error estimate | rest | Python `update_model()` calls per `run()` |
|---|---|---|---|---|---|
| parse | 0.50 ms | 60% | 4% | 36% | **2** |
| TCSPC lifetime | 3.26 ms | 41% | **32%** | 27% | **7** (5 of them for the error estimate) |
| TCSPC VV | 4.51 ms | 44% | **34%** | 22% | **8** (6 for the error estimate) |
| FRET (Gaussian) | 24.3 ms | 80% | 12% | 8% | **9** (7 for the error estimate) |

The optimisation column is rule-compliant: zero crossings per iteration.
**This table predates `T-20260901-10`** (2026-09-01, later the same day),
which closed the error-estimate column: the Jacobian is now differenced over
the graph in C++ (`Minimizer::compute_covariance` / `compute_jacobian`, an
absolute-floor step `eps*max(|x|, 1)` chosen for exactly the near-zero
parameter that defeats MINPACK's relative step), all seven consumers moved
with it, and the count is **2 Python `update_model()` calls per `run()`
whatever the model** (was 7/8/9); the error estimate fell from 32–34% of a
fit to 0–2%. Re-measuring the table is a [PRD-105](../prds/prd-105.md)
phase-1 deliverable.

## The named gaps

1. **~~The covariance falls back to a numpy Jacobian.~~ Closed,
   `T-20260901-10`** — see above. `chisurf/core/math/optimization/leastsqbound.py`
   (794 lines) and the `lltf` plugin's copy (365) were deleted with it; the
   frozen reference lives at `imp.bff/test/minimizer/reference_leastsqbound.py`.
   One residue: the `ResidualNode` fallback this created for every
   graph-less model exposes a director-lifetime segfault, board
   `T-20260901-13` — the first item of PRD-105 phase 0.

2. **The model curve is recomputed for display rather than read.** The graph
   is private to the fit by design (a port written from C++ is not seen
   through `Parameter._frozen_value`), so the answer is written back through
   the ordinary setters and `model.update_model()` re-runs ChiSurf's own
   pipeline. For a lifetime model that pipeline calls tttrlib too, and the
   parity tests pin the two equal to ~1e-15 — but it is still a second
   composition of the same kernels, computed a second time, for a curve the
   graph already holds on an output port.

3. **The data are duplicated.** A `DataCurve` holds `x`, `y`, `ey` as numpy
   and `ChiSquared.set_data_arrays` copies them into the node. One copy per
   fit is cheap, but "the data stay local" is not literally true while there
   are two copies and Python owns one of them.

## What has not been asked yet

The models outside the decay families — DEER, ICS, PCH/FIDA, PDA2C/3C, MFD,
and the structure model — have not been examined against this rule at all.
Board tickets `T-20260901-08` (the FRET distance distributions that still
have no node) and `T-20260901-09` (everything outside the decay families)
carry the work. The first question for each is not "port it" but *what is the
curve, and whose is it* — which is the [`imp-ecosystem`](../references/imp-ecosystem.md)
rule again, one layer down.
