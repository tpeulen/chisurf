---
type: Guide
title: Multispot (8-spot) smFRET
description: Multispot excitation splits the beam into several confocal spots imaged onto a detector array, so many molecules are observed in parallel…
tags: [guides, fret, smfret, bursts]
---

# Multispot (8-spot) smFRET

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the per-channel burst E/S analysis replicated across spots.
:::

## What it does

Multispot excitation splits the beam into several confocal spots imaged onto a
detector array, so many molecules are observed in **parallel** — multiplying the
throughput of diffusion-based smFRET. Each spot is an independent measurement
(its own background, burst search and FRET histogram); the per-spot results are
then fitted with a **shared** FRET model, and the small spot-to-spot differences
(from alignment/efficiency) are cross-checked. The analysis of each spot is
exactly the [single-spot workflow](27_alex_smfret_workflow.md), applied per
detector channel.

## In ChiSurf

Each spot is a routing channel (or channel pair), so multispot analysis is the
per-channel burst analysis run over the spots and the results tabulated. The FCS
correlator and burst engines already handle arbitrary channel sets; a global fit
shares the population efficiencies across spots while letting amplitudes vary.

```python
from chisurf.plugins.burst.burst_analysis.api.workflow import BurstWorkflow, Setup

wf = BurstWorkflow.demo()
handle = wf.register("multispot_measurement.hdf5")
per_spot = {}
for spot, (g_ch, r_ch) in enumerate(spot_channel_pairs):   # e.g. [((0,), (8,)), ((1,), (9,)), ...]
    bursts = wf.select_bursts(handle, setup=Setup.from_channels(green=g_ch, red=r_ch))
    per_spot[spot] = bursts.h2mm(states=(1, 2)).fret      # or .bva(), .two_cde()

# shared-model fit across spots (populations common, fractions per spot)
```

There is no dedicated multispot window: in the GUI, each spot is a detector
pair defined under the channel definitions of **Burst Selection** (one search
per pair), and the per-spot histograms are compared or fitted globally
afterwards. No multispot fixture ships with ChiSurf, so this page has no
screenshot of its own; the per-spot step is the single-spot one shown in
[tutorial 27](27_alex_smfret_workflow.md).

The burst table `select_bursts` returns carries the setup's per-detector
columns (`Number of Photons (<name>)` …), so a per-spot proximity-ratio histogram
reads straight off `bursts.table`.

## Result

Per-spot FRET-efficiency histograms of a simulated 8-spot measurement; the
population positions (red line = high-FRET median) agree across spots, which is
the check a real multispot run has to pass.

```{figure} figures/multispot.png
:name: fig-multispot
:width: 90%

Simulated 8-spot smFRET: per-spot E histograms, high-FRET median in red.
```

## See also

- The single-spot pipeline: [tutorial 27](27_alex_smfret_workflow.md); the FCS correlator handles arbitrary channel sets.
