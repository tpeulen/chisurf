---
type: Subsystem
title: "Regions of interest"
description: The shared ROI geometry in chisurf/core/roi — one class answering both point membership (gating) and pixel rasterisation (imaging), plus scikit-image-compatible region properties, with boolean composition, JSON persistence and a segmentation bridge.
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

## Measuring a region

`props.py` answers the third question — *what is it?* — with
`regionprops(label_image | mask | ROI | [ROI], intensity_image)` and
`regionprops_table(...)`, deliberately mirroring `skimage.measure.regionprops`:
same signature, same property names (`area_bbox`, `axis_major_length`,
`centroid_weighted`, `intensity_mean`, ...), same algorithms, and therefore the
same numbers — the border-weighted perimeter, the Crofton variant, the
half-pixel-offset convex hull, the inertia-tensor axes, the orientation sign
convention and the Euler coefficients all match, property by property, under
test. Borrowing the interface means habits and code transfer both ways and a
reported number is comparable with any other imaging pipeline.

Three things extend it: a **drawn region or a bare mask measures like a label**,
so a hand-drawn selection and a watershed output are directly comparable;
`RegionProperties.to_roi()` converts a measurement back into a region, closing
the loop between measuring and selecting; and `circularity` / `intensity_sum`
are reported because the imaging plugins here need them.

The pay-off is that the measurements stop being re-derived. Molecule MLE used
`skimage.measure.regionprops` directly and object colocalization used a pile of
per-quantity `scipy.ndimage` reductions; both now read one property set.

Caveat worth carrying: on regions a few pixels across the discrete perimeter is
biased in both directions, so `circularity` can exceed 1 (a 7x7 square scores
1.07). It sorts single molecules; it does not measure them.

## Consumers

* **Image correlation** (`core/experiments/ics/`) — the reader takes a `roi`
  and passes it to the correlator; it replaced the ad-hoc `masks.py` helpers.
* **Colocalization** — `pixelwise.py` accepts a ROI or a bare mask (the painted
  brush region is a `MaskROI`); `objects.py` measures its segmented objects with
  `regionprops` and exposes them through `ObjectSet.properties` / `.rois()`.
* **Molecule MLE** (`plugins/microscopy/sm_image_mle`) — the whole foreground /
  background split is regions: `MoleculeMleSettings.roi` confines the search
  (applied *before* the Otsu threshold, so the region sets its own level),
  `molecule_rois()` / `foreground_roi()` / `background_roi(margin)` partition the
  frame, `background_rate()` reads the mean photon rate outside the molecules,
  and the per-molecule table's shape columns come from `regionprops`. The
  background is the *dilated* foreground's complement — the pixels touching a
  molecule still carry its PSF tail.
* **Drift correction** (`core/fluorescence/imaging/drift.py`) — estimates
  within a region, as PAM's MIA does, cropping to `ROI.bounding_box`.

Still on their own implementations, and the natural next migrations: the
AutoForm `image` section's `rect_roi_call`/`rect_roi_source` seam, the 2-D
residual plot's rectangle, and ndX's `DataSelection` hierarchy (which lives in
a separate package and would need the dependency direction thought through).

# Citations

[1] [Image correlation](/references/image-correlation-theory.md)
