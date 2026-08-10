---
type: Concept
title: Deconvolution
description: 'Undoing the blur a microscope adds: the point spread function, why inverting it is not a division, and why the iteration count is the regularisation rather than a convergence knob.'
tags: [concepts, imaging, deconvolution, psf, restoration]
anchor: concept-deconvolution
---

(concept-deconvolution)=

# Deconvolution

A microscope does not record the sample. It records the sample convolved with
the instrument's **point spread function** — the image a single point source
produces — plus noise:

$$
g = f \ast h + n
$$

where $f$ is the object, $h$ the PSF, $g$ what the detector wrote down. The PSF
is a low-pass filter: it passes coarse structure and attenuates fine structure,
until above the diffraction cut-off it passes nothing at all.

Deconvolution estimates $f$ from $g$ and $h$. It is worth being precise about
what it can and cannot do. It **restores contrast** at spatial frequencies the
PSF attenuated but did not erase — which is most of the useful band, and the
reason a deconvolved confocal stack looks so much better. It does **not**
recover frequencies above the cut-off, where the PSF transmitted exactly zero;
no amount of arithmetic recovers information that was never recorded.

## Why it is not a division

In Fourier space the convolution is a product, so the obvious inverse is
$F = G / H$. That fails, and it fails badly: where $H$ is small, $G$ there is
almost entirely noise, and dividing by a small number amplifies it without
bound. The result is not a sharper image but a field of high-frequency garbage.

Every practical method is therefore some way of *declining* to divide where the
data does not support it. They differ in what they assume the noise is.

## Richardson–Lucy: the Poisson answer

{cite}`richardson1972` and {cite}`lucy1974` independently derived the same
fixed-point iteration, which is the maximum-likelihood estimate when the noise
is **Poisson**:

$$
f^{(k+1)} = f^{(k)} \cdot \left( \frac{g}{f^{(k)} \ast h} \star h \right)
$$

($\ast$ convolution, $\star$ correlation.) Read it as a feedback loop: blur the
current estimate, compare it with what was actually measured as a *ratio*, and
push that ratio back through the PSF to say where the estimate should go up or
down.

Two properties follow from the form and both matter for photon data:

* **The estimate stays non-negative.** Every factor is a ratio of non-negative
  quantities, so a count never comes out negative — which a linear filter
  cannot promise, and a negative photon count is not a small error but a
  meaningless one.
* **Flux is conserved.** The correlation is with a normalised kernel, so the
  total does not move; photons are redistributed, not created.

The noise model is the reason this is the default here rather than a linear
filter. A confocal or widefield fluorescence image at useful speed is
photon-limited, and Poisson is not an approximation to its noise — it *is* its
noise.

## The iteration count is the regularisation

Richardson–Lucy has no explicit regularisation term. What stops it fitting the
noise is that it is *stopped*. Early iterations recover the coarse structure the
PSF attenuated most gently; later ones reach for finer structure, and eventually
for structure that is not in the object at all.

Plotted against the truth on a simulated frame, the error traces a **U**:

| iterations | 5 | 20 | 100 | 400 |
|---|---:|---:|---:|---:|
| relative error | 0.24 | **0.10** | 0.21 | 0.41 |

Past the minimum the image keeps looking sharper while getting further from the
truth — noise consolidates into speckles that are indistinguishable, by eye,
from small objects. This is the single most important thing to know when using
it: **more iterations is not more converged, it is more confident about noise.**
Tens, not thousands, and the right number is a property of the data.

Acceleration {cite}`biggs1997` extrapolates along the direction the last two
iterations agreed on. It is a step-size change, not a better estimator: on the
same frame, 30 accelerated iterations land where 400 plain ones do. That reaches
the optimum in about 5 iterations instead of 20, but the coarser step can
overshoot what is a shallow minimum — so it is a good way to explore and a bad
way to settle the count.

## Where the PSF comes from

Deconvolving with the wrong PSF does not fail; it produces a confident wrong
answer. Too narrow leaves the image blurred, too wide rings around every object.
Three routes, in decreasing order of trust:

1. **Measured from beads.** Image sub-resolution fluorescent beads under the
   same optics and fit them. ChiSurf's **PSF determination** tool does this and
   reports $\sigma$ per axis; that number is the input to the kernel builder.
2. **Computed from the optics.** The Gaussian approximations of
   {cite}`zhang2007`:

   $$
   \sigma_{xy} \approx \frac{0.21\,\lambda}{\mathrm{NA}}, \qquad
   \sigma_{z} \approx \frac{0.66\,\lambda\,n}{\mathrm{NA}^{2}}
   $$

   Good to a few percent up to about NA 1.0 and progressively optimistic above
   it; at NA 1.4 the true PSF has structure a Gaussian cannot represent. Note
   the asymmetry — axial resolution is two to three times worse than lateral,
   which is why a deconvolved stack gains most in $z$.
3. **Guessed.** Only for a first look.

## Sampling, and what to check before deconvolving

* **Nyquist.** The PSF must be sampled by at least two pixels across its width,
  or the frequencies deconvolution works on were aliased before it started.
* **Background.** A constant offset is not part of the convolution model;
  subtract it first, or the iteration attributes it to the object.
* **Saturation and clipping.** A clipped pixel violates the likelihood the
  method maximises, and produces ringing that looks like structure.

## See also

- Tools in ChiSurf: **PSF determination** (`chisurf/plugins/microscopy/psf_determination/`)
  measures the PSF from beads; the deconvolution itself is
  `chisurf.core.fluorescence.imaging.restoration`, over the compiled engine in
  the photon library.
- {ref}`concept-density-clustering` and the region tools for what to do with a
  restored image.

## References

- {cite}`richardson1972`, {cite}`lucy1974` — the iteration.
- {cite}`biggs1997` — acceleration by vector extrapolation.
- {cite}`zhang2007` — the Gaussian PSF approximations and their accuracy.
