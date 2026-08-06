---
type: Guide
title: Drift correction
description: Measure and remove inter-frame sample drift, in camera stacks and in photon-stream (confocal) images alike.
tags: [guides, corrections, photons]
---

# Drift correction

Measure and remove inter-frame sample drift, in camera stacks and in
photon-stream (confocal) images alike.

For why drift matters — and why it is a systematic error rather than a cosmetic
one — see {ref}`concept-drift-correction`.

## Open the tool

It lives in **Spectroscopy → Image Tools**, as the **Drift** step between
*Browser* and *1. Intensity* — deliberately, because every per-pixel map in the
numbered pipeline below it is built from frames that must already be aligned.
Correct the drift first, then walk the pipeline with **Next ▶**.

It is also available standalone as **Imaging → Drift Correction**. Either way you
can drop a file onto the window. It accepts

* **TIFF stacks** (and anything else the image reader handles), and
* **photon streams** — PTU, HT3, SPC — reconstructed into a confocal-scan image.

The two are corrected differently under the hood: a TIFF stack by shifting
intensities, a photon stream by moving photons between pixels. The second is
what keeps the corrected image usable for lifetime and correlation work
afterwards.

## Measure

1. **Image** — browse, pick a database entry, or drop a file.
2. **Measure on** — the channel that drives the estimate. Pick the brightest,
   most structured one. The sample moves as a whole, so this single estimate is
   applied to every channel.
3. **Reference** — *First frame* for slow monotonic stage drift; *Previous
   frame* for a long series that bleaches or wanders.
4. **Apply by** — *Wrapping* keeps all signal but makes the edge strip
   meaningless; *Blanking* drops what leaves the frame.
5. Press **▶ Measure**.

```{figure} figures/drift_workspace.png
:name: fig-drift-workspace
:width: 100%

The drift-correction workspace. Left: the settings, in workflow order. Right:
the drift trace, with `dx`, `dy` and the total displacement `|d|` per frame.
This stack was built with a known linear drift, so the trace is the ground
truth.
```

## Read the result

The status line reports the **maximum drift**, which is the number to act on:

* **below one pixel** — nothing to correct; leave the tool off;
* **a few pixels** — correct before any frame-lag analysis;
* **beyond the beam waist** — the uncorrected frame-lag results were measuring
  the stage, not the sample.

The **drift trace** tells you what kind of motion it was. A straight line is
stage drift. A step is a bump or a refocus. Noise about zero means there was
nothing there. An *erratic* trace usually means the assumption has failed — the
sample is rotating or deforming, which this correction cannot fix.

The **Projection** tab is the check that matters, because it is independent of
the numbers:

```{figure} figures/drift_before.png
:name: fig-drift-before
:width: 60%

Before: all frames summed. Drift smears every punctum into a diagonal streak
along the direction of travel.
```

```{figure} figures/drift_after.png
:name: fig-drift-after
:width: 60%

After: the same sum with the drift removed. The same signal is concentrated
back into round spots. If your "after" looks no sharper than your "before",
the correction did not work — do not export it.
```

## Export

* **💾 Export shifts** — a CSV with `frame, dx_px, dy_px, magnitude_px`, for
  plotting the drift rate or feeding another tool.
* **💾 Export stack** — the corrected stack as a multi-page TIFF, all channels
  corrected with the single estimate.

## Correcting before an image correlation

This is the main reason the tool exists. The
{doc}`image-correlation experiment </concepts/image_correlation>` reads
diffusion off frame lags, and drift adds a decay to exactly that axis.

You have two routes:

* **In the reader** — the image-correlation reader has its own **Drift
  correction** setting (Off / First frame / Previous frame / Stack mean). Turn
  it on and the correction happens before the correlation, with the measured
  shifts recorded in the dataset metadata. Use this when you already know the
  data drifts.
* **In this tool first** — measure here, look at the trace and the projections,
  and decide. Use this when you do not yet know whether drift is a problem,
  which is most of the time.

## Headless

```bash
img-drift movie.tif --channel 0 --reference first \
    --out-shifts drift.csv --out-stack corrected.tif
```

```
source        : movie.tif (image)
frames        : 12
channels      : ch0
max drift     : 24.19 px
final offset  : dy=+22.00 dx=-11.00 px
wrote shifts  : drift.csv
wrote stack   : corrected.tif
```

`--json` prints the same summary as JSON, including the full shift list.
`--roi roi.json` restricts the estimate to a stored region — worth doing when
most of the field is empty, since a bright structured patch gives a far sharper
correlation peak than a mostly-dark frame.

## Python

```python
from chisurf.plugins.microscopy.img_drift import core

result = core.measure_drift("movie.tif", channel=0, reference="first")
print(result.total_drift, "px")          # the number to act on
data, shifts = core.corrected_stack("movie.tif")

# photon streams: corrected photon by photon, so the image stays analysable
clsm, shifts = core.correct_photon_image("scan.ptu", channels=[0])
```

## See also

- Tool: **Drift Correction** (`chisurf/plugins/microscopy/img_drift/`).
