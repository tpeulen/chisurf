---
type: Reference
title: Graph-eligibility verdicts — the model families outside the decay
description: The written verdict per model family that board T-20260901-09 asked for — what each family's curve is, whose it is under the placement rule, whether it can or should become an IMP.bff graph objective, and what its census fixture hides. Decisions, not an inventory; the survey behind them is in the resolved board ticket.
resource: chisurf/core/models/, chisurf/core/fitting/minimizer.py
tags: [reference, architecture, fitting, imp.bff, tttrlib, census]
timestamp: '2026-09-02T00:00:00Z'
---

# Why one verdict per family

The census (`imp.bff/test/minimizer/census_models.py`) says 10 of 42
constructible model classes build a graph. For the rest, the first question is
not "port it" but **what is the curve, and whose is it** — the
[imp-ecosystem](imp-ecosystem.md) rule one layer down. This page is the
answer per family, written 2026-09-02 (board `T-20260901-09`).

One structural fact frames every row: `graph_objective` never *inspects*
these families. They are hand-written `ModelCurve` subclasses with no parse
expression, so all of them fail `_member_objective`'s one-line test and take
the director path. Reaching any of them needs an objective-side node, not the
relaxation of a refusal. And three families do not even produce a residual
`ChiSquared` computes (PDA2c projects a 2-D matrix; MFD scores through more
than one marginal) — for those, a perfect forward-model node would still not
make `Expression → ChiSquared` the right objective.

# The verdicts

| family | verdict | first action |
|---|---|---|
| **ICS** | **shipped 2026-09-02** — fits through the graph | `_member_objective` now takes model-declared axes (`graph_axes()` → name→flat array, each as long as the data), and both ICS models expose their compute as a generated expression over `xi`/`psi`/`tau` — one unconditional string, because every optional term is *exactly* neutral at its default (`a_T=0` → triplet factor 1; at `N_imm=0` the two amplitude spellings are algebraically identical); only `two_d` regenerates it, and the graph cache key now carries the equation string so the flip cannot reuse the 3D graph. Timing is folded into the `tau` axis: freeing a timing parameter refuses the graph (unclaimable port), the correct fallback. Parity ≤3e-16 engine-vs-numpy across 3D/2D × full/neutral; node curve = `update_model` at 1e-12 (`test/fitting/test_graph_fit_ics.py`). Measured: converging RICS fit 128→30 ms (4.3×), early-stop STICS 5.5→4.2 ms, Python evaluations per run 28→1, per-iteration 0.19→0.004 ms. Census: both models flip to yes (12/42), and the census now curve-checks *expression* graphs too (previously only decay graphs — parse-family "yes" rows were unverified). |
| **PCH / FIDA** | stays — kernels already tttrlib's | No node: the kernel sits beside the photon-counting code that produces the histogram, and a bff twin would be a second implementation for no measured gain. **Fixed 2026-09-02 (PRD-121):** `FidaModel` now refuses a non-count axis outright (the same `0, 1, ... k_max` check `pch.py` uses for `PchMultiComponentModel`) instead of computing on it — the census fixture's decay-time axis used to produce a finite, non-constant, meaningless histogram with nothing to say so; it now warns and reports a dead curve. The `pch_mixture` upstream bug its wrapper documented is **already fixed in tttrlib** (`okf/BUGS.md`, fixed 2026-08-10, confirmed present in the `arm64` env); the wrapper's docstring and `okf/references/known-issues.md` now say so instead of "filed, awaiting a fix". |
| **PDA2c** | split, later — and the cache fix came first | The physics (parameters → probability spectrum, ~4k lines of numpy) is a clean bff candidate; the S1S2 engine is tttrlib's and correctly so; the projection/statistic stays chisurf's choice. A `graph_objective` path is wrong as things stand — the objective is a projected matrix under Poisson deviance, not `(y−d)/ey`. **Fixed on sight (2026-09-02): the per-residual callback reassignment** that defeated `tttrlib::Pda`'s bin cache — ~(n_max+1)(n_max+2)/2 director crossings per residual, measured 6× per residual at n_max=120 — now keyed on `(axis, gamma, R0)`, rebuilding only when a fitted nuisance actually moves the projection. |
| **MFD 2D** | stays numpy — blocked on the objective, not the curve | The strongest bff candidate after ICS, but its histogram source scores bursts through more than one marginal, so a `ChiSquared` downstream would be numerically fine and statistically wrong (the `MaxEntLifetimeModel` failure mode). Settle the statistic first. **Fixed 2026-09-02 (PRD-121):** `update_model`'s no-op without a payload now logs a named warning (`"Mfd2DModel.update_model: no MFD burst payload..."`) rather than silently leaving the curve untouched, so the census's curve column reads it honestly as dead instead of the phantom it used to be. |
| **Stopped-flow** | stays scipy — **deliberately deferred** | The model exists because the scheme has no closed form; a graph needs a stiff general mass-action ODE node to replace LSODA — a large piece of new engine for one family, and the cost is in LSODA, not the crossing. Deferred with the reason, not overlooked. |
| **FCS (kinetics + composable)** | **both steps shipped 2026-09-02** | Step 1 was `T-20260902-11` (MDF 110→5.3 ms/curve; saturation ported after the owner's overrule). Step 2, the composition layer: `GeneralFCSModel` regenerates its compound equation for the graph — the diffusion mode, species count, relaxation-term count and the dataset's count-rate constant are all structural, each regenerates the string, and the cache key carries it, so the `MaxEntLifetimeModel` trap cannot fire. `gauss`/`two_focus`/`species` modes fit through the graph (parity 1e-12 with every optional factor armed; `diam=0`/`bg=0` are *exactly* neutral so one string serves each configuration); `"mdf"` refuses — a numerical kernel is not a formula — as does a free `bg` without count-rate metadata (unclaimable port). The relaxation terms' declared bounds are now *enforced* (`bounds_on=True`): a time constant at ≤0 made the director silently drop the factor, a discontinuous objective no compiled expression can follow. Measured: 2.75→1.62 ms (1.7×), zero Python evaluations per run. Census 13/42. Remaining, deliberate: an `FcsMdf`-backed node for the `"mdf"` mode, and `FCSKineticsModel`'s `"full"` mode as a node over the saturation kernel — both engine nodes, not expressions. |

# What the census fixture hid

More dangerous than its construction errors were its **silent passes**: on the
shared decay-shaped fixture, `Mfd2DModel` constructed and `update_model`
no-opped; ICS constructed and emitted zeros; `FidaModel` computed on a
meaningless axis without complaint. Each read as "buildable, just not built"
when the truth was "never computed at all". PDA2c's `AttributeError` was, by
comparison, the honest failure.

**Closed 2026-09-02 (PRD-121).** The census grew the third check this section
called for — `curve_verdict()` in `imp.bff/test/minimizer/census_models.py`
runs `update_model()` independently of whether a graph builds and reports
`dead` for an empty, non-finite, or constant array, printing a `PHANTOM
GRAPHS` line whenever a `yes` graph verdict sits beside a `dead` curve. The
ICS fixture gap was already closed (see the ICS row); the two rows this
section named — `Mfd2DModel`'s no-op and `FidaModel`'s meaningless axis — now
read `dead` honestly instead of `no`/`yes` with nothing to say so, because
both now log a named warning and refuse to compute nonsense rather than
leaving `ModelCurve`'s zeroed placeholder to pass as "buildable".

# Where to pick this up

1. ~~The ICS `_member_objective` generalisation~~ — done 2026-09-02 (see the
   ICS row). The door it opened: any model can now declare its own evaluation
   axes via `graph_axes()`, which is what the FCS composition layer (step 2
   of the FCS row) and future multi-axis parse models build on.
2. ~~The census's non-degenerate-curve column~~ — done 2026-09-02 (PRD-121,
   see "What the census fixture hid" above).
3. ~~`FidaModel`'s axis refusal; the `pch_mixture` upstream filing~~ — done
   2026-09-02 (PRD-121). `pch_mixture` turned out to be fixed upstream already
   (tttrlib, 2026-08-10) by the time this was picked up; only the wrapper's
   stale docstring and this repo's `known-issues.md` needed updating.
4. The MFD statistic decision, before any MFD port — still open, and unrelated
   to the curve-honesty fix above: the loud no-op tells you the model wasn't
   fitted, not what the right objective is once it is.
