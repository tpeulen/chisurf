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
import tttrlib

cfg = tttrlib.SimEngine.default_json()          # edit species, D, brightness, kinetics
sim = tttrlib.SimEngine.from_json(cfg)
sim.run()
macro = sim.macro_window                        # + sim.arrival_time, sim.micro_time, sim.channel
```

The lifetime-FCS simulator (`chisurf/core/fluorescence/fcs/simulate.py`) and the
FRET-docking / burst-workflow `simulate()` helpers wrap this for common cases,
returning data registered in MMFDB so recovered states can be compared with the
truth.

## Result

A simulated confocal intensity trace (molecules transiting the Gaussian spot) and
its autocorrelation — the closed loop that lets every FCS/burst analysis be
validated against a known input.

![Simulated confocal trace and its correlation](figures/simulation.png)

## See also

- `tttrlib.SimEngine`; `chisurf/core/fluorescence/fcs/simulate.py`.
