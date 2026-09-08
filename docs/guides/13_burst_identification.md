---
type: Guide
title: Photon burst identification and the burst list
description: In a confocal single-molecule experiment the focus is mostly empty; a molecule crossing it produces a short, intense burst of photons above the diffuse background.
tags: [guides, bursts, photons, corrections]
---

# Photon burst identification and the burst list

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for burst search and the per-burst observables.
:::

## What it does

In a confocal single-molecule experiment the focus is mostly empty; a molecule
crossing it produces a short, intense **burst** of photons above the diffuse
background. Identifying those bursts — and building the **burst list** (the
photon-index ranges of each burst) — is the first step of every burst analysis
([2CDE](01_fret_2cde.md), [BVA](08_burst_variance_analysis.md),
[PDA](11_pda2c.md), MLE lifetimes, HMM).

A **sliding-window** search flags photons whose local count rate (photons per
short window, or the inverse inter-photon time) exceeds a threshold; contiguous
flagged photons that also satisfy a minimum-photon count form a burst. Variants
(count-rate, CUSUM, Bayesian-blocks, Kalman) trade sensitivity against false
positives.

## In ChiSurf

```python
import tttrlib

# sliding-window burst search directly on a TTTR object
bursts = d.burst_search(L=20, m=10, T=0.5e-3)   # min photons, window size, window time (s)
```

The `burst_selection` plugin exposes the search, the pre-filters (channel /
micro-time / delta-macro-time), and the burst-list manipulations (split, merge,
select by size/duration/background) with a live preview, publishing the burst
folder into the guided workflow context. From the guided facade:
`workflow.select_bursts(method="burst", min_photons=20)`.

## Result

A simulated photon stream (diffuse background with occasional bright transits)
and its sliding-window count-rate trace; windows above the threshold (red) are
the detected bursts.

```{figure} figures/burst_search.png
:name: fig-burst-search
:width: 90%

Burst identification.
```

## Reading the diagnostic plots

The plots draw a **window of the measurement**, not all of it. Ten seconds by
default: a six-file selection is half an hour and millions of photons, and drawn
whole it is an envelope with no individual burst visible in it.

**Show a window of** sets the length and the slider walks it through the
selection. The caption under the slider says where you are and, because the
files are laid end to end on one timeline, which file you are looking at —
`1074.0–1084.0 s of 1800.0 s · 004_….sm (4/6)`. Unchecking it draws everything,
which is what the plots did before.

The window is the same setting as **First photon** / **Last photon** underneath;
type there when you want an exact photon range.

## See also

- `chisurf/plugins/burst/burst_selection/`; `chisurf/core/fluorescence/burst/`.
