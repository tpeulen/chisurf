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
| **ICS** | → imp.bff, via `Expression` | Generalise `_member_objective` to N array ports; the model is one closed-form expression over three pre-broadcast lag grids. Best payoff-to-work in the set, and the builder change lands every future multi-axis parse model too. |
| **PCH / FIDA** | stays — kernels already tttrlib's | No node: the kernel sits beside the photon-counting code that produces the histogram, and a bff twin would be a second implementation for no measured gain. Do fix `FidaModel`'s silent acceptance of a non-integer count axis, and file the `pch_mixture` upstream bug its wrapper documents. |
| **PDA2c** | split, later — and the cache fix came first | The physics (parameters → probability spectrum, ~4k lines of numpy) is a clean bff candidate; the S1S2 engine is tttrlib's and correctly so; the projection/statistic stays chisurf's choice. A `graph_objective` path is wrong as things stand — the objective is a projected matrix under Poisson deviance, not `(y−d)/ey`. **Fixed on sight (2026-09-02): the per-residual callback reassignment** that defeated `tttrlib::Pda`'s bin cache — ~(n_max+1)(n_max+2)/2 director crossings per residual, measured 6× per residual at n_max=120 — now keyed on `(axis, gamma, R0)`, rebuilding only when a fitted nuisance actually moves the projection. |
| **MFD 2D** | stays numpy — blocked on the objective, not the curve | The strongest bff candidate after ICS, but its histogram source scores bursts through more than one marginal, so a `ChiSquared` downstream would be numerically fine and statistically wrong (the `MaxEntLifetimeModel` failure mode). Settle the statistic first; also stop `update_model`'s silent no-op without a payload, which makes the census report a phantom. |
| **Stopped-flow** | stays scipy — **deliberately deferred** | The model exists because the scheme has no closed form; a graph needs a stiff general mass-action ODE node to replace LSODA — a large piece of new engine for one family, and the cost is in LSODA, not the crossing. Deferred with the reason, not overlooked. |
| **FCS (kinetics + composable)** | → imp.bff, in two steps | Step 1 is `T-20260902-11` (saturation + PSF kernels; MDF already landed at 110→5.3 ms/curve). Step 2 is the composition layer: `GeneralFCSModel`'s curve genuinely *is* an equation (`equation_html` already writes it), so a regenerated-`Expression` graph fits the existing path; the kinetics model's `"full"` mode is a node that follows the kernel. Mode switches must invalidate the cached graph — the `MaxEntLifetimeModel` trap. |

# What the census fixture hides

More dangerous than its construction errors are its **silent passes**: on the
shared decay-shaped fixture, `Mfd2DModel` constructs and `update_model`
no-ops; ICS constructs and emits zeros; `FidaModel` computes on a meaningless
axis without complaint. Each reads as "buildable, just not built" when the
truth is "never computed at all". The census should grow a third check —
*does `update_model` produce a non-degenerate curve* — so fixture gaps stop
looking like builder verdicts. PDA2c's `AttributeError` is, by comparison,
the honest failure.

# Where to pick this up

1. The ICS `_member_objective` generalisation (N array ports) — smallest
   step, widest door.
2. The census's non-degenerate-curve column.
3. `FidaModel`'s axis refusal; the `pch_mixture` upstream filing.
4. The MFD statistic decision, before any MFD port.
