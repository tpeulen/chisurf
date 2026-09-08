---
type: Guide
title: Background rates
description: Every single-molecule measurement has a background — detector dark counts, buffer Raman/scatter, and afterpulsing — that must be subtracted from burst signals for accurate FRET, brightness and correlation.
tags: [guides, corrections, bursts, fret, correlation]
---

# Background rates

:::{admonition} Theory
:class: seealso
See {ref}`concept-smfret-bursts` for the role of background in the E/S corrections.
:::

## What it does

Every single-molecule measurement has a background — detector dark counts, buffer
Raman/scatter, and afterpulsing — that must be subtracted from burst signals for
accurate FRET, brightness and correlation. The background photon rate is read
from the **inter-photon-time distribution**: background photons arrive as a
homogeneous Poisson process, so the *tail* of the inter-photon-time histogram
(the long gaps, dominated by background) is a single exponential whose rate is
the background count rate.

## In ChiSurf

```python
from chisurf.core.fluorescence.burst import background

rate_hz = background.estimate_background_from_interphoton_times(
    dt_ms, tail_range_ms=(1.0, 6.0))   # the window; omit it for the fraction rule
```

The `burst_background` plugin estimates a per-detector background rate; the
`burst_irf_bg` step additionally recovers a scatter-derived **IRF** from the same
non-burst photons (the photons the burst search rejects are the built-in
scatter/background), feeding both the correction factors and the MLE lifetime
fit — with no separate buffer acquisition. See
[Lifetime from photon bursts](21_lifetime_from_bursts.md).

## Choosing the fit window

The one judgement call. The **Fit from** and **Fit to** sliders set the window in
milliseconds, and the shaded band on the inter-photon-time plot is the same
setting — drag the band or type the numbers, whichever the picture makes easier.

Both edges matter, for opposite reasons:

- **Too low a lower edge** and burst photons are fitted as background, so the
  rate comes out too high.
- **Too high an upper edge** and the fit is dominated by the far tail, which is
  bins holding one count each. On a real ALEX calibration measurement an
  unbounded window fitted 17–22 ms, where one detector has no counts at all, and
  returned a background of exactly **0.00 kHz**; the same data over 1–6 ms gives
  2.2 and 3.2 kHz. Nothing about a zero looks wrong on the plot, and every
  corrected quantity downstream is a count minus a background.

Put the window where the points are still dense, and check that the fitted line
lies on them inside the band rather than only crossing it.

## Result

An inter-photon-time histogram (log–log): the short-gap peak is the bright bursts;
the long-gap tail is the Poisson background, whose exponential slope gives the
background rate.

```{figure} figures/background.png
:name: fig-background
:width: 90%

Background from inter-photon times.
```

## See also

- {src}`chisurf/core/fluorescence/burst/background.py`, `.../irf_bg.py`; plugin `burst_background`.
- Tool: **Burst Background Estimation** (`chisurf/plugins/burst/burst_background/`).
