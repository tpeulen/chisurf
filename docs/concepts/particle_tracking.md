---
type: Concept
title: Single-particle tracking
description: 'Following individual particles through a movie measures transport directly: not an ensemble average over a focal volume, but the actual path each particle took.'
tags: [concepts, particle, tracking]
anchor: concept-particle-tracking
---

(concept-particle-tracking)=

# Single-particle tracking

Following individual particles through a movie measures transport directly: not
an ensemble average over a focal volume, but the actual path each particle took.
That is what makes it able to distinguish a population with two mobilities from
one with an intermediate mobility — something no correlation measurement can do
from the decay shape alone.

It is also the analysis with the most ways to be quietly wrong, because a single
mis-linked pair invents a displacement that never happened, and the resulting
diffusion coefficient looks perfectly reasonable.

The matching guide is {doc}`/guides/50_particle_tracking`.

## Three stages, three failure modes

| stage | question | how it fails |
| --- | --- | --- |
| **detect** | where are the particles in this frame? | noise admitted as particles; real particles missed |
| **link** | which one in frame *t+1* is which in frame *t*? | identity swaps, invented displacements |
| **analyse** | what does the trajectory say about transport? | biased fits, error bars that mean nothing |

Keeping them separate is deliberate: each is diagnosable on its own, and a
problem in one is invisible in the output of the next.

## Detection

A diffraction-limited particle is a Gaussian spot several pixels wide. Two facts
follow, and between them they define the detector:

* **A spot is not one pixel.** A dead or hot camera pixel is exactly one, so
  requiring a minimum connected *area* separates them.
* **The position is the centroid, not the brightest pixel.** Intensity-weighted
  centroids localise to a fraction of a pixel, which is what makes sub-pixel
  tracking possible at all — pixel-accurate positions would swamp the
  displacements of any slow particle with quantisation noise.

### Why a wavelet, and why two scales

Thresholding raw intensity requires a flat background and bright spots. The
**à trous** (with holes) wavelet transform smooths the image at successive dyadic
scales without decimating it; the difference of two consecutive smoothings is a
band-pass plane that keeps structures of about one size and discards the slowly
varying background — with no intensity threshold chosen anywhere.

One plane is not enough, and the reason is a genuine trap: **the transform
spreads a single-pixel spike over several pixels**, so a minimum-area rule
applied to one plane sees a legitimate multi-pixel region and admits the hot
pixel it was meant to reject.

The **multiscale product** — the geometric mean of two adjacent planes — fixes
it. A real spot is significant at both scales; a one-pixel spike is strong only
at the finest and is annihilated by the coarser factor. It also almost removes
the dependence of false positives on field size. Measured on simulated frames
with 8 planted particles, detections per frame:

| threshold | 128² | 256² | 512² |
| --- | --- | --- | --- |
| 3σ, one plane | 9.8 | 33.9 | 131.2 |
| 3σ, product | 8.0 | 8.4 | 9.6 |
| 5σ, product | 8.0 | 8.0 | 8.0 |

The single-plane row is the point: the number of noise pixels surviving *k*
sigma is the pixel count times the tail probability, so a threshold that looks
clean on a small frame floods a large one.

## Linking

### An assignment, not a nearest neighbour

The obvious algorithm — for each particle take the nearest detection in the next
frame — breaks whenever two particles approach each other: both can claim the
same neighbour, and which one gets it depends on iteration order.

Framing it as a **global assignment** and solving it exactly (the Hungarian
algorithm) minimises the *total* squared displacement instead. Under isotropic
Brownian motion that is the maximum-likelihood pairing, and it does not depend
on the order anything is visited in.

### The maximum linking distance is the entire safety margin

It is what stops a particle that blinked out being linked to an unrelated one
across the field. Set it from the physics — a Brownian particle moves about
$\sqrt{4 D \Delta t}$ between frames — and never from what makes the tracks look
longest.

### Crowding, not the algorithm, is the limit

This is worth stating plainly because it is where tracking studies go wrong.
When two particles are within the linking distance of each other, the assignment
is **genuinely ambiguous**: no algorithm can resolve it from positions alone.

In simulations where 10 % of particles had a neighbour inside the linking
distance, up to a quarter of the recovered tracks merged two different particles,
and the fitted $D$ scattered over a factor of two. On a sparse field the same
code recovers identity *exactly*. It bites earlier than one would guess: at only
**4 %** crowded, eight tracks already merged and $D$ moved by ~20 %. The remedy is experimental, not computational:
label more sparsely, or image faster so the linking distance shrinks.

### Gap closing

Particles blink, defocus and are missed. Frame-to-frame linking alone therefore
shatters one trajectory into several, and short tracks are **biased** (see
below). A second pass reconnects a track that ended to one that started a few
frames later, with the search radius grown as $\sqrt{\text{gap}}$ because that is
how far diffusion carries a particle meanwhile.

Every closed gap asserts that no other particle could have been there. Keep the
allowed gap small and check what changing it does to the answer.

## Transport from the mean squared displacement

For a track sampled at frames, the time-averaged MSD at lag $n$ is the mean of
$|r(i+n) - r(i)|^2$ over all $i$. In two dimensions,

$$
\mathrm{MSD}(\tau) = 4 D \tau^{\alpha} + 4 \sigma^2 ,
$$

with $\alpha = 1$ for normal diffusion, $< 1$ for subdiffusion (crowding,
transient binding, confinement) and $> 1$ for directed transport.

Four things about fitting it are not optional.

**The offset is part of the model.** $\sigma$ is the localisation uncertainty and
adds a *constant* to every lag. Omit it and that constant is absorbed into $D$,
inflating it — badly for slow particles, where the offset is a large fraction of
the whole curve. Fitting it also measures the localisation precision for free.

**Long lags are nearly useless.** The MSD at lag $n$ of a track of length $N$
averages only $N-n$ displacements, and those *overlap*, so the points are few and
strongly correlated. Fitting the whole curve lets the noisy tail dominate; a
quarter of the lags is the usual compromise.

**Short tracks are biased, not merely noisy.** A particle is likelier to be
detected twice in a row if it happened to stay put, so the shortest tracks
over-represent the slowest motion. A minimum track length is a bias correction,
not a tidiness rule.

**$D$ and $\alpha$ are nearly degenerate.** A fit too high in one is too low in
the other and the curve still passes through the points. Fitting both roughly
quadruples the spread of $D$ — measured over 20 simulations, the standard
deviation of $D/D_\text{true}$ rose from 0.15 to 0.57. Fit $\alpha$ only when the
question genuinely is whether the motion is anomalous, and then read its error
bar before concluding anything.

### The error bar has to come from resampling

This deserves its own note because the natural choice is wrong. A least-squares
fit reports a covariance matrix, and it assumes **independent residuals**. MSD
points at different lags are built from overlapping displacements of the same
trajectories and are strongly correlated, so that assumption fails badly.

Measured against simulations with a known $D$, the covariance error bar covered
the truth in **4 runs out of 20** — it should be about 19. An error bar that
wrong is worse than none, because it invites confidence the data do not support.

Resampling **whole tracks** with replacement captures both the track-to-track
spread and the within-track correlation, since a track moves as a unit. That
gives 20 out of 20.

## What this cannot tell you

* **Drift is indistinguishable from directed motion.** Correct it first
  ({doc}`drift_correction`); no amount of tracking separates them afterwards.
* **A single $D$ from a heterogeneous sample is a weighted average** of whatever
  populations are present, and the weighting depends on track lengths. Look at
  the distribution of per-track $D$ before quoting one number.
* **Blinking that outlasts the gap tolerance** splits a trajectory in two, which
  biases the length distribution and therefore $D$.

## See also

- Tools in ChiSurf: **Particle Tracking** (`chisurf/plugins/microscopy/img_tracking/`) detects, links and fits the MSD, and writes the trajectories out per track.

## References

- {cite}`crocker1996` — the centroid localisation and linking that every tracker still starts from.
- {cite}`olivomarin2002` — the multiscale-product spot detector used to find particles before linking.
- {cite}`jaqaman2008` — linking as a global assignment problem, which is what survives dense fields.
- {cite}`michalet2010` — how localisation error and finite track length bias an MSD-derived D.
- {cite}`chenouard2014` — the community benchmark, and the source of the "density, not algorithm, is the limit" conclusion.

## Runnable examples

* `examples/notebooks/Particle_Tracking_Simulation_And_Recovery.ipynb` (with its
  `.py` cell-script twin, which also runs as a plain script) — the full loop on
  data whose answer is known: simulate a movie of Brownian particles, detect
  them, link them, check the recovered *identities* against the truth, and fit
  `D` with a bootstrapped error bar. It also shows how little crowding it takes
  to start merging tracks, and what fitting `alpha` costs.
