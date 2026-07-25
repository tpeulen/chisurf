# Drift correction

Stage drift moves the sample between frames. This tool measures that movement
and removes it, for both camera stacks and photon-stream (confocal) images.

It sits in the **Image Tools** toolbox between *Browser* and *1. Intensity*,
because every per-pixel map in the numbered pipeline is built from frames that
must already be aligned. Correct here first, then continue with **Next ▶**.

## Why it matters more than it looks

For a plain intensity image, drift is a cosmetic blur in the summed projection.
For anything that correlates frames it is a **systematic error**, because a
translation between two frames is indistinguishable from the decorrelation that
diffusion produces. Leave it in and a diffusion fit over frame lags — STICS,
TICS, iMSD — absorbs it by reporting a larger diffusion coefficient.

The number to look at is the **maximum drift** in the status line:

* **below one pixel** — the correction changes nothing; leave it off;
* **a few pixels** — worth correcting before any frame-lag analysis;
* **beyond the beam waist** — any frame-lag result from the raw data was
  compromised, not merely noisy.

## How the measurement works

Each frame is cross-correlated with a reference frame by FFT, and the position
of the correlation peak is the displacement. The correlation is blurred
slightly before the peak is located, so that a noise-driven tie between two
neighbouring pixels cannot flip the answer by a whole pixel.

It assumes **pure translation** — no rotation, no scaling, no deformation. A
sample that rotates or a cell that changes shape will not be corrected by this,
and the drift trace will look erratic rather than smooth.

**Reference**

* **First frame** — every frame compared with frame 0. Right for slow monotonic
  stage drift, and error never accumulates.
* **Previous frame** — consecutive frames compared and the shifts accumulated.
  Follows non-monotonic wander, but small per-frame errors add up over a long
  series.
* **Stack mean** — compared against the average of all frames; a compromise for
  noisy data with no single good reference.

**Measure on** picks the channel that drives the estimate. The sample moves as a
whole, so one channel is measured and the correction is applied to all of them.
Choose the brightest, most structured channel — a flat or empty channel gives a
soft peak and an unreliable shift.

## How the correction is applied

**Wrapping** rolls the content that leaves one edge back in at the other. No
signal is lost, which is why it is the reference behaviour, but the wrapped
strip at the edge is meaningless — do not analyse it.

**Blanking** discards what moves out of frame and leaves the vacated strip
empty. Honest about the missing data, at the cost of edges that carry no
signal.

Either way the correction is applied in **whole pixels**. Sub-pixel refinement
sharpens the *measurement* (useful for reading off a slow drift rate) but the
image itself is only ever moved by integers, since moving photons between
pixels cannot be fractional.

## Photon streams are corrected photon by photon

This is the part that distinguishes a confocal image from a camera stack. A
photon-stream image is not an array of intensities — each pixel holds a list of
photons, with their arrival times and micro-times. Correcting it therefore
**moves photons between pixels** rather than resampling numbers.

That matters because the corrected image is still a real photon image: lifetime
fits, decay extraction and correlation all remain valid afterwards. Shifting a
rendered intensity image would have thrown that information away.

## Outputs

* **Drift trace** — displacement per frame. A straight line is stage drift; a
  step is a bump or a refocus; noise about zero means there was nothing to
  correct.
* **Before / After projections** — all frames summed, either side of the
  correction. If it worked, features are visibly sharper on the right. If the
  two look the same, there was no drift.
* **Shifts table** — the per-frame numbers, exportable as CSV.
* **Export stack** — the corrected stack as a multi-page TIFF.
