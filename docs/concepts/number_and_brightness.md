---
type: Concept
title: 'Number & Brightness: molecule number and oligomeric state from pixel fluctuations'
description: 'How the per-pixel mean and variance of an image stack separate how many molecules there are from how bright each one is — for photon-counting and analog detectors, across two channels, and what bleaching, immobile structure and dead time do to it.'
tags: [concepts, imaging, fluctuation, brightness, oligomerization]
anchor: concept-number-and-brightness
---

(concept-number-and-brightness)=
# Number & Brightness: molecule number and oligomeric state from pixel fluctuations

An intensity image cannot tell ten molecules of brightness 1 from five of
brightness 2. Their **fluctuations** can. Number & Brightness (N&B)
{cite}`digman2008b` records the same field many times and, pixel by pixel, reads
the molecule number and the brightness per molecule from the mean and the
variance of the counts over the frames. Because a dimer is twice as bright as its
monomer, the brightness map is a map of oligomeric state. For the workflow in
ChiSurf see the {doc}`guide </guides/67_number_and_brightness>`.

## Moments of a fluctuating pixel

Let a pixel hold $n$ molecules in a frame, with $n$ Poisson-distributed around
$\langle n\rangle$ as molecules diffuse in and out between frames, and let each
molecule contribute on average $\varepsilon$ counts during the pixel dwell. The
recorded counts $k$ are Poisson given $n$, so by the law of total variance

$$
\langle k\rangle = \varepsilon\langle n\rangle, \qquad
\sigma^2 = \underbrace{\varepsilon\langle n\rangle}_{\text{shot noise}}
         + \underbrace{\varepsilon^2\langle n\rangle}_{\text{number fluctuation}} .
$$

The **apparent** brightness and number are the ratios anyone can form,

$$
B = \frac{\sigma^2}{\langle k\rangle} = 1 + \varepsilon, \qquad
N = \frac{\langle k\rangle^2}{\sigma^2},
$$

and the **true** molecular brightness and number follow once the shot-noise
floor (the $1$) is removed:

$$
\varepsilon = \frac{B - 1}{\gamma}, \qquad
n = \frac{\gamma\,\langle k\rangle}{B - 1} .
$$

A pixel with nothing moving through it — an immobile structure, pure background —
has $B = 1$ and $\varepsilon = 0$ whatever its intensity. $\gamma$ is the shape
factor of the observation volume; with $\gamma = 1$ the numbers are those of
Digman et al., with $\gamma = 2^{-3/2} = 1/\sqrt{8}$ (3-D Gaussian) they are the
$\gamma$-corrected values some packages report.

The variance is the **unbiased** sample variance (divided by $K-1$ for $K$
frames). The population variance underestimates $\sigma^2$, and therefore $B$, by
$(K-1)/K$ — 2 % for 50 frames, enough to bias $\varepsilon$ of a dim species
visibly.

## Analog detectors

A detector that integrates current rather than counting photons reports
$k = S\cdot(\text{photons}) + k_0$ plus read noise of variance $\sigma_0^2$. With
$I = \langle k\rangle - k_0$ and $V = \sigma^2 - \sigma_0^2$ {cite}`dalal2008`,

$$
B = \frac{V}{I}, \qquad
\varepsilon = \frac{V - S I}{S I\,\gamma}, \qquad
n = \frac{\gamma I^2}{V - S I} .
$$

$S$ and $k_0$ are not guesses. Image a sample that does **not** fluctuate but
spans a range of intensities (a dye film under an illumination gradient): every
pixel then carries only detector noise, $\sigma^2 = S(\langle k\rangle - k_0) +
\sigma_0^2$, and a straight line through the $(\langle k\rangle, \sigma^2)$ cloud
gives the slope $S$ and, with $\sigma_0^2$ from a dark measurement, the offset.
Using the photon-counting formula on analog data inflates $\varepsilon$ by roughly
the gain.

## Cross N&B

Two detection channels $a$ and $b$ of the same field give the covariance
$C = \langle k_a k_b\rangle - \langle k_a\rangle\langle k_b\rangle$ and

$$
B_\text{cross} = \frac{C}{\sqrt{\langle k_a\rangle\langle k_b\rangle}}, \qquad
N_\text{cross} = \frac{\langle k_a\rangle\langle k_b\rangle}{C} .
$$

There is **no** $-1$: shot noise in one detector is independent of shot noise in
the other, so the cross term has no noise floor to remove. Uncorrelated species
give $B_\text{cross} \approx 0$; a species carrying both labels with brightnesses
$\varepsilon_a$, $\varepsilon_b$ gives $\sqrt{\varepsilon_a\varepsilon_b}$.
Copying the auto formula here biases every value by $-1$.

## Everything else that fluctuates

N&B attributes all excess variance to number fluctuations, so anything else that
changes the counts between frames masquerades as brightness.

**Photobleaching** makes $\langle n\rangle$ drift down through the stack; the
drift adds variance. *Segmented detrending* fits a straight line to every pixel
within each of several time segments, subtracts it, and adds the pixel's own mean
back. The mean restoration is not optional — the residuals have zero mean and
$B$ divides by the mean. Each fitted line also removes two degrees of freedom,
so the variance is divided by $K - 2\cdot\text{segments}$; with ten-frame segments,
ignoring that biases $B$ low by 20 %.

**Immobile structure and slow drifts** are removed by subtracting a pixel mean or a
sliding box average and adding a mean back. That is a different operation from
detrending: it removes structure shared across frames, not a trend in time.

**Dead time** loses counts in bright pixels, which compresses the variance more
than the mean. Counts are corrected as $k/(1 - k\,\tau/T)$ for a dead time $\tau$
and pixel dwell $T$ before the moments are taken.

**Smoothing** the mean and standard-deviation maps (box, disk or Gaussian) trades
resolution for precision. Smoothing $\sigma$ rather than $\sigma^2$ — what the
reference implementation does — slightly underestimates $\sigma^2$ where it
varies within the kernel.

## Gating a population

The readout of an N&B experiment is rarely a single number. Pixels are scattered
on a **parameter plane** — intensity against $B$ is the classic one — where
species of different brightness form separate clouds at the same intensity. A
region drawn round a cloud selects pixels, and those pixels, mapped back onto the
image, show *where* that oligomeric state is. Maps that were thresholded to NaN
(background, masked cells) are smoothed with weights restricted to valid pixels,
so the masked region does not bleed into the edge of the map.

## Reference implementation

The estimators, the dead-time correction, the moment filters (box, disk and
Gaussian with MATLAB-style kernels and mirrored borders), the median filter, the
cross channel, the counts histogram and the outlier-trimmed display ranges were
verified against the N&B of PAM {cite}`schrimpf2018` run under Octave, to
$10^{-10}$ relative; the fixture and its generator live in `test/data/nb/`.

## References

- {cite}`digman2008b` — the method: per-pixel $B$ and $N$, the $-1$, oligomer maps.
- {cite}`dalal2008` — analog detectors and the gradient calibration of $S$ and the offset.
- {cite}`schrimpf2018` — PAM, the reference implementation compared against.

## See also

- {ref}`concept-pch-fida` — the full photon-counting histogram, of which N&B uses the first two moments.
- {ref}`concept-image-correlation` — the spatial and temporal correlation of the same image stacks.
