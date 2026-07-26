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
| `EllipseROI` | circles (beads, spots) and rotated ellipses; the 2-D Gaussian gates on parameter histograms. A zero radius is a **collapsed** axis with no extent, not an unbounded one — a degenerate gate selects its centre (or a segment), never the whole plane |
| `PolygonROI` | arbitrary regions **and** freehand outlines — a hand-drawn contour is just a polygon with many vertices, so there is no separate freehand type |
| `MaskROI` | anything not analytic: a painted brush stroke, one label of a segmentation, an imported classification map. Optionally cropped to a bounding box with an offset, or given an `extent` so its cells span **values** rather than pixel indices — `from_histogram(mask, edges_x, edges_y)` is how a region painted on a 2-D histogram gates the data behind it |
| `ThresholdROI` | intensity selection, absolute or percentile. Image-dependent, so it answers only the pixel question and raises on `contains` |
| `CompositeROI` | boolean combinations, built through the `&`, `|`, `^`, `-`, `~` operators |

Composition is where the split pays off: *"bright pixels inside this polygon"*
is `polygon & ThresholdROI(low=...)`, and a composite delegates per operand, so
an intensity-dependent region can take part in one.

`ROI.bounds` is the geometric companion to `bounding_box`: the extent in the
region's *own* coordinates, exact and grid-free for the analytic shapes,
rasterised for masks and thresholds. Interactive handles need it — a rectangle
that re-derives its corners from a rasterised box walks across the image.
`ROI.to_indices` answers the same question for a *flattened* array, which is the
form a fit holds its data in.

## The three coercions every consumer needs

A consumer receives a region in whatever form its caller had, and the same three
conversions were being written out per consumer — four copies of the first alone,
each handling `None` slightly differently:

| Helper | Converts |
| --- | --- |
| `as_roi(value)` | a `ROI`, its serialised dict (RPC, project files), or `None` → `ROI \| None` |
| `as_mask(region, shape, ...)` | a `ROI`, a raw array, or `None` ("everything") → boolean mask |
| `union_of(rois)` | several regions → one gate; a single region passes through unwrapped |

`as_mask` carries one rule worth knowing: in a numeric array only **positive**
entries are inside. A paint buffer marks erased pixels with a negative, so the
obvious `!= 0` selects exactly what the erase brush removed.

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

`load_regions(path)` is the entry point consumers should use, with
`load_region(path)` for the single-gate case. Dispatching on the extension per
consumer looks trivial and is not: a label image is also a valid mask, so
sending it to the mask reader merges every object into one region, silently.
The shared loader decides from the file's own content.

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

Labels are located with one `find_objects` pass and each region is cut from its
own bounding box, rather than comparing the whole frame against every label in
turn — the difference between `O(n_labels x frame)` and `O(frame)`, which is
what a segmentation holding a few thousand molecules actually costs.

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
  molecule still carry its PSF tail. The region is reachable from all three
  surfaces: an **Analysis region** `path_list` in the AutoForm view, `--roi` on
  the CLI, and `MoleculeMleSettings(roi=…)` in Python; all three take a saved
  ROI JSON, a mask image or a label image, several regions arriving as their
  union.
* **Drift correction** (`core/fluorescence/imaging/drift.py`) — estimates
  within a region, as PAM's MIA does, cropping to `ROI.bounding_box`.
* **CLSM pixel select** (`plugins/microscopy/clsm`) — the brush still paints an
  array (that is what a brush is), but everything downstream of it is a region:
  `selection_roi()` wraps the paint buffer, saved regions are ROIs listed with
  their own measurements (`216 px, 41.8 ph/px`), save/load goes through the
  native JSON *and* the segmentation importers, and the headless
  `extract_decay` resolves `--mask` / `--threshold` to a `MaskROI` /
  `ThresholdROI`. `imaging.selection_array` is the single seam where a region
  becomes the `uint8` array tttrlib wants.
* **Per-pixel FLIM MLE** (`plugins/microscopy/img_pixel_mle`) —
  `PixelMleSettings.roi` confines the fit to part of the frame, so a per-pixel
  lifetime fit costs one cell instead of the empty field around it; the rows
  outside come back unfitted, as if below `min_photons`. The GUI's **Region**
  field reads whatever `roi/io.py` reads, which makes the hand-off concrete:
  paint a region in CLSM Draw, save it as JSON, load it here.
* **Phasor cursors** (`plugins/microscopy/img_pixel_phasor`) — a cursor gating
  the `(g, s)` plane is an `EllipseROI`; `cursor_roi` builds it and
  `mask_from_cursor(g, s, roi)` is the general form, so a cluster that is
  neither a circle nor an ellipse can be enclosed by a polygon and a ring is
  `outer - inner`. The `phasor.cursor_mask` RPC takes a serialised region and
  returns the one it used, so a gate replays on the next measurement.
* **PSF determination** (`plugins/microscopy/psf_determination`) — bead
  detection groups the bright pixels of each sampled slice into connected
  regions and seeds the 3-D Gaussian fit with each region's intensity-weighted
  centre. Two things follow from measuring regions rather than picking pixels:
  a `min_area` of 2 rejects hot camera pixels (a bead covers several pixels, a
  defect covers one), and the seed sits at the centre of the spot rather than
  on its brightest pixel.
* **Painted gates** — the colocalization scatter and the phasor plane both take
  a brush now: the strokes land in a buffer over the histogram bins,
  `MaskROI.from_histogram` turns them into a region on the value axes, and it
  gates like any other. A population is rarely a rectangle or an ellipse, and
  before this the paint could only ever mean pixels.
* **Scatter gates** — `pixelwise.colocalization_metrics(gate=...)` takes a ROI
  as readily as the `(a_min, a_max, b_min, b_max)` tuple, evaluated with
  `contains` on each pixel's `(a, b)` value pair. That is the axis-free claim
  paying off: a gate on a joint histogram and a region on a frame are the same
  object, and a population can be gated with an ellipse or a polygon without a
  line of new machinery. The tuple stays for the drawn rectangle because it is
  inclusive at both ends where a half-open `RectangleROI` is not.
* **AutoForm `image` section** — the draggable rectangle exchanges a
  `RectangleROI` through `region_call` / `region_source` (formerly
  `rect_roi_call` / `rect_roi_source`, which passed four floats). Placement uses
  `ROI.bounds`, exact for analytic shapes: rasterising a rectangle to find its
  own extent snaps the handles to pixel edges, and doing that on every redraw
  makes an interactive gate creep.

* **2-D residual plot** (`gui/plots/residual_image.py`) — the rectangle that
  picks a lag window maps to the fit range through `ROI.to_indices`, the
  primitive for "a region on a 2-D map → entries of the flattened data vector"
  an image correlation fits. Verified to reproduce the previous hand-rolled
  `iy0 * nx + ix0` arithmetic exactly.

The last one still on its own is ndX's `DataSelection` hierarchy — a
Gaussian/Mahalanobis ellipse, a 1-D interval and a histogram bitmap, with the
opposite mask convention (`True` = excluded). It lives in a separate package,
so a bridge belongs on the ChiSurf side; `MaskROI.from_histogram` and
`EllipseROI` now cover both of its 2-D shapes, which is what such a bridge would
need.

## The collection, and the GUI over it

A single region answers "is this inside?". What a user works with is a *list*:
several named regions, some switched off, one or two inverted, reduced to the
one selection an analysis uses. `RegionCollection` (`collection.py`) is that
list — an ordered sequence of `RegionEntry` (region + `enabled` + `invert`) with
a `combine` rule (`and`/`or`/`xor`), unique names, measurement, and JSON
persistence that keeps every shape and flag. It is Qt-free, so a headless
script, an RPC payload and the widget share one object.

Its semantics are deliberately the union of what the tools had: the CLSM tool's
names/save/load/measure, ndXplorer's per-row enabled+invert combined by AND, and
the MLE tools' implicit union of everything in a file. `combined()` returns
`None` when nothing is enabled — *not* an all-true region, so "no regions" and
"every region switched off" stay distinguishable; the `to_mask`/`contains`
conveniences answer all-true, and `excluded()` names ndXplorer's inverted
convention rather than leaving it to be remembered.

The GUI is `chisurf/gui/widgets/roi/`, in two separable halves:

* `RegionEditor` — the list: name, shape, measurement, on/off, invert, the
  combining rule, save/load, and an optional `+` that keeps whatever the host is
  currently painting. Registered as the AutoForm section `region_list`, so a
  plugin gets it from its `.view.json`.
* `RegionOverlay` — the shapes on a chiplot canvas, dragged and written back
  into the collection. Rectangle, ellipse and polygon; a mask or a threshold has
  no handle, on purpose (a bounding box that replaced the mask on first drag
  would destroy what the user painted).

Drawing an ellipse or a polygon needed chiplot to grow those ROI kinds, plus
`Roi.points` and `Roi.set_pen`. Until then `PolygonROI` and `EllipseROI` had
**no producer anywhere in the GUI** — loadable from a file, not drawable.

An overlay may also be *read-only* (`movable=False`), which is how a measured
object is drawn: `RegionProperties.as_ellipse()` returns the ellipse with the
same second moments — centroid, axis lengths, orientation — so a segmentation
can be checked against the image rather than trusted, and a measured object
becomes a region that can be gated with, combined and stored like a drawn one.
The angle conversion is the fiddly part: `orientation` follows scikit-image and
is measured from the *row* axis, while `EllipseROI` rotates in `(x, y) =
(column, row)`, so the rotation is `-(θ + π/2)`.

### ndXplorer's selections are the same type

`selections.py` converts ndXplorer's `DataSelection` hierarchy — a 1-D interval,
a Mahalanobis ellipse, a painted histogram bitmap — into a `RegionCollection`.
The mapping is term for term: each selection's `enabled`/`invert` are the entry's
flags, and ndXplorer's implicit AND is `combine="and"`. Two things differ and
both are mechanical: its `get_mask` returns `True` for *excluded* (hence
`excluded()`), and a selection names its axes by parameter index where a region
carries none, so the axes are supplied at conversion. A selection constraining a
parameter that is not on the plane is skipped, not approximated.

The bridge is duck-typed and lives on the ChiSurf side, so the dependency stays
one-directional. Its tests assert agreement with ndXplorer's own `get_mask`
point for point, which is the only way to know the inverted convention was
reconciled rather than merely described. Storing gates as a collection also
fixes a real loss: ndXplorer's `onLoad_selection` rebuilds **only** rectangles,
so a saved ellipse or painted population disappeared on reload.

Regions are `(x, y) = (column, row)` throughout. The AutoForm `image` section
disagreed for 2-D images only — pyqtgraph's default maps axis 0 to *x* — while
its own markers, click picks, rectangle gate and 3-D path all assumed
column-major x. Its image item is now `axisOrder="row-major"`, which makes the
widget agree with itself, with numpy and with this subsystem; before that, a
marker on any 2-D map landed transposed.

# Documentation

The user-facing pair: `docs/concepts/region_properties.md` (what the
measurements are and how they are defined) and `docs/guides/48_regions.md`
(where regions appear in each tool, the foreground/background workflow, the
headless `--roi` option and the Python API).

# Citations

[1] [Image correlation](/references/image-correlation-theory.md)
