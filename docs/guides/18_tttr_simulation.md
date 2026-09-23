---
type: Guide
title: TTTR simulation of diffusing particles
description: 'Simulating single-molecule data with a known ground truth is the way to validate an analysis pipeline: you generate photons from molecules with defined diffusion coefficients, brightnesses, FRET states and kinetics…'
tags: [guides, tttr, photons, simulation, diffusion, fret, kinetics]
---

# TTTR simulation of diffusing particles

:::{admonition} Theory
:class: seealso
The ingredients of a single-molecule photon simulation — Brownian trajectories
through the detection profile, Poisson emission, FRET channel partitioning,
background and detector effects, and state kinetics — are explained in the
concept page {ref}`concept-photophysics-simulation`.
:::

## What it does

Simulating single-molecule data with a **known ground truth** is the way to
validate an analysis pipeline: you generate photons from molecules with defined
diffusion coefficients, brightnesses, FRET states and kinetics, run the same
analysis you use on real data, and check that it recovers the inputs.

ChiSurf drives **tttrlib's confocal simulator** (`SimEngine`): molecules perform
Brownian motion through a 3-D detection volume (optionally in a closed geometry),
emit Poisson photons at the local brightness with per-state micro-times
(lifetimes) and routing (colours), optionally exchanging between FRET/kinetic
states — and the events are encoded to a real TTTR container (PTU/HT3/SPC).

## In ChiSurf

```python
import numpy as np
import tttrlib

cfg = tttrlib.SimEngine.default_json()          # a JSON string: edit species, D, brightness, kinetics
sim = tttrlib.SimEngine.from_json(cfg)
sim.run()                                       # default: 1 000 000 photons, 2 channels
macro = np.asarray(sim.macro_window())          # accessors are methods returning tuples:
arrival = np.asarray(sim.arrival_time())        # + sim.micro_time(), sim.channel()
t = macro * 0.01 + arrival                      # absolute time = window * settings.dt + offset
```

The lifetime-FCS simulator ({src}`chisurf/core/fluorescence/fcs/simulate.py`) and the
FRET-docking / burst-workflow `simulate()` helpers wrap this for common cases,
returning data registered in MMFDB so recovered states can be compared with the
truth.

### The lifetime-FCS simulator

**Spectroscopy ▸ Fluorescence Correlation Spectroscopy ▸ Lifetime-FCS
Simulator** simulates two diffusing species with lifetimes **τ₁**, **τ₂** and
diffusion coefficients **D₁**, **D₂**, an optional symmetric interconversion
rate **k (1/ms)** (0 = static), a **Photons** budget and a **Seed**; **Simulate
+ Correlate** builds the lifetime filters from the species' reference decays and
plots the filtered species auto- and cross-correlations. The status line reports
the filter condition number (large = the lifetimes are too similar to separate).

```{figure} figures/18_lfcs_sim.png
:name: fig-18-lfcs-sim
:width: 100%

Defaults (τ₁ = 1 ns, D₁ = 8 µm²/ms; τ₂ = 4 ns, D₂ = 0.5 µm²/ms; k = 0;
400 000 photons; seed 1): the fast species (blue) decays at the shorter lag,
the static cross-correlation (green) is flat at 1. Filter condition number 3.3.
```

### Setting up species and kinetics in the GUI

The acquisition simulator is the *Simulation* device of **Main ▸ Tools ▸
Acquisition**; its card-setup dialog is shown below.

```{figure} figures/18_sim_setup.png
:name: fig-18-sim-setup
:width: 80%

The simulation setup dialog with two species, green and red detection, and the
*Kinetics* panel open: the radiative grid holds two non-zero rates
(1 → 2 at 1.0/ms, 2 → 1 at 0.5/ms), which the button reads back as
"2×2, 2 set".
```

The **Sample & brightness** panel is one row per species: molecules *M*,
diffusion coefficient *D*, and the parallel/perpendicular brightness *q* of each
enabled detection colour. Rows follow the **Species** count and columns follow
the channel checkboxes, so a species or a colour appears with its cells already
there. The last row is **BG** — the per-channel background, which is not a
species (its *M* and *D* read `—`) but is detected in the same channels, so it is
edited in the same grid.

The last column is **Decay**: a lifetime spectrum is not a number, so each
species carries a `…` button that opens the decay editor on *that* species —
its lifetime/amplitude table, an optional measured decay pattern, and the
shared Gaussian IRF. A species added after the others starts from the default
single 3.2 ns lifetime rather than inheriting a neighbour's spectrum.

#### State kinetics

The acquisition simulator's setup dialog has a **Kinetics** panel with two
buttons — *Radiative* (`k_rad`) and *Non-radiative* (`k_nrad`). Each opens an
editable N×N grid of interconversion rates in 1/ms, where row *i*, column *j* is
the rate from species *i* to species *j*; the diagonal is fixed at zero, and both
grids resize with the **Species** count. The button reads back the scheme's size
and how many transitions are non-zero, so the panel says what the kinetics are
without being opened.

The same grid appears in the dynamic PDA model editors, so a rate matrix is read
the same way everywhere — see {ref}`concept-pda2c`.

## Result

A simulated confocal intensity trace (molecules transiting the Gaussian spot) and
its autocorrelation — the closed loop that lets every FCS/burst analysis be
validated against a known input.

```{figure} figures/simulation.png
:name: fig-simulation
:width: 90%

Simulated confocal trace and its correlation.
```

## Known defects

- The Lifetime-FCS simulator's parameter column is capped at 320 px, which
  clips the **D₁**, **D₂** and **Photons** spin boxes (`8.0000`, `400000`
  are cut in the figure).

## See also

- `tttrlib.SimEngine`; {src}`chisurf/core/fluorescence/fcs/simulate.py`.
- Tool: the **lifetime-FCS simulator** (`chisurf/plugins/fcs/fcs_lfcs_sim/`).
