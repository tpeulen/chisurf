---
type: PRD
prd: "75"
title: "PRD-75: Brightness into the amplitude — species mixtures and FRET cross-talk in FCS"
description: Postponed design for how per-species brightness propagates into the FCS autocorrelation amplitude, so a mixture of FRET species with different brightnesses (and cross-talk between channels) contributes to G(0) by brightness-weighted concentrations rather than raw particle numbers.
status: draft
phase: "unassigned"
resource: chisurf/core/models/fcs/
tags: [prd, fcs, fret, brightness, amplitude, species-mixture, crosstalk]
timestamp: '2026-08-02T00:00:00Z'
---

# Summary

In `FCSKineticsModel.update_model` (and the general FCS model), the
autocorrelation amplitude is applied as `G(tau) = b + g(tau)/N` — one particle
number `N`, one diffusion shape, amplitude `1/N`. That is exact only for a
single species with a single brightness. A **mixture of FRET species with
different brightnesses** — the whole point of [PRD-73](prd-73.md)'s brightness
wiring — contributes to `G(0)` not as raw particle numbers but as
**brightness-weighted** terms, and crosstalk between detection channels
([PRD-73](prd-73.md) §3) couples the species further.

This PRD is the **postponed** piece. It was explicitly deferred from the FRET
wiring work because it is materially more complex than the wiring itself: it
changes the amplitude model, needs a mixture/species vocabulary the FCS models
do not have today, and interacts with the saturation expansion
(`V_0/V_eff`) of [PRD-74](prd-74.md). It is registered here so the question is
not lost, and so [PRD-73](prd-73.md) and [PRD-74](prd-74.md) do not
accidentally hard-code the single-species assumption.

# Motivation

FCS measures concentration-weighted fluctuations. For a single species:

```
G(0) = 1/N   (number fluctuations)
```

But when a measurement contains a mixture — donor-only, acceptor-only, and
FRET-pair species, each with its own brightness `B_i` — the fluctuation signal
is dominated by the brighter species:

```
G(0) = Σ_i (B_i)² N_i / (Σ_i B_i N_i)²
```

### Why the brightness is squared — derivation and numerical check

`F(t) = Σ_i B_i n_i(t)`, so `G(0) = ⟨δF²⟩/⟨F⟩²`. For independent species with
Poisson number fluctuations, `⟨δn_i²⟩ = N_i` and the cross-species terms
vanish, giving `⟨δF²⟩ = Σ_i B_i² N_i` and `⟨F⟩ = Σ_i B_i N_i`:

```
G(0) = Σ_i B_i² N_i / (Σ_i B_i N_i)²
```

Each molecule contributes `B_i` to **both** ends of the intensity–intensity
correlation, so the fluctuation term scales as `B_i² N_i` while the
normalisation is the (linear) brightness-weighted mean — brighter species
dominate the amplitude disproportionately. Monte-Carlo verification (Poisson
number fluctuations over 2e6 time points) reproduces the closed form:
`B=[1,2], N=[1,1]` → simulated 0.554 vs formula 0.556; `B=[1,3], N=[2,0.5]`
→ 0.530 vs 0.531. Sanity limits: equal brightnesses reduce to
`1/(N₁+N₂) = 1/N_total`, and a single species gives `1/N` — the current
`G = b + g/N` form is the special case, recovered exactly.

The amplitude is a **brightness-weighted** inverse concentration, not `1/N_total`.
Fitting such data with a single `1/N` amplitude silently mis-reports the
concentrations, and FRET cross-talk (donor signal bleeding into the acceptor
channel and vice versa) changes the effective `B_i` in each channel — which is
exactly the per-state brightness picture `StateBrightness` already carries
(`Q_i`) and that [PRD-73](prd-73.md) will feed from the FRET calculator.

Until this lands, the kinetics FCS model cannot honestly fit multi-species FRET
data; it can only fit single-species (or species where brightness is uniform
enough that `1/N` is a good approximation). This PRD exists to make that
boundary explicit and to give the mixture work a home.

# Design sketch (for the postponed implementation)

The full design is future work; this section fixes the direction and the open
questions so the next session starts from a decision, not a blank page.

## 1. A species/brightness vocabulary

The FCS models have one `N`, one `b`, one brightness array per *state* of one
*scheme*. A mixture needs a list of species, each with its own `N_i` and its
own (possibly channel-dependent) brightness `B_i`. Options:

- extend `KineticSaturationTerms`/`StateBrightness` to carry per-species
  multiplicity, or
- a new parameter group (e.g. `SpeciesBrightness`) that composes several
  brightness vectors, one per mixture component.

Open question — to be decided at implementation: how a species' brightness
relates to the per-state `Q_i` from [PRD-73](prd-73.md) (a mixture component
has its own FRET efficiency E, so its own `Q_i` from the same `L`/`sigma`).

## 2. Amplitude formula

Replace `g/N` with the brightness-weighted sum when more than one species is
active:

```
G(tau) = b + [Σ_i B_i² N_i g_i(tau)] / [Σ_i B_i N_i]²
```

with `g_i` the (possibly different) diffusion shape of species `i`. The
single-species case must reduce exactly to the current `1/N` form.

Open question — how this interacts with the saturation volume expansion
`V_0/V_eff` of [PRD-74](prd-74.md) (does each species carry its own expansion,
or is it per-scheme?).

## 3. Cross-talk coupling

With detection cross-talk, the brightness of species `i` in channel `c` is a
linear combination over the `L` (crosstalk) matrix of [PRD-73](prd-73.md):
`B_i(c) = Σ_j L[c,j] B_i(j)`. For a single-channel fit this is a per-species
scalar; for dual-channel (FCCS-style) it couples the two channels' amplitudes.

## 4. Validation

Because the weighted-amplitude formula is exact, the acceptance test is
closed-form: a two-species mixture with known `B_i`, `N_i` must reproduce the
analytic `G(0)` from the formula above, and must reduce to `1/N` when
`B_1 = B_2`.

# Status

Draft, **explicitly postponed**. Registered so the single-species assumption in
the current amplitude is a known, named limitation rather than a silent one.
Nothing implemented. Depends on [PRD-73](prd-73.md) (brightness source and the
Q-from-`L`/`sigma` definition) and interacts with [PRD-74](prd-74.md) (the
`V_0/V_eff` handling in the two saturation modes).

Related: [PRD-73](prd-73.md), [PRD-74](prd-74.md), [PRD-62](prd-62.md).
