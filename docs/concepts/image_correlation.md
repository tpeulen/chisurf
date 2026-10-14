---
type: Concept
title: 'Image correlation: one correlation array, four methods'
description: RICS, STICS, TICS and iMSD are computed from the same spatiotemporal correlation array, but they differ in what acquisition they need, where their lag time comes from, what they estimate and what they report.
tags: [concepts, imaging, correlation]
anchor: concept-image-correlation
---

(concept-image-correlation)=
# Image correlation: one correlation array, four methods

RICS, STICS, TICS and iMSD are computed from the same object — the
spatiotemporal correlation of an image stack. Sharing that array is a
computational convenience. They are still **four methods**: they need different
acquisitions, take their lag time from different clocks, use different
estimators and report different observables. This page shows the shared array,
then what separates the methods, then what ChiSurf implements today.

For the confocal single-point analogue, see {ref}`concept-fcs-correlation`; for
the flow-map workflow, the {doc}`pair-correlation guide </guides/55_pair_correlation>`;
for fitting a correlation curve in general, the {doc}`FCS guide </guides/09_diffusion_fcs>`. For
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

Each method reads a different region of it, with a different estimator.

## Three clocks on a raster scan

A laser-scanning microscope does not photograph a frame at an instant. It visits
pixels **one after another**. So within a raster scan a displacement in the
carpet is also a *delay*:

$$
\tau(\xi, \psi, \Delta) = \bigl|\, \xi\,t_\mathrm{pixel}
  + \psi\,t_\mathrm{line} + \Delta\,t_\mathrm{frame} \,\bigr|
$$

The three lag axes are three clocks running at very different rates. The pixel
and line clocks exist only for a sequential raster scan; a camera stack has the
frame clock alone, so it supports STICS, TICS and iMSD but not RICS.

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
A fifth method uses the same array to answer a different kind of question — not
*how fast* but *where to*. Follow the carpet column a distance
$\delta$ away from the origin instead of the one at zero and its peak is the time
molecules take to travel that distance. That is the pair correlation, and it is
what shows a barrier, a connection, or a direction: see
{ref}`concept-pair-correlation`.
```

### Which method is which

| | RICS | STICS | TICS | iMSD |
| --- | --- | --- | --- | --- |
| **Input** | raster scan only | frame series (scanned or camera) | frame series | frame series |
| **Region of $G$** | $\Delta = 0$, intra-frame $\xi, \psi$ | $\Delta > 0$, full $\xi, \psi$ map | $\xi = \psi = 0$ | $\xi, \psi$ at every $\Delta$ |
| **Lag time from** | pixel + line clock | frame clock | frame clock | frame clock |
| **Estimator** | fit the whole map with a scan-convolved model | track the peak **position** against $\Delta$ | fit the amplitude **decay** | track the peak **width** $\sigma^2(\tau)$ |
| **Observable** | $D$, $N$, brightness | a **velocity field** | $\tau_D$, flow, blinking | an **MSD curve** (free, confined or anomalous) |
| **Assumes a transport model** | yes | no | yes | no |

Two consequences matter in practice. STICS follows where the peak *moves*,
model-free and per sub-region, so it yields a map; fitting one global velocity
to the whole carpet is a different and weaker measurement. iMSD reads the
*shape* of $\sigma^2(\tau)$ — a plateau means confinement — so fitting an
anomalous exponent presumes the power law iMSD exists to test.

The family grew roughly in that order. Correlating a *single* frame
against itself came first and gave densities and aggregation states but no
dynamics {cite}`petersen1993`; adding a second colour turned it into a
colocalisation measurement {cite}`wiseman2000`. The step that produced RICS was
the realisation that a raster scan is not one instant — the pixel and line dwell
times already stamp a range of lag times onto a perfectly ordinary image stack,
so the dynamics were in data everyone was already collecting
{cite}`digman2005b`. Correlating in the spatial-frequency domain instead of real
space separates directed flow from diffusion more cleanly than fitting a
drifting peak {cite}`kolin2006`.

## The model ChiSurf fits

ChiSurf fits the carpet with one Gaussian transport model. A mobile species with $N$ particles in the
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

**The width term is not an iMSD.** The spatial Gaussian has width
$w_r^2 + \mathrm{MSD}(\tau)$, the quantity an iMSD analysis measures slice by
slice. Fitting it here imposes $\mathrm{MSD} = 4D\tau^\alpha$; an iMSD reads
$\sigma^2(\tau)$ without that assumption, which is what lets it show
confinement. A model-free width readout is not implemented yet.

**$\alpha$ is an anomalous-diffusion fit.** At $\alpha = 1$,
$\mathrm{MSD} = 4D\tau$ and $D$ is a diffusion coefficient in µm²/s. Releasing
$\alpha$ fits subdiffusion ($\alpha < 1$, crowding, transient binding) or
superdiffusion ($\alpha > 1$). As in FCS, **one anomalous component and two
normal components fit almost equally well**, so do not release $\alpha$ and add
a second component and expect either to be meaningful.

## Using it in ChiSurf

The reader setting **Max frame lag Δ** decides how much of the carpet is
computed:

- `0` — the zero-frame-lag slice only: a RICS map.
- `> 0` — the carpet extended along the frame axis, which the model above is
  then fitted against at every lag at once.

The model's optional terms all start at a **neutral value that switches them
off**:

| Release this | To fit |
| --- | --- |
| `alpha` | anomalous diffusion |
| `aT` | triplet/blinking |
| `N_imm` | an immobile fraction |
| `v_x`, `v_y` | one uniform flow or drift over the whole field |
| `sx`, `sy` | a cross-correlation displacement (ccRICS) |

Releasing `v_x`, `v_y` is not STICS: it fits one velocity, not a field. The
STICS velocity **map** — per-tile peak tracking — is the
**Flow Maps** tool (`chisurf/plugins/microscopy/img_flow/`). TICS decay models
and an iMSD width readout are not implemented yet.

## Failure modes

**The frame time is a silent multiplier.** It converts $\Delta$ into seconds, so
every $D$ derived from frame lags scales with it. With **Frame dur** left at
zero, ChiSurf estimates it as
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
asked to absorb. Use the reader's **Subtract avg** (`frame` or `stack`), and
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

## References

- {cite}`petersen1993` — image correlation spectroscopy: the spatial
  autocorrelation of one frame, read as cluster density and aggregation state.
- {cite}`wiseman2000` — ICS at video rate and its two-colour cross-correlation
  form, the basis of image cross-correlation.
- {cite}`digman2005b` — RICS: the scan's own pixel and line clocks as the lag
  axis, which is what makes a normal image stack yield $D$.
- {cite}`kolin2006` — k-space ICS, separating flow from diffusion in the
  spatial-frequency domain.
- {cite}`digman2008b` — Number & Brightness: per-pixel mean and variance mapped
  to oligomeric state, the imaging counterpart of {ref}`concept-pch-fida`.
  In ChiSurf: {ref}`concept-number-and-brightness`.

## See also

- Tools in ChiSurf: **RICS-Precision** (`chisurf/plugins/calculator/rics_precision/`) for choosing the dwell time, and **Flow Maps** (`chisurf/plugins/microscopy/img_flow/`) for the STICS velocity field.
