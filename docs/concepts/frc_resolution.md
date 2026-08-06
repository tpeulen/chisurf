---
type: Concept
title: 'Image resolution: what the photons actually resolved'
description: The resolution of a fluorescence image is not the pixel size, and it is not the diffraction limit either.
tags: [concepts, imaging, resolution]
anchor: concept-frc-resolution
---

(concept-frc-resolution)=
# Image resolution: what the photons actually resolved

The resolution of a fluorescence image is not the pixel size, and it is not the
diffraction limit either. Both are upper bounds on what the optics *could*
deliver; what a particular image *did* deliver also depends on how many photons
were collected, how bright the label was, how much the sample moved and how well
the focus held. Fourier ring correlation (FRC) measures that directly, from the
image itself, with no bead, no calibration slide and no model of the point-spread
function.

For the workflow, see {doc}`the FRC guide </guides/51_frc_resolution>`.

## The idea: reproducibility as a function of spatial frequency

Split one acquisition into two halves that are **statistically independent**
measurements of the same object — for instance the even and the odd frames.
Each half contains the same structure plus its own, independent, shot noise.
Take the Fourier transform of both and correlate them over rings of constant
spatial frequency $q$:

$$\mathrm{FRC}(q) = \frac{\sum_{|\mathbf{q}| \in q} F_1(\mathbf{q})\,
F_2^{*}(\mathbf{q})}{\sqrt{\sum_{|\mathbf{q}| \in q} |F_1(\mathbf{q})|^2
\sum_{|\mathbf{q}| \in q} |F_2(\mathbf{q})|^2}}.$$

At low frequency the coarse structure dominates both halves, they agree, and the
FRC is close to 1. At high frequency each half is mostly its own noise, the two
are uncorrelated, and the FRC falls to 0. The transition is not an artefact of
the analysis: it is the frequency at which the *signal* stops standing out of the
*noise*.

The resolution is the inverse of the frequency $q_c$ where the curve falls
through a threshold,

$$d = 1/q_c,$$

which is why the pixel size enters only as a scale factor — get it wrong by 10 %
and the resolution is wrong by 10 %.

## The split is the measurement

Everything rests on the two halves being independent measurements of the *same*
object. Two failure modes, both of which produce a confident number:

* **Not independent.** Correlating an image with itself gives 1 at every
  frequency — no crossing, and a naive implementation that then reports the last
  frequency would claim single-pixel resolution. Correlating it with a smoothed
  copy of itself measures the smoothing kernel.
* **Not the same object.** Two spectrally distinct labels on different
  structures correlate nowhere. Under the fixed 1/7 criterion the crossing then
  lands in the first few rings — a "resolution" of the order of the field of
  view; under the count-dependent criteria, whose thresholds start at 1, the
  curve never rises above its threshold at all and the answer is *no crossing*.
  A crossing is only ever reported where the curve was above its threshold and
  falls through it, so neither case can produce a number finer than the data.

The usual split, even/odd frames, is robust to slow drift because both halves
span the whole acquisition. Splitting into the first and the second half instead
is right when consecutive frames are *not* independent, and it has the useful
side effect of exposing bleaching: if the second half is much dimmer, the two
halves are no longer equivalent measurements.

## Which threshold?

The curve decays smoothly, so "where it falls to zero" is not a number. Three
conventions are in use, and they disagree:

**Fixed 1/7** ({cite}`nieuwenhuizen2013`). A constant threshold of $1/7 \approx
0.143$. It is the usual choice for fluorescence images, and the only one of the
three that does not depend on how the rings were binned or how large the image
is.

**½-bit** ({cite}`vanheel2005`). The frequency at which the accumulated
information suffices to interpret the structure:

$$T(q) = \frac{0.2071 + 1.9102/\sqrt{n_q}}{1.2071 + 0.9102/\sqrt{n_q}},$$

with $n_q$ the number of Fourier pixels in the ring. It starts at 1 on the
innermost rings and tends to 0.172 as the rings fill.

**2σ.** Twice the correlation expected from pure noise, $2/\sqrt{n_q/2}$. It
falls without limit as the rings fill, so it sits *above* the fixed 1/7 for
small images and below it for large ones — it crosses at $n_q \approx 392$
Fourier pixels per ring. Neither of the count-dependent criteria is uniformly
stricter than the other: where they sit depends on the image.

Because they differ by tens of per cent on the same data, **a resolution without
its criterion is not a result.** Quote both.

```{figure} figures/frc_thresholds.png
:name: fig-frc-thresholds
:width: 100%

**One curve, three criteria, three answers.** An FRC curve against the fixed 1/7 threshold, the ½-bit criterion and the $2\sigma$ criterion, each marked where the curve *falls through* it — 8, 11 and 10 nm on the same data. The count-dependent criteria start above 1 on the innermost rings, which is why a crossing counts only after the curve has been above the threshold; without that rule they both 'cross' in the first ring and report the field of view.
```

## What the number does and does not mean

* It is a property of *this acquisition*, not of the microscope. More frames, a
  brighter label or a longer dwell time all improve it; drift, bleaching and
  background all degrade it.
* Correcting drift before measuring matters ({ref}`concept-drift-correction`):
  drift blurs the summed image, and the FRC will faithfully report the blur.
* **No crossing is an answer.** Either the halves agree at every frequency the
  sampling can show — the image is oversampled relative to its resolution, and
  finer pixels would be needed to see the limit — or they agree nowhere, which
  means too few photons or a split that was not independent.
* The estimate is itself noisy near the crossing, where the curve is flat;
  treat the last digit as decoration. Smoothing the curve over a few rings
  before reading the crossing is standard and is what the tool does.

## See also

- Guide: {doc}`/guides/51_frc_resolution` · drift first:
  {ref}`concept-drift-correction`.
- Implementation: the split into two independent halves
  {src}`chisurf/plugins/microscopy/img_frc/core.py#halves`, the ring correlation
  and criteria {src}`chisurf/plugins/microscopy/img_frc/api/frc.py#compute_resolution`
  and {src}`chisurf/plugins/microscopy/img_frc/api/frc.py#list_criteria`.
- Tools in ChiSurf: **FRC Resolution** (`chisurf/plugins/microscopy/img_frc/`) splits the acquisition and reports the crossing under each criterion.

## References

- {cite}`vanheel2005` — the correlation-shell criteria themselves: where the
  ½-bit and the σ-based thresholds come from, and what each assumes.
- {cite}`banterle2013` — the FRC criterion argued specifically for
  super-resolution fluorescence images.
- {cite}`nieuwenhuizen2013` — FRC as the practical resolution measure for
  localisation microscopy, and the fixed 1/7 convention used here.
