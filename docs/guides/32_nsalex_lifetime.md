---
type: Guide
title: 'ns-ALEX / PIE: FRET, stoichiometry and lifetime together'
description: With pulsed interleaved excitation (PIE / ns-ALEX) each photon carries a nanotime (micro-time = delay after its excitation pulse) in addition to its detector and macro time.
tags: [guides, tcspc, lifetime, fret, photons]
---

# ns-ALEX / PIE: FRET, stoichiometry and lifetime together

:::{admonition} Theory
:class: seealso
See {ref}`concept-tcspc-lifetime` for the fluorescence-lifetime model fitted to the burst nanotimes.
:::

## What it does

With **pulsed** interleaved excitation (PIE / ns-ALEX) each photon carries a
**nanotime** (micro-time = delay after its excitation pulse) in addition to its
detector and macro time. That adds a **fluorescence-lifetime** axis to every
burst, on top of the FRET efficiency $E$ and stoichiometry $S$ from ALEX. The
**E–τ plot** (efficiency vs donor lifetime) is the multi-parameter workhorse:
a *static* FRET species lies on the line $\tau_D = \tau_0(1-E)$, while a species
that averages between states within the burst sits **above** the line — a direct,
model-free readout of sub-burst dynamics.

## In ChiSurf

The nanotimes are the micro-times of the burst photons, split by stream:

```python
import numpy as np

burst_ph = np.arange(first_photon, last_photon + 1)
micro = np.asarray(tttr.micro_times)[burst_ph]
route = np.asarray(tttr.routing_channels)[burst_ph]
donor_nanotimes = micro[np.isin(route, donor_channels)]     # per-burst donor decay
# mean donor lifetime per burst, or a full ML lifetime fit (tutorial 21)
```

The per-burst donor lifetime is fitted by maximum likelihood
([tutorial 21](21_lifetime_from_bursts.md)); the `burst_h2mm` E–τ panel draws the
static-FRET line and, with nanotime **divisors**, resolves states that share an
apparent $E$ but differ in lifetime. PIE/ALEX streams are prepared by the
`ptu_alex_creator` and micro-time-gating tools.

## Result

An E–τ plot: two static FRET populations on the $\tau_0(1-E)$ line and a dynamic
population displaced above it.

```{figure} figures/nsalex_etau.png
:name: fig-nsalex-etau
:width: 90%

ns-ALEX FRET–lifetime plot.
```

## See also

- Per-burst lifetimes: [tutorial 21](21_lifetime_from_bursts.md); lifetime-resolved HMM states: [H2MM](30_h2mm_workflow_results.md).
- Tool: **Burst MLE** (`chisurf/plugins/burst/burst_mle_analysis/`).
