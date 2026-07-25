---
type: Reference
title: "Image correlation: RICS, STICS, TICS and iMSD are one method"
description: The single spatiotemporal correlation carpet G(xi, psi, Delta) behind the image-correlation family, the lag-time identity that unifies it, and how ChiSurf implements it as one correlator and one fit model.
tags: [reference, imaging, ics, rics, stics, tics, imsd, diffusion]
timestamp: '2026-07-25T00:00:00Z'
---

# Image correlation: RICS, STICS, TICS and iMSD are one method

The literature presents Raster Image Correlation Spectroscopy (RICS),
Spatiotemporal Image Correlation Spectroscopy (STICS), Temporal Image
Correlation Spectroscopy (TICS) and image Mean Square Displacement (iMSD) as
four techniques, each with its own acronym, papers and software modules. They
are not four techniques. They are four ways of reading one object.

## The one object

Correlate an image stack with itself over a lag in the fast (pixel) scan
direction `xi`, a lag in the slow (line) direction `psi`, and a lag in whole
frames `Delta`. The result is a three-dimensional **correlation carpet**

```
G(xi, psi, Delta)
```

Every named method is a region of this carpet.

## The one identity

What makes the carpet a *physical* measurement rather than an array of numbers
is that a laser-scanning microscope visits pixels **sequentially**. A
displacement in the carpet is therefore a delay:

```
tau(xi, psi, Delta) = | xi*t_pixel + psi*t_line + Delta*t_frame |
```

This is the whole unification. The three lag axes are three clocks running at
wildly different rates, and the named methods are simply which clock dominates:

| Method | Region of the carpet | Lag time it probes | Typical scale |
| --- | --- | --- | --- |
| RICS  | `Delta = 0` | `xi*t_pixel + psi*t_line` | µs to ms |
| STICS | `Delta > 0` | `Delta*t_frame` | ms to s |
| TICS  | `xi = psi = 0` | `Delta*t_frame` only | ms to s |
| iMSD  | all `Delta` | width of each slice vs `tau` | µs to s |

A worked example makes the spread concrete. With a 10 µs pixel dwell, a 3 ms
line time and a 0.6 s frame time, one step along each axis costs:

```
one pixel  ->  10 µs
one line   ->   3 ms      (300x more)
one frame  ->  0.6 s      (200x more again)
```

A single RICS map already spans four decades of lag time internally — that is
precisely why one image, with no time series at all, is sensitive to diffusion.
Adding frame lags does not change the physics; it extends the same carpet by
two more decades.

## Why the separate names are misleading

* **RICS is not "the spatial one".** It is time-resolved; its time axis is the
  scan pattern rather than the frame counter.
* **TICS is not "the temporal one".** It is the single point `xi = psi = 0` of
  every STICS slice — the least informative column of the carpet, discarding all
  spatial information.
* **iMSD is not a different correlation.** It is a two-step reading of the same
  slices: fit a Gaussian width to each `Delta` slice, then plot width against
  `tau`. Since the model's Gaussian width is `w_r^2 + MSD(tau)` by construction,
  fitting the whole carpet at once does the same job in one step, with the PSF
  width as an explicit parameter instead of an extrapolated intercept.
* **Fitting them separately throws away constraints.** The same `D` and the same
  `N` appear in every region. Fitting RICS alone, then TICS alone, produces two
  estimates of one quantity from disjoint subsets of one dataset.

## How ChiSurf implements it

One correlator and one model, in `chisurf/core/experiments/ics/` and
`chisurf/core/models/ics/`.

**The correlator.** `compute_ics_carpet(images, settings)` returns an
`IcsCarpet`: `correlation` of shape `(n_lags, ny, nx)`, the two spatial lag
grids, the frame lags, and an `IcsTiming` carrying `t_pixel`/`t_line`/`t_frame`.
The reader setting **`max_frame_lag`** is the only control that separates the
methods: `0` correlates the zero-lag slice only (a classic RICS map), higher
values extend the same carpet along time. The named readings are methods on the
carpet — `rics_map()`, `stics_map(delta)`, `tics_curve()`, `lag_time_grid()` —
not separate code paths.

**The model.** `image_correlation(xi, psi, Delta, ...)` is a single function over
all three lag axes:

```
G = G_0 + gamma/(N + N_imm)^2 * [ N*T(tau)*D(tau)*S(xi, psi, tau)
                                + N_imm*S_imm(xi, psi) ]
```

with `MSD(tau) = 4*D*tau^alpha` entering the spatial term as
`exp(-(dx^2 + dy^2) / (w_r^2 + MSD))`. Every optional term is written so that
its **neutral value switches it off**: `alpha = 1` is normal diffusion,
`a_T = 0` removes blinking, `N_imm = 0` removes the immobile component, zero
velocities remove flow. The model therefore opens as plain one-component
diffusion and becomes anomalous/iMSD, blinking, two-component or flow-resolved
by releasing one parameter — not by picking a different model from a list.

**In the GUI**, the 2D plot carries a frame-lag slider (Δ) and a
Residual/Data/Model source selector, so the carpet is browsable along time
rather than collapsed to a single map.

## Consequences worth knowing

* **Cost is linear in lags.** Each frame lag is a full FFT pass over all frame
  pairs at that lag. `max_frame_lag = 10` costs roughly ten RICS maps.
* **Pairs run out.** A stack of `n` frames yields `n - Delta` pairs at lag
  `Delta`, so the highest lags are the noisiest slices. The carpet's `error`
  array is the standard error over those pairs and shrinks accordingly.
* **The frame time must be right.** It is what converts `Delta` into seconds.
  When unset, ChiSurf estimates it as `n_lines * t_line`, which is exact only
  for a scanner without inter-frame dead time — a real dead time biases every
  `D` fitted from frame lags. Set it explicitly when it matters.
* **Immobile structures dominate long lags.** The static term is
  lag-independent, so at large `Delta` the carpet is mostly immobile signal;
  this is a feature (it separates the fractions) but it means `N_imm` should be
  released whenever frame lags are included.

## Pointers

* Correlator: `chisurf/core/experiments/ics/ics_core.py`, containers and the
  lag-time identity in `.../ics/data.py`.
* Model: `chisurf/core/models/ics/models.py`, fit classes in `.../ics/ics.py`.
* Tests: `test/experiments/test_ics_unification.py` pins the identities above;
  `test/experiments/test_ics_vs_pam.py` cross-checks the zero-lag slice against
  an established implementation's stored correlation on a real EGFP dataset.
* User-facing guide: `docs/concepts/image_correlation.md`.
