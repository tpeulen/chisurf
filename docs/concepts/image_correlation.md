---
type: Concept
title: 'Image correlation: RICS, STICS, TICS and iMSD are one method'
description: Four acronyms appear in the image-correlation literature — RICS, STICS, TICS and iMSD — and they are usually taught as four techniques with four workflows.
tags: [concepts, imaging, correlation]
anchor: concept-image-correlation
---

(concept-image-correlation)=
# Image correlation: RICS, STICS, TICS and iMSD are one method

Four acronyms appear in the image-correlation literature — RICS, STICS, TICS and
iMSD — and they are usually taught as four techniques with four workflows. They
are not. They are four ways of reading **one** object, and this page is mostly
about making that concrete, because once you see it the parameter choices in
ChiSurf stop being arbitrary.

For the step-by-step workflow, see the {doc}`FCS guide </guides/09_diffusion_fcs>`;
for the confocal single-point analogue, see {ref}`concept-fcs-correlation`. For
choosing the scan settings *before* recording — the dwell time is a physics
parameter, not a convenience — see {ref}`concept-scan-precision`.

## The object: a correlation carpet

Take a stack of images of a fluorescent sample. Correlate it with itself over
three lags at once:

- $\xi$ — a shift along the **fast** (pixel) scan direction,
- $\psi$ — a shift along the **slow** (line) direction,
- $\Delta$ — a shift in whole **frames**.

The result is a three-dimensional **correlation carpet**

$$
G(\xi, \psi, \Delta).
$$

Everything below is a region of this carpet.

## The identity that unifies everything

A laser-scanning microscope does not photograph a frame at an instant. It visits
pixels **one after another**. So a displacement in the carpet is not just a
displacement — it is a *delay*:

$$
\tau(\xi, \psi, \Delta) = \bigl|\, \xi\,t_\mathrm{pixel}
  + \psi\,t_\mathrm{line} + \Delta\,t_\mathrm{frame} \,\bigr|
$$

That is the entire unification. The three lag axes are three clocks running at
very different rates.

### Worked numbers

Take a typical confocal raster: 10 µs pixel dwell, 3 ms per line, 0.6 s per
frame. One step along each axis costs:

| Step | Lag time | Ratio to previous |
| --- | --- | --- |
| one pixel, $\xi = 1$ | 10 µs | — |
| one line, $\psi = 1$ | 3 ms | ×300 |
| one frame, $\Delta = 1$ | 0.6 s | ×200 |

Within a **single frame**, scanning 100 lines already spans 10 µs to 0.3 s. This
is the answer to the question people usually ask first about RICS — *how can one
image measure diffusion?* — the image is not one time point. It is a time series
smeared across space by the scan pattern.

```{note}
There is a **fifth** reading of the same carpet, and it answers a different kind
of question — not *how fast* but *where to*. Follow the carpet column a distance
$\delta$ away from the origin instead of the one at zero and its peak is the time
molecules take to travel that distance. That is the pair correlation, and it is
what shows a barrier, a connection, or a direction: see
{ref}`concept-pair-correlation`.
```

### Which method is which

| Method | Region read | Clock that dominates | Scale |
| --- | --- | --- | --- |
| **RICS** | $\Delta = 0$ | pixel + line | µs–ms |
| **STICS** | $\Delta > 0$ | frame | ms–s |
| **TICS** | $\xi = \psi = 0$ | frame only | ms–s |
| **iMSD** | all $\Delta$ | width of each slice vs $\tau$ | µs–s |

Reading that table the other way round is more useful: **TICS is one column of
STICS**, throwing away all spatial information. **RICS is one slice of STICS**,
the one at zero frame lag. **iMSD is a two-step summary** of the same slices.

## What the model says

One function covers all of it. A mobile species with $N$ particles in the
detection volume, a lateral waist $w_r$ and an axial waist $w_z$ gives

$$
G(\xi, \psi, \Delta) = G_0 + \frac{\gamma}{N}\,
  \underbrace{T(\tau)}_{\text{blinking}}\;
  \underbrace{\Bigl(1 + \tfrac{\mathrm{MSD}}{w_r^2}\Bigr)^{-1}
              \Bigl(1 + \tfrac{\mathrm{MSD}}{w_z^2}\Bigr)^{-1/2}}_{\text{amplitude decay}}\;
  \underbrace{\exp\!\left[-\frac{\delta x^2 + \delta y^2}{w_r^2 + \mathrm{MSD}}\right]}_{\text{spatial correlation}}
$$

with the mean square displacement

$$
\mathrm{MSD}(\tau) = 4 D \tau^{\alpha}
$$

and $\delta x, \delta y$ the scan displacement in µm, reduced by any flow
travelled during $\tau$.

Two things are worth staring at.

**The width term is the iMSD.** The Gaussian in the spatial factor has width
$w_r^2 + \mathrm{MSD}(\tau)$. An iMSD analysis fits a Gaussian to each frame-lag
slice, plots the fitted width against $\tau$, and reads the slope as $4D$ — with
the intercept giving $w_r^2$. Fitting the carpet with this model does the same
thing in one step, and $w_r$ is an explicit parameter rather than an
extrapolation. Both routes answer the same question; the joint fit uses more of
the data.

**$\alpha$ is the only thing separating "normal" from "anomalous".** At
$\alpha = 1$, $\mathrm{MSD} = 4D\tau$ and $D$ is a diffusion coefficient in
µm²/s. Release $\alpha$ and you have subdiffusion ($\alpha < 1$, crowding,
transient binding) or superdiffusion ($\alpha > 1$, directed transport). The
caveat familiar from FCS applies here too: **one anomalous component and two
normal components fit almost equally well**, so do not release $\alpha$ and add a
second component and expect either to be meaningful.

## Using it in ChiSurf

The reader setting that decides which "method" you are doing is
**Max frame lag Δ**:

- `0` — correlate the zero-lag slice only. This is a classic RICS map.
- `> 0` — extend the same carpet along time. STICS, TICS and iMSD all become
  readable from it, and the fit sees every lag at once.

Everything else follows from the model's parameters, all of which start at a
**neutral value that switches their term off**:

| Release this | To fit |
| --- | --- |
| `alpha` | anomalous transport (the iMSD case) |
| `a_T` | triplet/blinking |
| `N_imm` | an immobile fraction |
| `v_x`, `v_y` | uniform flow or drift |
| `s_x`, `s_y` | a cross-correlation displacement (ccRICS) |

So there is no model picker with six near-identical entries. There is one model,
and you decide what physics it contains by choosing what to release.

## Failure modes

**The frame time is a silent multiplier.** It converts $\Delta$ into seconds, so
every $D$ derived from frame lags scales with it. ChiSurf estimates it as
(lines per frame) × (line time) when you leave it at zero, which is exact only if
the scanner has no inter-frame dead time. A 20 % dead time you did not account
for is a 20 % error in $D$ — set it explicitly when it matters.

**High lags are the noisiest data.** A stack of $n$ frames yields only
$n - \Delta$ frame pairs at lag $\Delta$. The last few lags of a long carpet are
averaged over a handful of pairs and will pull a fit around if you weight them
equally. The carpet's error array reflects this; check it before trusting a
long-lag feature.

**Immobile structure dominates long lags.** The static term does not decay, so at
large $\Delta$ most of what remains is immobile signal. That is useful — it is
how the mobile and immobile fractions separate — but it means `N_imm` should be
released whenever you include frame lags, or the fit will inflate $N$ to absorb
it.

**Diffusion can be too fast for the frame axis.** If the species decorrelates
within one frame time, every $\Delta > 0$ slice is flat and only the offset
survives. That is not a failed measurement; it is the carpet telling you the
motion lives in the RICS region. On a typical EGFP-in-solution dataset with
0.67 s frames, the correlation is entirely gone by the first frame lag — the
information is all in the pixel/line lags.

**Bleaching looks like slow diffusion.** A monotonic intensity decay across the
stack adds a slow decay to the frame-lag axis that no diffusion model should be
asked to absorb. Use the frame- or stack-average subtraction in the reader, and
be suspicious of a fitted $D$ that depends strongly on how many frame lags you
included.

## Runnable examples

* `examples/notebooks/RICS_Simulation_And_Recovery.ipynb` (with its `.py`
  cell-script twin) — raster-scan a freely diffusing population with a known
  `D`, look at the images and the correlation map, and fit `D` back out. It
  makes the fast/slow axis asymmetry visible, shows the `N`-`D`-waist
  degeneracy, finds the slow end of the working range, and demonstrates the
  three ways to produce a scan that looks healthy and carries no diffusion
  information at all.

## See also

- Tools in ChiSurf: **RICS-Precision** (`chisurf/plugins/calculator/rics_precision/`) for choosing the dwell time, and **Flow Maps** (`chisurf/plugins/microscopy/img_flow/`) for the STICS velocity field.
