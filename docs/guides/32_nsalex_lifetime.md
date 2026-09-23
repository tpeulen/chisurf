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

The nanotimes are the micro-times of the burst photons, split by stream. On a
BH SPC-130 PIE measurement, with the burst table the search wrote:

```python
import numpy as np
import tttrlib
from chisurf.core.datastore import numeric_column
from chisurf.core.fluorescence.burst.photons import load_bur_dataframe

tttr = tttrlib.TTTR("m000.spc", "SPC-130")
bursts = load_bur_dataframe(["burstwise_All 0.1000#15/bi4_bur/m000.bur"])
first = numeric_column(bursts, "First Photon").astype(int)
last = numeric_column(bursts, "Last Photon").astype(int)

micro = np.asarray(tttr.micro_times)
route = np.asarray(tttr.routing_channels)
dt_ns = tttr.header.micro_time_resolution * 1e9
donor_channels, prompt = (0, 8), (0, 2048)                 # donor detectors, Dex window

mean_delay = []
for s, e in zip(first, last):
    if e <= s:                                               # separator row
        continue
    m, r = micro[s:e + 1], route[s:e + 1]
    dd = m[np.isin(r, donor_channels) & (m >= prompt[0]) & (m < prompt[1])]
    mean_delay.append(dd.mean() * dt_ns if dd.size >= 20 else np.nan)
# per-burst mean donor delay; a full ML lifetime fit is tutorial 21
```

On `m000.spc` of the double-labelled DNA fixture this gives 203 bursts, 90 of
them with ≥ 20 donor photons, and a median mean delay of 3.9 ns (measured from
the start of the TAC, so it still contains the IRF position).

The per-burst donor lifetime proper is fitted by maximum likelihood in
**Burst MLE** ([tutorial 21](21_lifetime_from_bursts.md), step 6 of Burst
Analysis); the E–τ plot with the static-FRET line is drawn by the **Accurate
FRET** tool ([accurate FRET](41_accurate_fret.md)) and by ndX. PIE/ALEX streams
are prepared by the `ptu_alex_creator` and micro-time-gating tools.

**H2MM** adds the lifetime per *state* rather than per burst: its *Per-state
decay* dock histograms the micro times of the photons each state was assigned,
per detection colour, and the **Nanotime divisors** setting splits every stream
into micro-time bins so that states with the same apparent E but different
lifetimes can be told apart.

```{figure} figures/32_h2mm_state_decays.png
:name: fig-32-h2mm-state-decays
:width: 90%

*Per-state decay* of the four-state H2MM fit of the DNA fixture
([H2MM results](30_h2mm_workflow_results.md)), donor (*green*) photons of the
three FRET states. The decay steepens as E rises: over 2.6–12 ns the mean delay
after the peak is 1.76, 1.66 and 1.18 ns for S1 (E ≈ 0.22), S2 (≈ 0.62) and S3
(≈ 0.88), against 2.55 ns for the donor-only-like S0 (E ≈ 0.03, unticked here).
The colour and state boxes under the plot choose the curves.
```

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
- Tools: **Burst MLE** (`chisurf/plugins/burst/burst_mle_analysis/`), **Accurate FRET** for the E–τ plot, **H2MM** for per-state decays.
