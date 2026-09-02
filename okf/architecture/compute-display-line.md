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
[PRD-105](../prds/prd-105.md). State as of 2026-09-02 evening: phases 0–2
are complete, phase 1's measured gaps are all closed or measured-and-queued
(see below), and phase 3 is complete except the FCS composition layer and
the nested-optimiser deletions. What remains on the PRD: phases 4–6
(duplication register, batching the chatty burst paths, the
all-three-repos cleanliness pass) and the queued owner decisions it lists.
Work it through the board tickets it names.

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
inside it counted. Re-measured **2026-09-02 evening** (`arm64` env, 512
channels; the 2026-09-01 columns kept for the distance travelled):

| fit | total 09-01 | total 09-02 | `update_model()`/`run()` 09-01 → 09-02 |
|---|---|---|---|
| parse | 0.50 ms | 0.51 ms | 2 → **1** (the display refresh) |
| TCSPC lifetime | 3.26 ms | 2.06 ms | 7 → **0** |
| TCSPC VV | 4.51 ms | ~8–16 ms* | 8 → **0** |
| FRET (Gaussian) | 24.3 ms | 7.11 ms | 9 → **0** |

The crossing count is the rule's column, and it is **zero for every decay
fit**: parameters go in through the ports, the curve and the autoscaled
`n0` come off the node (`_publish_curve`), and nothing Python owns is
consulted between `run()`'s first and last line. (*The VV row's wall time
is fixture- and iteration-count-sensitive across sessions — the same
fixture measured paired on 2026-09-02 gives graph 15.9 ms vs director
136.1 ms, an 8.5× win — so read the crossings column, not row-to-row wall
time.) Two families that could not build a graph at all on 2026-09-01 now
do: both ICS models (model-declared axes, `graph_axes()`) and any decay
with pile-up or a DNL table armed.

## The named gaps

1. **~~The covariance falls back to a numpy Jacobian.~~ Closed,
   `T-20260901-10`.** `leastsqbound.py` (794 lines) and the `lltf` copy
   (365) deleted; frozen reference at
   `imp.bff/test/minimizer/reference_leastsqbound.py`. The director
   segfault it exposed was fixed in phase 0 (`T-20260901-13`, the
   `%pythonappend` keepalive).

2. **~~The model curve is recomputed for display rather than read.~~
   Closed, `T-20260901-11`** (2026-09-02, both halves): the ports are set
   to the solution, the node re-evaluated in C++, and the curve **and**
   `n0` read off together — publishing the curve without `n0` was the trap,
   because the autoscaled amplitude is computed *by* the evaluation.
   Zero `update_model()` calls per decay `run()`, pinned by test.

3. **The data are duplicated — measured 2026-09-02, and the number says
   leave it.** `ChiSquared.set_data_arrays` costs **0.6 µs of a 252.7 µs
   graph build** (0.2%) at 512 channels and 19.4 µs at 65k, once per
   `run()` (consumers share `_cached_graph`). The end-state — `DataCurve`
   wrapping an engine-owned buffer — would invert buffer ownership across
   the whole application (the 2×N `d` storage, the write-lock discipline,
   pickling, every view) for sub-microsecond gains. Buffer plumbing is
   generic infrastructure, where refusal-with-a-number remains the
   sanctioned method (the saturation overrule reached forward models, not
   this). **Queued as an owner decision in PRD-105**: literal engine
   ownership is an architecture statement, not a performance one, and only
   the owner can want it at that price.

## Every family has now been asked

The question "what is the curve, and whose is it" has been answered for
every model family: the decay families are on the graph, ICS joined via
model-declared axes, and DEER, PCH/FIDA, PDA2c, MFD, stopped-flow and FCS
each carry a written verdict in
[graph-eligibility-verdicts](../references/graph-eligibility-verdicts.md)
— including the deliberate stays and what would change them.
