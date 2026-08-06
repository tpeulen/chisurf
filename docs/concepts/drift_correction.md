(concept-drift-correction)=
# Drift correction

Over the minutes a stack takes to record, the sample moves. Thermal expansion in
the stage, a slowly relaxing mount, a drifting objective — the mechanism varies,
the effect does not: frame $k$ shows the same sample displaced by some
$(\delta y, \delta x)$ from frame 0.

For a single image this is invisible. For anything that compares frames it is a
**systematic error**, and this page is mostly about why.

For the workflow, see {doc}`the drift-correction guide </guides/43_drift_correction>`;
for the analysis it protects, {ref}`concept-image-correlation`.

## Why drift is not just blur

Sum a drifting stack and you get a smear. That much is obvious, and if all you
want is a picture, correcting it is cosmetic.

The problem is correlation. A correlation analysis asks *how much does the image
at time $t$ resemble the image at time $t + \tau$?*, and answers it with the
overlap between the two. Diffusion reduces that overlap because molecules move
independently. **Translation reduces it too** — and the correlation function
cannot tell the two apart.

Concretely, for a stack whose frames are identical except for a translation,
the frame-lag correlation at zero spatial lag falls off with $\Delta$:

| Frame lag $\Delta$ | $G(0,0,\Delta)$ uncorrected | corrected |
| --- | --- | --- |
| 0 | 1.291 | 1.291 |
| 1 | 1.190 | 1.285 |
| 2 | 0.983 | 1.284 |

Nothing in that sample is diffusing. The decay on the left is pure drift, and a
diffusion model fitted to it has only one way to reproduce a decay — report a
larger $D$. The correction restores the flat curve the physics demands.

The scale that matters is the **beam waist**, not the pixel. Drift comparable to
$w_r$ decorrelates a frame pair completely; drift well below one pixel does
nothing at all. Hence the rule of thumb:

* $< 1$ px total — ignore it;
* a few px — correct before any frame-lag analysis;
* $> w_r$ — the uncorrected frame-lag results were not merely noisy, they were
  measuring the stage.

## Measuring the shift

The estimator is cross-correlation. For a reference frame $a$ and a later frame
$b$,

$$
C(\xi, \psi) = \mathcal{F}^{-1}\bigl\{\, \mathcal{F}(a)\,\overline{\mathcal{F}(b)} \,\bigr\}
$$

peaks at the displacement between them, and the peak position *is* the shift.
Both frames have their mean removed first, so the flat background does not
dominate the peak.

Two practical details matter more than the formula.

**The correlation is smoothed before the peak is found.** With shot noise, two
neighbouring pixels of $C$ are often within noise of each other, and picking the
larger one is a coin flip that moves the answer by a whole pixel. A small
Gaussian ($\sigma \approx 2$ px) removes that coin flip. This is what the
reference implementation does, and it is worth keeping.

**The choice of reference is a bias/variance trade.**

| Reference | Behaviour |
| --- | --- |
| First frame | Every frame compared with frame 0. No error accumulation, but if the sample decorrelates (photobleaching, real dynamics) the late frames correlate poorly with the first. |
| Previous frame | Consecutive frames, shifts accumulated. Always well-correlated, so it follows non-monotonic wander — but each estimate's error adds into every later frame. |
| Stack mean | Compared against the average. A compromise when no single frame is a good template. |

For slow monotonic stage drift over a stable sample, *first frame* is right. For
a long series that bleaches, *previous frame* usually wins despite the drift of
its own.

The reference also fixes where the zero of the trace sits. With *first frame* or
*previous frame*, frame 0 **is** the reference, so its shift is zero by
construction and the trace starts at the origin. With *stack mean* the reference
is the average, which no single frame occupies: frame 0 is displaced from it like
any other, so its shift is measured too and the trace is centred on zero rather
than starting there. Only the differences between rows are physical in either
case — the same drift, read against a different origin.

## Applying it

The measured displacement is removed by moving each frame back. What happens at
the edges is a genuine choice:

**Wrapping** rolls what leaves one edge back in at the other. Every photon is
kept — the total intensity is conserved exactly — but the wrapped strip is
nonsense, showing the far side of the field. Analyse the interior only.

**Blanking** discards it and leaves the strip empty. Honest about the missing
data, at the cost of edges with no signal, which will bias any statistic that
averages over the whole frame.

Neither is free. Wrapping is the reference behaviour, and for correlation work
the wrapped strip contributes a small, roughly constant background rather than a
structured artefact.

The correction is applied in **whole pixels**. Sub-pixel refinement (fitting a
parabola through the correlation peak and its neighbours) sharpens the measured
*number*, which is what you want for reading off a drift rate, but the image is
still moved by integers.

## Photon streams are a different object

A camera stack is an array of intensities, so correcting it means resampling
numbers. A confocal image reconstructed from a photon stream is not: each pixel
holds a **list of photons**, each with its arrival time and micro-time.

Correcting such an image therefore means *moving photons between pixels*, not
shifting an intensity map. The distinction is not pedantic — it decides what you
can do afterwards. Correct at photon level and the result is still a photon
image: lifetimes, decays, and correlations all remain available. Shift a rendered
intensity image instead and every photon-level quantity has been discarded.

ChiSurf corrects photon streams the first way. A round-trip through a known
injected drift returns the original image bit-for-bit, with every photon
conserved.

## What it cannot do

The model is **pure translation**. No rotation, no scaling, no deformation.

A rotating sample, a cell that changes shape, or a field where different objects
move differently will not be corrected by this, and — importantly — the failure
is not silent if you look: the drift trace becomes erratic rather than smooth,
and the "after" projection is no sharper than the "before". Those two diagnostics
are the reason the tool shows them.

Two more failure modes worth knowing:

**A featureless channel gives a meaningless shift.** The correlation peak of a
near-uniform field is broad and noise-dominated. Measure on the brightest,
most structured channel and apply the result to the rest — the sample moves as a
whole, so there is nothing to gain from per-channel estimates and plenty of noise
to add.

**Bleaching is not drift, but it perturbs the estimate.** A stack that dims
monotonically has frames that differ in amplitude as well as position. Removing
each frame's mean (as the estimator does) handles the offset, not the change in
contrast; with severe bleaching, prefer *previous frame* referencing, where
consecutive frames are most similar in brightness.

## See also

- Tools in ChiSurf: **Drift Correction** (`chisurf/plugins/microscopy/img_drift/`) measures the shift and applies it — to the frames of a stack, or to the coordinates of a photon stream.
