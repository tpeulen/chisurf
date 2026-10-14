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

**Spectroscopy ▸ Correlation ▸ Lifetime-FCS
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

The acquisition simulator is the *Simulation* device of **Tools ▸ Views ▸
Acquisition**. Press **Simulation setup…** (or **Device Setup…** with the
Simulation source selected) to open its setup dialog, an emtk window declared as
an AutoForm spec. **OK** merges the dialog over the tool's current simulator
parameters, validates the result by constructing the simulator engine, and uses
it for the next **Start**; a set the engine rejects keeps the dialog open and says
why on the status line. **Cancel** changes nothing. *Advanced simulation
parameters* still shows the same dictionary as raw JSON.

```{figure} figures/18_sim_setup.png
:name: fig-18-sim-setup
:width: 80%

The simulation setup dialog with two species, green and red detection, and the
*Kinetics* fold open: the radiative grid holds two non-zero rates
(s0 → s1 at 1.0/ms, s1 → s0 at 0.5/ms).
```

The **Sample & brightness** panel is one table with a row per species: molecules
*M*, diffusion coefficient *D*, and the parallel/perpendicular brightness *q* of
each enabled detection colour. Double-click a number to edit it (Enter commits,
Escape cancels). Rows follow the **Species** count and columns follow the
*Green* / *Red* / *Yellow* checkboxes, so a species or a colour appears with its
cells already there. The last row is **BG** — the per-channel background, which
is not a species (its *M* and *D* are blank and cannot be edited) but is detected
in the same channels, so it is edited in the same grid.

The last column is **Decay**: a lifetime spectrum is not a number, so each
species shows a summary (`τ 3.8 ns`) that a double click turns into the decay
editor for *that* species — its amplitude/lifetime table (**Add**, **Remove**),
an optional measured decay pattern file (**Clear pattern** drops it), the shared
Gaussian IRF width, and a live preview of the resulting micro-time decay. **OK**
in the decay editor writes every species' edits back; **Cancel** discards them.
The **Decay…** button opens the editor on the selected row. A species added after
the others starts from the default single 3.2 ns lifetime rather than inheriting
a neighbour's spectrum. **Load JSON**, **Save JSON** and **View JSON** read,
write and show the parameter dictionary the simulator receives.

#### State kinetics

The **Kinetics** fold (closed until opened) holds two editable N×N grids,
*Radiative* (`k_rad`) and *Non-radiative* (`k_nrad`), of interconversion rates in
1/ms: row *i*, column *j* is the rate from species *i* to species *j*. The
diagonal is not a rate and cannot be edited, and both grids resize with the
**Species** count, keeping the rates already entered.

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

## See also

- `tttrlib.SimEngine`; {src}`chisurf/core/fluorescence/fcs/simulate.py`.
- Tool: the **lifetime-FCS simulator** (`chisurf/plugins/fcs/fcs_lfcs_sim/`).

Uncorrelated background in the lifetime-FCS simulator is spread uniformly over
the laser period (not prompt scatter at micro-time zero), so a seeded run with
background differs from one made before that change.
