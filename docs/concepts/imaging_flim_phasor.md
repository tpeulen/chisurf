---
type: Concept
title: FLIM and the phasor approach
description: 'Fluorescence-lifetime imaging microscopy (FLIM) turns a decay time into a contrast mechanism: each pixel of an image carries not just a brightness but a fluorescence lifetime that reports on the fluorophore''s environment…'
tags: [concepts, imaging, flim, phasor, tcspc, lifetime, decay]
anchor: concept-imaging-flim-phasor
---

(concept-imaging-flim-phasor)=
# FLIM and the phasor approach

Fluorescence-lifetime imaging microscopy (FLIM) turns a **decay time** into a
**contrast mechanism**: each pixel of an image carries not just a brightness but a
fluorescence lifetime that reports on the fluorophore's environment — refractive
index, ion concentration, pH, binding state, and, crucially, FRET. This page
explains how ChiSurf builds lifetime images from a confocal photon stream and how
the **phasor approach** lets you read those images *without fitting a single pixel*.

For the step-by-step workflow in ChiSurf, see the guide
{doc}`/guides/24_scan_images`.

## From a photon stream to a lifetime image

A laser-scanning confocal microscope (CLSM) has no camera. It builds an image by
rastering a diffraction-limited focus across the sample while an avalanche
photodiode counts photons. In a TTTR (time-tagged time-resolved) measurement each
photon carries three numbers:

- a **macro time** — when it arrived, coarsely, which the frame / line / pixel
  markers in the stream turn into a scan position $(x, y)$;
- a **micro time** $t$ — its delay after the exciting laser pulse (the TCSPC
  channel);
- a detection channel.

A **pixel** is therefore just *the set of photons recorded while the focus sat at
that scan position*. Accumulate their micro times into a histogram and you have a
per-pixel fluorescence decay $I(t)$. The intensity image is the photon count per
pixel; the **lifetime image** is a summary of the *shape* of each pixel's decay.

For a single fluorescing species the decay is a mono-exponential
$I(t) = I_0\,e^{-t/\tau}$, and $\tau$ (a few ns) is the observable. Real pixels mix
species, so the decay is multi-exponential and a single "lifetime" is only an
apparent, intensity-weighted average. Two routes summarize a pixel:

- **Fitting** — fit each pixel's decay to an exponential model (ChiSurf's
  per-pixel maximum-likelihood tools). Accurate, but slow, and it needs enough
  photons per pixel to constrain the model.
- **The phasor transform** — a fit-free, model-free projection that maps every
  pixel's *whole decay* to a single point in a 2-D plane.

## The phasor transform

The phasor sends a pixel's decay $I(t)$ to a pair of coordinates $(g, s)$ — the
cosine- and sine-weighted moments of the decay, normalized by its integral:

$$
g(\omega) = \frac{\displaystyle\int_0^\infty I(t)\,\cos(\omega t)\,\mathrm{d}t}
                  {\displaystyle\int_0^\infty I(t)\,\mathrm{d}t},
\qquad
s(\omega) = \frac{\displaystyle\int_0^\infty I(t)\,\sin(\omega t)\,\mathrm{d}t}
                  {\displaystyle\int_0^\infty I(t)\,\mathrm{d}t}.
$$

Here $\omega = 2\pi f$ is the angular **laser repetition frequency** (or a harmonic
$n\omega$). $(g, s)$ are just the real and imaginary parts of the first Fourier
component of the decay, normalized so that the total intensity drops out — the
phasor sees the decay's *shape*, not its brightness. Plotting $s$ against $g$ for
every pixel gives the **phasor plot**, a 2-D map in which each pixel is one dot.

This is the whole idea: a slow, noisy, high-dimensional per-pixel decay becomes a
single robust point. The transform is a sum, so it is fast, needs no starting
guess, and degrades gracefully with few photons. The mapping is also
**reciprocal** — you can select a region in the phasor plot and paint back exactly
the image pixels that fall in it (ROI back-projection).

## The universal semicircle

The power of the phasor plot comes from a geometric fact. A **single exponential**
of lifetime $\tau$ transforms to

$$
g = \frac{1}{1 + (\omega\tau)^2},
\qquad
s = \frac{\omega\tau}{1 + (\omega\tau)^2},
$$

and these coordinates satisfy

$$
\left(g - \tfrac{1}{2}\right)^2 + s^2 = \left(\tfrac{1}{2}\right)^2 .
$$

Every possible mono-exponential lifetime therefore lands on a **semicircle of
radius $\tfrac12$ centred at $(\tfrac12, 0)$** — the *universal circle*. It is
universal because it does not depend on the sample, only on $\omega$. Reading it is
intuitive:

- $\tau = 0$ sits at $(1, 0)$, the right end (infinitely fast, no delay);
- $\tau \to \infty$ sits at $(0, 0)$, the left end;
- **short lifetimes are on the right, long lifetimes on the left**, sweeping
  counter-clockwise as $\tau$ grows. The apex of the arc corresponds to
  $\omega\tau = 1$.

A pixel that contains a **mixture** of species does *not* lie on the circle. By the
linearity of the transform, its phasor is the **intensity-weighted vector sum** of
the component phasors, so a multi-exponential pixel lands **inside** the arc, on the
line segment (or polygon) joining its pure components. Anything strictly inside the
circle is, by construction, multi-exponential.

```{figure} figures/phasor_circle.png
:name: fig-phasor-circle
:width: 100%

**The universal circle at 80 MHz.** Single exponentials land on the arc — marked at 0.5, 1, 2, 4 and 8 ns, short lifetimes to the right. A pixel mixing a 0.6 ns and a 4 ns species lies on the chord between them, at the position the lever rule gives for its fractional intensities (quarter points shown). Anything strictly inside the arc is multi-exponential; nothing outside it is physical.
```

## Apparent lifetimes

A phasor in polar form is a phase $\varphi = \arctan(s/g)$ and a modulation
$M = \sqrt{g^2 + s^2}$ — the two numbers a frequency-domain fluorometer measures
directly. Inverting the single-exponential relations $\tan\varphi = \omega\tau$
and $M = 1/\sqrt{1 + (\omega\tau)^2}$ gives two lifetimes from every point:

$$
\tau_\varphi = \frac{1}{\omega}\,\frac{s}{g},
\qquad
\tau_M = \frac{1}{\omega}\sqrt{\frac{1}{g^2 + s^2} - 1}.
$$

$\tau_\varphi$ is constant along a ray from the origin (**iso-phase** line), $\tau_M$
along an arc centred on the origin (**iso-modulation** arc); both lines cross on the
semicircle at the lifetime they name. On the circle $\tau_\varphi = \tau_M = \tau$.
Inside it, for any mixture of exponentials, $\tau_\varphi < \tau_M$
{cite}`jameson1984`, and neither equals the intensity-weighted mean lifetime. A
50:50 photon mixture of 0.6 ns and 5 ns at 80 MHz reads $\tau_\varphi = 1.17$ ns and
$\tau_M = 2.58$ ns, against a mean of 2.8 ns. The gap between the two is itself a
heterogeneity readout; a single "phasor lifetime" quoted without saying which is
ambiguous by up to a factor of two.

## Harmonics

The transform can be taken at any integer multiple $n\omega$ of the repetition
frequency. The $n$-th harmonic of a single exponential is

$$
g_n = \frac{1}{1 + (n\omega\tau)^2},
\qquad
s_n = \frac{n\omega\tau}{1 + (n\omega\tau)^2},
$$

so every harmonic has its own universal semicircle, with lifetimes spread along it
by $n\omega\tau$ instead of $\omega\tau$. Two uses follow.

- **Placing lifetimes where they resolve.** Angular separation on the arc is
  largest near its apex, $n\omega\tau = 1$. At 80 MHz the apex sits at 2 ns; a
  sample whose lifetimes are 0.3–0.6 ns crowds against $(1, 0)$ at $n = 1$ and
  spreads out at $n = 2$ or $3$.
- **Counting components.** A single exponential lies on the circle at *every*
  harmonic, with the same $\tau_\varphi = \tau_M$. A mixture falls inside, and its
  apparent lifetimes move with $n$ because each component is re-weighted by its
  own $n\omega\tau$. Each harmonic adds two equations, which is what lets more than
  two components be resolved in one pixel {cite}`vallmitjana2020`. Measured on the
  repository's donor-only and donor–acceptor decays (`test/data/tcspc/ibh_sample`,
  IRF-corrected, fundamental 17.3 MHz): the donor-only $\tau_\varphi$ stays at 4.15,
  4.12, 4.08 ns for $n = 1, 2, 3$, while the donor–acceptor sample falls
  3.21 → 2.96 → 2.67 ns with $\tau_M$ at 3.72, 3.67, 3.56 ns — a quenched
  sub-population that no single harmonic names but the trend reveals.

Higher harmonics carry less signal: $M_n$ falls as $1/(n\omega\tau)$ and the IRF's
own modulation falls with $n$, so the noise in $(g_n, s_n)$ grows. One or two
harmonics above the fundamental are usually all the data support.

## Fractions by the lever rule

Because mixing is linear, composition is read off *geometrically*. If a pixel is a
blend of two species whose pure phasors are $P_1$ and $P_2$, its phasor lies on the
chord $\overline{P_1 P_2}$, and its position along that chord gives the fractional
intensities by the **lever rule**:

$$
f_1 = \frac{\lvert P - P_2\rvert}{\lvert P_1 - P_2\rvert},
\qquad
f_2 = 1 - f_1 .
$$

The closer the pixel phasor sits to a vertex, the larger that component's
fractional-intensity contribution. With three components the pixel falls inside the
triangle $P_1 P_2 P_3$ and the fractions are the barycentric weights. This
**graphical unmixing** replaces per-pixel fitting entirely: no model, no starting
values, no convergence — just distances on a plot.

The weights are **fractional intensities** (photon fractions), not the
pre-exponential amplitudes a fit reports. For $I(t) = \sum_i a_i e^{-t/\tau_i}$,

$$
P = \sum_i f_i\,P(\tau_i),
\qquad
f_i = \frac{a_i\tau_i}{\sum_j a_j\tau_j},
$$

so a long-lived minority species pulls the phasor further than its amplitude
suggests. Convert with $a_i \propto f_i/\tau_i$ before comparing with a fit.

### Two components of unknown lifetime

The lever rule needs the pure phasors. When they are unknown but every pixel is a
mixture of the *same* two single-exponential species, the pixel cloud lies on one
chord, and the chord's ends are the answer. Fit a straight line $s = v\,g + u$
through the cloud; it meets the circle where $s/g = \omega\tau$, which gives
{cite}`clayton2004`

$$
\tau_{1,2} = \frac{1 \pm \sqrt{1 - 4u(u + v)}}{2\omega u}.
$$

This is the imaging form of the older result that phase and modulation at one
frequency determine two lifetimes and their fraction {cite}`weber1981`. It fails
quietly when either species is itself multi-exponential — the cloud is then no
longer on a chord whose ends are on the circle — so check that the cloud is
linear before trusting the intersections.

## Calibration

The raw phasor of a real measurement is rotated and scaled away from the ideal
circle by the instrument response — the finite width of the laser pulse and the
detector/electronics timing (the IRF). Phasor FLIM handles this without
deconvolution by a one-point **calibration**: measure a **reference dye of known,
single lifetime** $\tau_R$ (e.g. a standard fluorophore in solution),
compute where its phasor *should* sit on the universal circle, and derive the fixed
rotation and scaling that move the measured reference point onto that ideal
position. The same correction is then applied to every pixel of the sample. After
calibration, sample phasors sit in true coordinates and lifetimes can be read
directly off the circle.

### The correction as arithmetic

Write the phasor as a complex number, $P = g + i s$. The measured decay is the
true decay convolved with the IRF, and the Fourier transform turns convolution
into multiplication; because each phasor is normalized by its own integral,

$$
P_\text{meas} = P_\text{IRF}\,P_\text{true}
\quad\Longrightarrow\quad
P_\text{true} = \frac{P_\text{meas}}{P_\text{IRF}}
$$

at each harmonic {cite}`redford2005`. In polar form the division is a rotation
and a rescaling: $\varphi_\text{true} = \varphi_\text{meas} - \varphi_\text{IRF}$,
$M_\text{true} = M_\text{meas}/M_\text{IRF}$.

A measured IRF gives $P_\text{IRF}$ directly. A **reference of known lifetime** $\tau_R$
gives it indirectly — which is the usual route, because a reference dye is
recorded under the same conditions as the sample (same emission path, same
detector colour response) and a scatter IRF is not {cite}`digman2008,stefl2011`:

$$
P_\text{IRF} = \frac{P_{R,\text{meas}}}{P(\tau_R)},
\qquad
\Delta\varphi = \arctan(\omega\tau_R) - \varphi_{R,\text{meas}},
\qquad
m = \frac{1}{M_{R,\text{meas}}\sqrt{1 + (\omega\tau_R)^2}},
$$

and every sample pixel is rotated by $\Delta\varphi$ and scaled by $m$
{cite}`ranjit2018`. Two conditions make it exact: the reference must be a single
exponential at the frequency used, and $\omega$ must be the true repetition
frequency (or a harmonic of it) with the decay fully relaxed within one period —
a TCSPC window shorter than the period truncates the decay, and the truncated
decay's phasor is no longer on the circle.

On the donor-only decay in `test/data/tcspc/ibh_sample` (window as period,
17.3 MHz), $P_\text{meas}/P_\text{IRF}$ lands 0.0008 outside the circle — on it,
within noise — at $\tau_\varphi = 4.15$ ns and $\tau_M = 4.12$ ns, against 4.15 ns
from a mono-exponential reconvolution fit of the same file.

## Fit-free FLIM and FRET by phasor

With the plot calibrated, two everyday tasks become inspection rather than
computation:

- **Fit-free lifetime maps.** Read a pixel's **apparent (phase / modulation)
  lifetime** from its angle and radius, or segment the image by drawing cursors on
  clusters in the phasor plot and back-projecting them — every pixel in a cluster
  shares a photophysical state, so distinct environments separate as distinct
  clouds.

  A cursor is a {ref}`region <concept-region-properties>` on the $(g, s)$ plane,
  the same object that selects pixels on a frame — only the axes differ. The
  classic circle and ellipse are the common cases, but a cluster that is neither
  can be enclosed by a polygon, and two cursors combine (a ring is
  `outer - inner`) without anything special. Cursors serialise with the project
  and travel over RPC, so a gate drawn once can be replayed on the next
  measurement.

- **FRET as a trajectory.** FRET shortens the donor lifetime, so as transfer
  efficiency rises the donor phasor moves **off** its unquenched position on the
  circle **toward shorter lifetime**, along a predictable **FRET trajectory**. A
  pixel's distance along that trajectory is its FRET efficiency; because unquenched
  donors, background, and autofluorescence each have their own phasor, the trajectory
  is a curve (not a straight chord) that accounts for the non-FRETing fraction. You
  read $E$ per pixel by projecting onto this curve — again, with no fitting.

The trade-off is the usual one: phasors give speed, robustness, and an intuitive,
model-free overview, and are ideal for **segmentation, screening, and separating
states**; explicit multi-exponential fitting still wins when you need the actual
amplitudes and lifetimes of resolved components in a single pixel. In practice the
two are complementary — use the phasor plot to find and separate populations, then
fit the pixels that matter.

## See also

- Guide: {doc}`/guides/24_scan_images` — building CLSM images from a TTTR stream and
  computing per-pixel intensity, lifetime, MLE, and phasor maps.
- Phasor math: the two moments are computed by the photon library
  (`tttrlib.DecayPhasor` for a decay histogram or a micro-time selection,
  `tttrlib.StreamingPhasor` for a live stream, `CLSMImage.get_phasor` per
  pixel), and reached through
  {src}`chisurf/core/fluorescence/imaging/pixel_maps.py#phasor_maps`. IRF
  calibration is `DecayPhasor.g`/`DecayPhasor.s`; the apparent lifetimes,
  cursors and unmixing built on top of $(g, s)$ live in
  {src}`chisurf/plugins/microscopy/img_pixel_phasor/analysis.py`.
- Imaging plugins: `chisurf/plugins/microscopy/img_pixel_phasor/` (per-pixel
  $g,s$ maps, universal-circle ROI, apparent lifetime, cursor masks, unmixing),
  `img_pixel_micro_time/`, and `img_pixel_mle/` for per-pixel fitting; CLSM
  reconstruction via `tttrlib.CLSMImage`.
- Key literature: {cite}`digman2008` is the phasor approach to FLIM itself;
  {cite}`colyer2012` the polar plot as the visual basis of it;
  {cite}`malacrida2021` a review of the universal circle and how to read a
  phasor plot without fitting. For the origins: {cite}`lakowicz1992b` is the
  method paper for lifetime imaging, and {cite}`lakowicz1992` the measurement
  that made it worth doing — free and protein-bound NADH separated by lifetime
  alone, which is still the basis of label-free metabolic imaging.
  {cite}`verveer2000` is the global alternative to per-pixel fitting: hold one
  lifetime pair fixed across the whole stack and fit only the fraction per pixel,
  which is what makes a two-state FRET map tractable at realistic photon counts.
  For the frequency-domain roots: {cite}`jameson1984` is the review of phase and
  modulation lifetimes and why they differ for mixtures, {cite}`weber1981` the
  two-component resolution from them, and {cite}`redford2005` the polar plot with
  its instrument correction. {cite}`clayton2004` resolves two unknown lifetimes
  from the chord of a pixel cloud; {cite}`stefl2011` applies phasors to cuvette
  data, including reference calibration; {cite}`ranjit2018` is the working
  protocol; {cite}`vallmitjana2020` uses higher harmonics to resolve more
  components per pixel.
- Guide: {doc}`/guides/77_phasor_calculator` — the Phasor-Calculator, with the
  headless equivalents of every overlay.
- Tools in ChiSurf: the **Phasor-Calculator** (`chisurf/plugins/calculator/phasor_calculator/`) for the universal circle and the FRET trajectory; **Pixel Phasor** (`chisurf/plugins/microscopy/img_pixel_phasor/`), **Mean Micro-Time** (`chisurf/plugins/microscopy/img_pixel_micro_time/`) and **Pixel-wise MLE** (`chisurf/plugins/microscopy/img_pixel_mle/`) for the maps themselves.
