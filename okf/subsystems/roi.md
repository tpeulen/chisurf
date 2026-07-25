---
type: Subsystem
title: "Regions of interest"
description: The shared ROI geometry in chisurf/core/roi — one class answering both point membership (gating) and pixel rasterisation (imaging), with boolean composition, JSON persistence and a segmentation bridge.
resource: chisurf/core/roi/
tags: [subsystems, roi, imaging, gating, segmentation]
timestamp: '2026-07-25T00:00:00Z'
---

# Regions of interest

A region of interest answers one of two questions, and ChiSurf asks both:

* **Is this point inside?** — gating scattered data: burst parameters in a 2-D
  histogram, molecule centroids, any point cloud. `ROI.contains(points)`.
* **Which pixels are inside?** — restricting an image analysis to part of a
  frame. `ROI.to_mask(shape, extent, image)`.

Both follow from the same geometry, so they live on one object. That is the
point of the subsystem: before it, ChiSurf had at least seven unrelated notions
of "region" — index ranges in the image correlator, a painted array in
colocalization, a rectangle on the AutoForm image section, another on the 2-D
residual plot, watershed labels in molecule MLE, and ndX's data-space gates —
none of which could be combined, stored, or handed from one tool to another.

## Coordinates are supplied, not baked in

A ROI carries no axes. `to_mask` takes an `extent` `(x0, x1, y0, y1)` giving the
value span of the array being masked; omitting it means pixel-index
coordinates, with pixel centres on integers.

This is what lets **one rectangle** mean "these pixels" on a CLSM frame and
"these bursts" on an E-vs-S histogram. A gate drawn on a parameter plot and a
region drawn on an image are the same `RectangleROI`.

## The shapes

| Class | Covers |
| --- | --- |
| `RectangleROI` | index ranges, drawn boxes, histogram gates. Half-open, so abutting rectangles tile without overlap; `from_slices` converts array slice bounds |
| `EllipseROI` | circles (beads, spots) and rotated ellipses; the 2-D Gaussian gates on parameter histograms |
| `PolygonROI` | arbitrary regions **and** freehand outlines — a hand-drawn contour is just a polygon with many vertices, so there is no separate freehand type |
| `MaskROI` | anything not analytic: a painted brush stroke, one label of a segmentation, an imported classification map. Optionally cropped to a bounding box with an offset |
| `ThresholdROI` | intensity selection, absolute or percentile. Image-dependent, so it answers only the pixel question and raises on `contains` |
| `CompositeROI` | boolean combinations, built through the `&`, `|`, `^`, `-`, `~` operators |

Composition is where the split pays off: *"bright pixels inside this polygon"*
is `polygon & ThresholdROI(low=...)`, and a composite delegates per operand, so
an intensity-dependent region can take part in one.

## Persistence and segmentation

`ROI.to_dict()` / `roi_from_dict()` round-trip through plain JSON, including
nested composites, so a selection survives a project save, an RPC hop, or a
hand-off between tools.

`labels_to_rois(label_image)` is the bridge from segmentation: watershed
output, connected components or an imported classification map becomes a list
of regions that gate, combine and store like any drawn one.
`rois_to_labels` is the inverse.

## Building a region from the data

`builders.arbitrary_region` is the port of the reference suite's two-scale pixel
selection. A pixel survives only if its **local** statistics resemble those of
its **neighbourhood**: the mean and population variance in a small window are
compared against those in a larger window centred on the same pixel, and pixels
whose ratios fall outside the given folds are dropped.

That comparison is what it buys over a threshold. An aggregate, a speck of
debris or a dead patch need not be an outlier in the image as a whole — only
against its own surroundings. Two objects of *identical* brightness are told
apart by their extent, which no absolute threshold can do.

Deviation from the reference: the window filters use nearest-edge rather than
zero padding. Zero padding biases every border pixel downwards and makes the
frame edge look anomalous, rejecting a one-window-wide border for no physical
reason.

## Getting regions in and out

`io.py` covers three directions:

* **native JSON** — lossless for every shape including nested composites, and
  plain readable text rather than the binary mask file the reference exports,
  so a stored selection is diffable and hand-editable;
* **segmentation import** — a Cellpose `_seg.npy` (a pickled dict whose `masks`
  entry is a label image) or any integer label image becomes one region per
  object, so work done in a dedicated segmentation tool arrives as regions
  ChiSurf can gate, combine and store;
* **label images and binary masks**, both directions, for tools that know
  nothing about ChiSurf's own format.

## Consumers

* **Image correlation** (`core/experiments/ics/`) — the reader takes a `roi`
  and passes it to the correlator; it replaced the ad-hoc `masks.py` helpers.
* **Colocalization** (`core/fluorescence/imaging/colocalization/pixelwise.py`)
  — accepts a ROI or a bare mask; the painted brush region is now a `MaskROI`.
* **Molecule MLE** (`plugins/microscopy/sm_image_mle`) —
  `MoleculeMleResult.molecule_rois()` exposes the watershed labels as regions.
* **Drift correction** (`core/fluorescence/imaging/drift.py`) — estimates
  within a region, as PAM's MIA does.

Still on their own implementations, and the natural next migrations: the
AutoForm `image` section's `rect_roi_call`/`rect_roi_source` seam, the 2-D
residual plot's rectangle, and ndX's `DataSelection` hierarchy (which lives in
a separate package and would need the dependency direction thought through).

# Citations

[1] [Image correlation](/references/image-correlation-theory.md)
