---
type: Guide
title: 'H2MM: simulating and validating'
description: 'Before trusting an H2MM result on real data you validate the whole chain on simulated data with a known number of states, known FRET efficiencies and known transition rates: simulate the photon stream…'
tags: [guides, simulation, fret, photons]
---

# H2MM: simulating and validating

:::{admonition} Theory
:class: seealso
See {ref}`concept-photophysics-simulation` for how the ground-truth photon
stream is generated and {ref}`concept-h2mm` for the model being validated.
:::

## What it does

Before trusting an H2MM result on real data you validate the whole chain on
**simulated** data with a known number of states, known FRET efficiencies and
known transition rates: simulate the photon stream, run the same
`analyze(...)` you use on measurements, and check that the model-selection
criterion recovers the right number of states and that the fitted efficiencies
and rates match the inputs. This is also how the **uncertainty** of a real fit
is assessed — by bootstrapping (resampling bursts with replacement and refitting)
to get error bars on the per-state E/S and rates.

## In ChiSurf

Simulate a ground-truth dataset (via the tttrlib confocal simulator, see
[tutorial 18](18_tttr_simulation.md)) and analyse it exactly as measured data:

```python
from chisurf.plugins.burst.burst_analysis.api.workflow import BurstWorkflow

wf = BurstWorkflow.demo()
sim = wf.simulate(fret=[0.3, 0.7], exchange_rate=0.2)       # 0.2 /ms = 200 /s, known truth
bursts = wf.select_bursts(sim.handle, setup=sim.setup)
result = bursts.h2mm(states=(1, 2, 3))                      # should select 2 states
print(result.summary())
wf.close()
```

`exchange_rate` is in 1/ms. This run finds 990 bursts, selects two states at
E = 0.30 and 0.70 and returns exchange rates of 195 and 203 s⁻¹
(`result.analysis.trans_rates`) against the simulated 200 s⁻¹; at
`exchange_rate=0.05` it returns 42 and 36 s⁻¹ against 50 s⁻¹.

The uncertainty of a fit is its bootstrap over bursts. The core API exposes the
simulator of the model itself, which is the quickest way to check recovery and
error bars together:

```python
import numpy as np
from chisurf.plugins.burst.burst_h2mm.core import h2mm
from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze, bootstrap_uncertainty

truth = h2mm.H2mmModel(
    prior=np.array([0.5, 0.5]),
    trans=np.array([[0.995, 0.005], [0.010, 0.990]]),   # per tick
    obs=np.array([[0.85, 0.15], [0.20, 0.80]]),         # E = 0.15 and 0.80
)
rng = np.random.default_rng(1)
times = [np.concatenate([[0], np.cumsum(rng.poisson(4, 119) + 1)]) for _ in range(400)]
data = h2mm.prepare_bursts(times, h2mm.simulate_bursts(truth, times, seed=8), n_streams=2)

ana = analyze(data, state_counts=(1, 2, 3, 4), criterion="bic", base_time_s=1e-6)
unc = bootstrap_uncertainty(data, ana.best.n_states, n_boot=20)
ana.best.n_states, ana.fret, ana.trans_rates      # 2 states, E and rates (1/s)
unc.fret_lo, unc.fret_hi                          # 95 % bootstrap interval per state
```

With a 1 µs tick the truth is 5000 and 10 000 s⁻¹. The fit returns two states
at E = 0.151 and 0.799 with rates of 4931 and 10 265 s⁻¹, and 95 % bootstrap
intervals of [0.146, 0.156] and [0.794, 0.804], in about 4 s.

In the **H2MM** window the same bootstrap is the **±** button (run after a
fit; it overlays the intervals as error bars), and **📈** profiles the
likelihood of each state's E/S instead. `burst_h2mm` also offers an
`em-float32` engine (the GUI default) and an optional trained neural surrogate
for large datasets.

```{figure} figures/31_h2mm_simulated.png
:name: fig-31-h2mm-simulated
:width: 100%

The H2MM window on the simulated two-state dataset of the second code block
(400 bursts, 48 000 photons, donor = channel 0, acceptor = channel 1, no Aex
stream, scan patience *off*). *Model selection*: BIC drops from 1 to 2 states
and stays flat after. *Dwell FRET states*: dwells at E = 0.15 and 0.80.
*Transition rates*: 4.9k and 10.3k s⁻¹ for a truth of 5k and 10k. *Per-state
decay* is empty because the simulation has no micro times.
```

:::{admonition} Known defects
:class: warning
- At `exchange_rate=0.5` (500 s⁻¹) the facade simulation above is *not*
  recovered: BIC picks three states, one at E = 0.44 holding 96 % of the
  photons and two at E = 1.00 with rates of order 10⁵ s⁻¹.
- The plugin's example generator (`examples/generate_example_data.py`) writes
  its Photon-HDF5 file without a macro-time resolution. tttrlib reports −1 for
  it and the H2MM service uses that as the time base, so dwell times and the
  state path come out negative and the rates are per tick. The figure above
  was made from the same model written with a 1 µs tick.
:::

## Result

A script figure of the same check. **Left:** the BIC drops sharply from 1 to 2
states and rises again at 3 — correctly selecting the simulated two-state
model. **Right:** the FRET efficiencies recovered by H2MM match the simulated
values.

```{figure} figures/h2mm_recovery.png
:name: fig-h2mm-recovery
:width: 90%

H2MM recovers the simulated states.
```

## See also

- `chisurf/plugins/burst/burst_h2mm/core/` (`surrogate.py`, `analysis.py`); the ground-truth simulator: [tutorial 18](18_tttr_simulation.md).
