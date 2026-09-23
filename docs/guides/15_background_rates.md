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

The tool is **Background** in the burst workflow (**Spectroscopy ▸ Burst
Analysis**, below the numbered steps); it is not on the menu on its own. Inside
the workflow the measurements and the detector definition come from *1. Data
Selection*, so the panel shows only the file list, the **Estimate background**
action and four docks: **Fit**, **Inter-photon time**, **Background rate**
(per-detector bars) and **Results** (one row per file and detector, in kHz).
Each file's rates are also recorded beside its photons.

```{figure} figures/15_burst_background.png
:name: fig-15-burst-background
:width: 100%

The **Inter-photon time** dock after *Estimate background* on the BH SPC-132
smFRET measurement (green = routing channels 0/8, red = 1/9). Points are the
histogram, lines the fitted exponential tails, the shaded band the fit window
(3.34–4.41 ms, seeded from the data). *Results* reads 1.869 kHz green,
0.968 kHz red.
```

```{figure} figures/15_burst_background_fit.png
:name: fig-15-burst-background-fit
:width: 90%

The **Fit** dock: the window edges (log sliders coupled to the band), the
histogram **Bin width** (0.1 ms) and **Min. counts per bin** (1).
```

The **Fit from** / **Fit to** window is seeded on the first estimate from
quantiles of every detector's inter-photon times (so all detectors have counts
inside it) and is kept on re-estimates; moving a slider re-fits the cached
intervals without re-reading the file. A window holding fewer than three
populated bins for a detector is named in the status line.

Headless, on the same file and window:

```python
import tttrlib
from chisurf.core.fluorescence.burst import background

tttr = tttrlib.TTTR("test/data/tttr/BH/132/BH_SPC132.spc", "SPC-130")
scale = tttr.header.macro_time_resolution * 1e3          # ticks -> ms
dt_ms = background._detector_interphoton_times(tttr, {"chs": [0, 8]}, scale)
rate_khz = background.estimate_background_from_interphoton_times(
    dt_ms, tail_range_ms=(3.335, 4.412))   # 1.869 kHz; omit the window for the fraction rule
```

The `burst-background analyze FILES -s setups.json -n <setup>` command runs the
same estimate over many files, but with the older **fraction rule** only
(`--tail-fraction`, fit from `max(dt)·fraction` to the end); it has no window
option. On this file the fraction rule gives 2.10 / 0.59 kHz and a 1–6 ms window
2.28 / 0.63 kHz, against 1.87 / 0.97 kHz for the seeded window — the rate moves
with the window, which is why the window is the setting to check.

The `burst_irf_bg` step (**IRF & Background**, the next tool in the workflow)
additionally recovers a scatter-derived **IRF** from the same non-burst photons
(the photons the burst search rejects are the built-in scatter/background),
feeding both the correction factors and the MLE lifetime fit — with no separate
buffer acquisition. See [Lifetime from photon bursts](21_lifetime_from_bursts.md).

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
