---
type: Reference
title: "Driving the photon simulator: states, channels and patterns"
description: How to express photophysics for the confocal photon simulator — a species is any emitting state, brightness is per detection channel, the micro-time pattern belongs to the state, and routing between states is either spontaneous (conformational) or excitation-scaled (photo-induced). Covers why colour x polarization, sensitized acceptor decay and PIE all use the same encoding rather than dedicated parameters, and which convenience parameters are legacy special cases to avoid.
resource: chisurf/core/fluorescence/burst/simulate.py
tags: [reference, simulation, photons, tttr, smfret, anisotropy, mfd, kinetics]
timestamp: '2026-08-03T00:00:00Z'
---

# Driving the photon simulator: states, channels and patterns

The confocal photon simulator has one modelling idea, and nearly every question
about it ("can it do X?") is really the question "how do I express X in that
idea?". The answer is almost always yes, and almost never through a parameter
named after X.

This page exists because that question keeps being asked, and because the wrong
answer — "it cannot, so approximate it afterwards" — is easy to reach by reading
the parameter list instead of the model.

## The idea

A molecule occupies one **species** at a time. A species is *any emitting state*,
not a chemical identity, and it carries three things:

| | meaning |
|---|---|
| `q` | brightness **per detection channel** (`q_alex[laser][channel]` with alternating excitation) |
| `decay` | the micro-time pattern of photons emitted **from this state** |
| `D`, `v_scale` | how this state moves |

Molecules move between species through two rate matrices, and the distinction
between them is the useful part:

* **`k_nrad`** — spontaneous rates. Conformational exchange, blinking, bleaching.
  These run on the wall clock, so they are what a *kinetic scheme* means.
* **`k_rad`** — rates **scaled by the local excitation intensity**. Photo-induced
  events: they happen on the excitation clock, are zero for a molecule outside
  the focus, and scale correctly when a molecule crosses a bright region.

Both are **row-major source → target**, in **per-macro-time-unit** rates. With
the millisecond convention (`D` in µm²/ms, brightness per ms) that is ms⁻¹, which
is the transpose *and* a factor of 1000 away from chisurf's `K[target, source]`
in Hz. Getting either wrong yields a simulation that runs and is silently static,
or a thousand times too fast. Convert in one place; see
`SmfretParameters.exchange_matrix_ms`.

## The consequence: no feature needs a feature

Because the state carries both *where* its photons go and *what their micro times
look like*, anything of the form "these photons are different from those photons"
is a state, not a parameter:

* **Sensitized acceptor decay.** A FRET pair modelled as one species with
  `q = [green, red]` gives acceptor photons the *donor's* decay, which is wrong —
  they have a rise. Modelled as two species (donor-excited → acceptor-via-FRET,
  routed by **`k_rad`**, because transfer is excitation-driven), each carries its
  own pattern and the rise appears by construction.
* **PIE.** The prompt/delayed windows are `decay.t0` offsets on the states that
  emit into them.
* **Colour × polarization.** See below.

## Colour × polarization

The apparent obstacle: a species has exactly one `decay`, so it cannot give
different micro-time distributions to different channels; and the `r0` / `l1` /
`l2` / `D_rot` parameters — described in the source as reviving *"the legacy
rotational-diffusion model"* — route photons parallel/perpendicular into channels
0/1 **instead of** by colour, not in addition to it.

Both dissolve once polarization is treated as a state. The joint distribution
over (channel, micro time) factorizes exactly:

```
P(parallel)   ∝ ∫ VV(t) dt          P(t | parallel)   ∝ VV(t)
P(perpendicular) ∝ ∫ VH(t) dt       P(t | perpendicular) ∝ VH(t)
```

and both polarized decays are **ordinary multi-exponentials**, because
`exp(−t/τ)·exp(−t/ρ)` is just another exponential:

```
VV(t) = vm(t)·[1 + (2 − 3·l1)·r(t)]      VH(t) = vm(t)·[1 − (1 − 3·l2)·r(t)] / G
r(t)  = r0·exp(−t/ρ)
```

So each conformational state becomes **one species per emission mode** — parallel
and perpendicular — with `q` on that mode's channels and the corresponding
polarized spectrum as its `decay`. Routing between the two modes uses `k_rad`,
not `k_nrad`: photoselection happens on the excitation clock, so an
excitation-scaled rate makes successive photons independent without needing a
huge spontaneous rate, and costs nothing while the molecule is away from the
focus.

The state space becomes *conformation × emission mode*, so a two-state kinetic
scheme with two polarizations is four species: conformational rates go in
`k_nrad` between same-mode species, mode-switching rates in `k_rad` within a
conformation.

This is exact. The alternative — splitting polarization afterwards in Python from
each photon's micro time — is exact only for quantities that *sum* the two
polarizations (the whole FRET axis of an MFD measurement) and approximate for
anything that reads them apart.

## Things that bite

* **`active_margin` must scale with the slowest rate**, not be a constant. The
  open-volume optimisation skips molecules far from the focus, and the schema
  requires `margin ≳ √(2·D/k)` so a molecule arrives with its state distribution
  equilibrated rather than frozen. Slow exchange needs the *largest* margin, which
  is exactly the regime a kinetics study cares about. Derive it, or set 0.
* **`q_alex` must have exactly one row per excitation grid.** A single-laser
  configuration must omit it and use `q`.
* **Plain Python lists, not `VectorDouble`,** for by-value `std::vector`
  arguments: the proxy is rejected once another SWIG extension has claimed the
  shared type table.
* **The state log is the ground truth** (`set_state_log`, `state_occupancy`,
  `emitting_species`, `emitting_molecule`). It is what makes a simulated
  measurement a *test* rather than another model: bursts can be defined by which
  molecule emitted them instead of by a threshold.

## See also

* [Time-resolved anisotropy](anisotropy-theory.md) — where VV/VH and the G-factor come from.
* [Fitting the 2D MFD histogram](../../docs/concepts/mfd_fitting.md) — the analysis this feeds.
