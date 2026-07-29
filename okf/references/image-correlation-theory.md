---
type: Reference
title: "Image correlation: four methods over one correlation carpet"
description: The spatiotemporal correlation carpet G(xi, psi, Delta) shared by RICS, STICS, TICS and iMSD, the lag-time relation that links its axes, and where the four methods genuinely differ — inputs, estimators and observables.
tags: [reference, imaging, ics, rics, stics, tics, imsd, diffusion]
timestamp: '2026-07-25T00:00:00Z'
---

# Image correlation: four methods over one correlation carpet

Raster Image Correlation Spectroscopy (RICS), Spatiotemporal Image Correlation
Spectroscopy (STICS), Temporal Image Correlation Spectroscopy (TICS) and image
Mean Square Displacement (iMSD) are **four distinct methods**. They differ in what
they require of the acquisition, where their lag time comes from, which estimator
they apply, and what they measure.

What they *share* is a computational substrate: all four are read off one
spatiotemporal correlation array. That is worth exploiting in code — one
correlator serves all of them — but sharing a correlation routine is a
computational convenience, **not** a methodological identity. Compute the carpet
once; then apply four different estimators to it.

| | RICS | STICS | TICS | iMSD |
| --- | --- | --- | --- | --- |
| Input | raster scan **only** | frame series (scan or camera) | frame series | frame series |
| Estimator | fit the map with a scan-convolved model | track peak **position** vs `Delta` | fit the amplitude **decay** | track peak **width** vs `tau` |
| Observable | `D`, `N`, brightness | **velocity vector field** | `tau_D`, flow, blinking | **MSD curve** (free/confined/anomalous) |
| Assumes a transport model | yes | no | yes | **no** |
| Needs the scan term `S(xi, psi)` | **yes** | no | no | no |

A camera-acquired stack therefore supports STICS, TICS and iMSD but **not** RICS:
RICS's time axis *is* the raster scan, and a camera frame has no such clock.

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
Adding frame lags extends the accessible range by two more decades.

**The relation is not a licence to mix the clocks.** `xi*t_pixel + psi*t_line`
describes sequential visiting of pixels *within one frame*; it belongs to RICS.
At `Delta > 0` the frame time dominates by orders of magnitude and the intra-frame
terms are normally dropped, and on a camera stack they do not exist at all.

## What the separate names do and do not mean

* **RICS is not "the spatial one".** It is time-resolved; its time axis is the
  scan pattern rather than the frame counter.
* **TICS is not "the temporal one".** It is the single point `xi = psi = 0` of
  every STICS slice — the least informative column of the carpet, discarding all
  spatial information.
* **STICS is not RICS with a velocity parameter.** Its estimator is the
  *displacement of the correlation peak* between frame lags — model-free, and
  computed **per sub-region** to yield a velocity **field**. A single global
  velocity fitted to a whole-field correlation presumes one uniform flow and a
  transport model, and cannot produce a map.
* **iMSD is not an anomalous-diffusion fit.** It fits a Gaussian *width* to each
  `Delta` slice and plots that width against `tau`; the **shape** of the resulting
  curve is the result — a plateau means confinement, curvature means anomalous
  transport. Fitting the carpet with `MSD(tau) = 4*D*tau^alpha` instead *presumes*
  the power law that iMSD exists to test, and a confined trajectory has no
  `alpha` that reproduces its plateau.
* **Joint fitting shares constraints — where the methods genuinely overlap.** The
  same `D` and `N` enter the regions that assume the same transport model, so
  fitting those together beats fitting them from disjoint subsets. This argument
  does not extend to the model-free estimators (STICS peak tracking, iMSD width),
  whose point is to *avoid* assuming that model.

## How ChiSurf implements it

One correlator and — **today** — one model, in `chisurf/core/experiments/ics/` and
`chisurf/core/models/ics/`. The shared correlator is the right design. The single
model is not: it conflates four methods into one parameterisation. Splitting them
into distinct selectable models, and adding the model-free STICS and iMSD
estimators the current code lacks, is [PRD-51](/prds/prd-51.md).

**The correlator.** `compute_ics_carpet(images, settings)` returns an
`IcsCarpet`: `correlation` of shape `(n_lags, ny, nx)`, the two spatial lag
grids, the frame lags, and an `IcsTiming` carrying `t_pixel`/`t_line`/`t_frame`.
The reader setting **`max_frame_lag`** controls how much of the carpet is
computed: `0` correlates the zero-lag slice only (all RICS needs), higher values
extend it along time (what STICS, TICS and iMSD read). Accessors select the region
each method uses — `rics_map()`, `stics_map(delta)`, `tics_curve()`,
`lag_time_grid()`. Selecting a region is not the same as applying a method: the
estimators that make a region *into* STICS or iMSD are what PRD-51 adds.

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
diffusion and becomes anomalous, blinking, two-component or flow-resolved by
releasing one parameter.

**Do not read those switches as method selection.** Releasing `alpha` gives an
anomalous-diffusion fit, not iMSD; releasing `v_x`/`v_y` gives a globally fitted
uniform flow, not STICS. Both are legitimate fits and both are *weaker* than the
methods whose names they resemble, because they assume the transport model that
the real estimators avoid. See [PRD-51](/prds/prd-51.md).

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
