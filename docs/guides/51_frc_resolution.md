---
type: Guide
title: 'Image resolution: measuring it from the image itself'
description: Measuring the resolution an acquisition actually achieved with Fourier ring correlation, and reading the resolution curve it produces.
tags: [guides, imaging, correlation]
---

# Image resolution: measuring it from the image itself

How fine a detail did this acquisition actually resolve? Fourier ring
correlation answers it from the data — no bead, no calibration slide, no model
of the point-spread function — for camera stacks and photon streams alike.

For why the method works and which threshold to quote, see
{ref}`concept-frc-resolution`.

## Open the tool

It lives in **Spectroscopy → Image Tools**, as the **Resolution** step after
*Drift*. That order is deliberate: drift blurs the summed image, and the FRC
faithfully reports the blur, so an uncorrected stack measures the stage rather
than the microscope. It is also available standalone as **Imaging → FRC
Resolution**, and you can drop a file onto the window.

It accepts

* **TIFF stacks** (and anything else the image reader handles), and
* **photon streams** — PTU, HT3, SPC — reconstructed into a confocal-scan image.

```{figure} figures/frc_workspace.png
:name: fig-frc-workspace
:width: 100%

The FRC workspace on a confocal photon stream. Left: the settings. Right: the
headline resolution, the FRC curve against the 1/7 threshold with the crossing
marked, and — behind the *Diagnostics* tabs — the two independent halves the
curve came from and the ring-by-ring numbers.
```

## Measure

1. **Image** — browse, pick a database entry, or drop a file.
2. **Split into halves by** — the choice the whole method rests on:
   * *Even / odd frames* — the default. Both halves span the whole acquisition,
     so slow drift affects them equally.
   * *First / second half* — for detectors whose consecutive frames are not
     independent. It also exposes bleaching: a much dimmer second half means the
     two halves are no longer equivalent measurements.
   * *Two channels* — two detectors that saw the *same* structure. This is the
     split to use when the image has only one frame.
   * *Two files* — two repeated acquisitions of the same field of view.
3. **Channel** — the one to measure. Pick the brightest, most structured one; a
   flat channel has no fine detail to correlate.
4. **Pixel size** — in nm, which turns the answer from pixels into nanometres.
   It scales the result linearly.
5. **Criterion** — *Fixed 1/7* unless you have a reason; see below.
6. Press **▶ Measure**.

Under *Estimator* sit three things you will rarely touch: the **ring width**
(zero means one Fourier pixel, the finest the sampling supports), the
**smoothing** applied before the crossing is read, and the **TIFF axis order**.

The last one has a real trap behind it. A plain TIFF stack carries no metadata
saying what its pages are, and four or fewer of them look far more like a
two/three-colour image than like a time series — so a four-frame acquisition
arrives as one frame with four channels, and a frame split then has nothing to
split. If a short stack reports one frame, set **TIFF axis order** to *All
planes are frames*. A stack written by ChiSurf with labelled axes (`TYX`) says
so in the file and needs no override, and photon streams are unaffected: their
frames and detector channels are declared in the file.

## Read the result

The headline is the resolution and **the criterion it was read against**. Quote
both: the three conventions disagree by tens of per cent on the same data, and
2σ is not uniformly more permissive than 1/7 — where it sits depends on how many
Fourier pixels each ring holds.

The **curve** is the thing to look at before believing the number:

* A clean sigmoid from 1 down into noise is a good measurement.
* A curve that starts *below* 1 means the two halves already disagree at coarse
  frequencies — usually a split that is not measuring the same object.
* A curve that never falls through the threshold reports **no crossing**. That
  is an answer, not an error: either the image is oversampled relative to its
  resolution, or the halves are not independent (the same file twice, for
  instance).
* A crossing in the first few rings means nothing was resolved — too few
  photons, or two channels showing different structures.

The **Halves** tab is the fastest check that the split did what you meant: both
images should show the same structure, each noisier than the summed image.
**Rings** lists the curve numerically, including how many Fourier pixels each
ring holds — the quantity the ½-bit and 2σ thresholds depend on. **💾 Export
CSV** writes all of it for a methods section.

## Headless

```bash
img-frc image.tif --pixel-size 65 --criterion fixed_1/7
img-frc scan.ptu --channel ch0 --pixel-size 80 --split even_odd --json
img-frc short_stack.tif --axis-order frames --out-csv frc.csv
```

It prints the crossing and the resolution, and exits non-zero when the curve
never crosses — so a batch script cannot mistake "nothing resolved" for a
measurement. `--json` emits the whole curve, the threshold and the ring counts
for a script to consume.

The same three calls are available over RPC as `img_frc.resolution.compute`,
`img_frc.criteria.list` and `img_frc.contract.describe`, which is what the GUI
itself uses.

## Using it well

**Measure it on the data you will publish.** The resolution is a property of the
acquisition, so it changes with the frame count, the label and the dwell time.
Measuring it once on a bright test sample says nothing about the dim one.

**Correct drift first.** See {doc}`43_drift_correction`.

**Do not chase the last digit.** Near the crossing the curve is flat, so the
estimate wanders by a ring or two; a difference of a few per cent between two
images is not a difference.

## See also

- Tool: **FRC Resolution** (`chisurf/plugins/microscopy/img_frc/`).
