---
type: Concept
title: Super-resolution and localization microscopy
description: How the diffraction limit is circumvented, what sets localization precision, and why a resolution claim needs labelling density as well as precision.
tags: [concepts, resolution, localization, imaging, palm, storm, sted]
anchor: concept-super-resolution
---

(concept-super-resolution)=
# Super-resolution and localization microscopy

A fluorescence microscope cannot resolve two emitters closer than roughly half
the wavelength of the light it collects — about 200 nm for visible excitation
{cite}`abbe1873`. The limit is a property of the optics, not of the sample, and
no amount of magnification or exposure removes it.

Every method on this page evades that limit rather than repealing it, and they
all do so the same way: **make the emitters distinguishable in something other
than position**, then read position out one distinguishable group at a time.
What differs is the property used and whether the experimenter chooses it.

This page explains what the methods produce, so the analyses ChiSurf runs on
localization data — {ref}`concept-frc-resolution`,
{ref}`concept-drift-correction`, {ref}`concept-density-clustering`,
{ref}`concept-colocalization` — can be read against the measurement that made
them. ChiSurf analyses this data; it does not drive the microscope.

## Two families, and what each spends

**Targeted switching** decides *where* molecules may emit. In **STED** a second,
red-shifted doughnut beam drives molecules at the periphery of the excitation
spot back to the ground state by stimulated emission, so only those at the zero
of the doughnut still fluoresce {cite}`hell1994`. The effective spot shrinks
with depletion intensity roughly as $(1 + I/I_{\mathrm{sat}})^{-1/2}$, so
resolution is bought with laser power and has no hard floor
{cite}`klar1999,klar2000`. **Structured illumination** instead patterns the
excitation and uses the resulting moiré to shift high spatial frequencies into
the passband, recovering roughly a factor of two without switching anything
{cite}`gustafsson2000`.

**Stochastic switching** decides *how many* molecules emit, without choosing
which. Almost all fluorophores are dark at any instant; a sparse random subset is
on, each is imaged as an isolated spot, localized, and switched off. Repeat
$10^4$–$10^5$ times and the accumulated coordinates form the image. **PALM**
does this with photoactivatable proteins {cite}`betzig2006`, **STORM** with
switchable organic dyes {cite}`rust2006,bates2007`, and **PAINT** avoids
switching entirely by letting labels bind transiently from solution, so a
"blink" is a binding event {cite}`sharonov2006`. **DNA-PAINT** makes that
binding a designed DNA duplex, which turns the blink rate into a parameter you
set rather than a property of the dye {cite}`jungmann2014`. The idea predates
the chemistry by a decade {cite}`betzig1995`.

**MINFLUX** sits between the two: it localizes single molecules, like the
stochastic family, but probes each with a beam whose *zero* is scanned nearby,
so the informative measurement is the absence of photons {cite}`balzarotti2017`.
That inverts the usual economics — precision comes from few photons rather than
many.

The trade is consistent. Targeted methods image fast and need no reconstruction,
so they can follow dynamics {cite}`westphal2008`; stochastic methods reach finer
precision but must accumulate many frames, so a structure that moves during the
acquisition is blurred rather than resolved. {cite}`huang2009` is the review that
sets these against each other.

## What sets localization precision

Localizing an isolated spot is not limited by its width but by how well its
centre is determined. For $N$ detected photons from a spot of standard deviation
$s$, with pixel size $a$ and background $b$ per pixel, the uncertainty is
approximately

$$
\sigma^2 \;\approx\; \frac{s^2 + a^2/12}{N} \;+\; \frac{8\pi s^4 b^2}{a^2 N^2},
$$

with the first term the photon-counting limit and the second the background
penalty {cite}`thompson2002`. Three things follow, and all three are practical:

- **Precision improves only as $1/\sqrt{N}$.** Ten times better needs a hundred
  times the photons, which is why the photon budget of the label
  ({ref}`fundamentals-fluorophores`) sets what any of this can achieve.
- **Background enters quadratically at low $N$.** A dim emitter on a bright
  background is not slightly worse, it is disproportionately worse — which is
  what TIRF and light-sheet illumination exist to fix.
- **Pixel size is a genuine optimum, not "smaller is better".** Too large adds
  the $a^2/12$ pixelation term; too small spreads the same photons over more
  pixels, so each carries more read noise relative to signal.

Fitting the spot by maximum likelihood against the correct noise model, rather
than by a centroid or a least-squares Gaussian, reaches the Cramér–Rao bound —
the best any unbiased estimator can do with that data
{cite}`mortensen2010`. This is the same argument that makes maximum likelihood
the right estimator for photon-counting data generally
({ref}`fundamentals-photon-statistics`).

## Precision is not resolution

A localization precision of 10 nm does not give a 10 nm image, and treating the
two as the same is the most common error in this field.

Resolving two structures also requires *finding* both, which means enough
labelled molecules to sample them. The Nyquist argument is the usual statement:
to claim a resolution $d$, the mean distance between localized labels must be
below about $d/2$. Sparse labelling produces an image of beautifully precise
points that resolves nothing, because the gaps are unsampled rather than empty.

Three further effects break the identification, and none of them is visible in
the precision number:

- **Linkage error.** The localization reports the *dye*, not the target. A
  primary–secondary antibody pair displaces it by 10–20 nm, comparable to the
  precision being claimed.
- **Overcounting.** One molecule that blinks repeatedly appears as a cluster of
  localizations. This is indistinguishable from a real cluster on inspection and
  is why {ref}`concept-density-clustering` results from this data need a
  blinking-aware control, not just a distance threshold.
- **Drift.** Stage drift over a long acquisition smears every structure
  identically, and is corrected rather than avoided
  ({ref}`concept-drift-correction`).

Because of all this, the honest resolution of a reconstructed image is measured
from the image itself rather than computed from the optics — which is what
Fourier ring correlation does, and why {ref}`concept-frc-resolution` is the
number to quote.

## Where this connects in ChiSurf

The output of any of these methods is a coordinate table, and that is where
ChiSurf's analyses begin:

| Question | Page |
|---|---|
| What did this image actually resolve? | {ref}`concept-frc-resolution` |
| Did the stage move during acquisition? | {ref}`concept-drift-correction` |
| Are these localizations clustered, or is that blinking? | {ref}`concept-density-clustering` |
| Do two channels colocalize? | {ref}`concept-colocalization` |
| How large and how shaped are the objects? | {ref}`concept-region-properties` |
| How did a single particle move? | {ref}`concept-particle-tracking` |

For choosing acquisition parameters before measuring, the same
photons-versus-time reasoning appears in {ref}`concept-scan-precision`.

## References

- {cite}`abbe1873` — the diffraction limit.
- {cite}`hell1994` and {cite}`klar1999,klar2000` — STED, proposed and then
  demonstrated.
- {cite}`gustafsson2000` — structured illumination.
- {cite}`betzig1995` — the localization idea, before the chemistry existed.
- {cite}`betzig2006` and {cite}`rust2006,bates2007` — PALM and STORM.
- {cite}`sharonov2006` and {cite}`jungmann2014` — PAINT and DNA-PAINT.
- {cite}`balzarotti2017` — MINFLUX.
- {cite}`thompson2002` and {cite}`mortensen2010` — localization precision, and
  the bound on it.
- {cite}`huang2009` — the comparative review; {cite}`westphal2008` for the speed
  argument.

## See also

- Fundamentals: {ref}`fundamentals-fluorophores` (photon budget and switching) ·
  {ref}`fundamentals-photon-statistics` (why maximum likelihood) ·
  {ref}`fundamentals-instrumentation` (detectors and background).
- Concepts: {ref}`concept-frc-resolution` · {ref}`concept-drift-correction` ·
  {ref}`concept-density-clustering` · {ref}`concept-colocalization` ·
  {ref}`concept-particle-tracking` · {ref}`concept-region-properties`.
