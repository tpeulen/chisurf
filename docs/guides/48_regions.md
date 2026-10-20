---
type: Guide
title: 'Regions: selecting pixels, measuring what you selected'
description: Almost every imaging analysis begins by deciding which pixels count — a cell, an illuminated patch, a bead, one immobilised molecule, the empty field that measures background.
tags: [guides, imaging, corrections]
---

# Regions: selecting pixels, measuring what you selected

Almost every imaging analysis begins by deciding **which pixels count** — a
cell, an illuminated patch, a bead, one immobilised molecule, the empty field
that measures background. ChiSurf calls all of them *regions* and treats them as
one kind of object, whether drawn with a mouse, thresholded, painted, or
imported from a segmentation.

This guide is how to use them. For what the measured numbers mean — area,
circularity, the inertia-tensor axes, why a perimeter is not a pixel count — see
{ref}`concept-region-properties`.

## Where regions appear

The imaging tools are steps of **Spectroscopy → Imaging → Image Tools**; Drift Correction is a button of its own there.

| Tool | What a region does there |
|---|---|
| **Spot Finder** | the analysis region confines the search; every detected object is written as a region |
| **Region MLE** | fits one lifetime per detected region; its analysis region restricts which are fitted |
| **CLSM Draw** | the full editor: paint, draw, name, combine, measure; the decay follows the combined region |
| **Colocalization** | every gate on the intensity scatter in one list — a typed box, a painted cloud, a drawn shape — combined rather than overriding |
| **5. Phasor-FLIM** | cursors on the $(g,s)$ plane; the *Selected* tab shows the pixels they pick out |
| **Drift Correction** (headless `--roi`) | a structured patch gives a sharper correlation peak than a mostly-dark frame |
| **ndX** | a gate on any two parameters selects the bursts inside it |

They are the same object in all of them. A rectangle drawn on a confocal image and a
rectangle drawn on an $E$–$S$ histogram differ only in the axes handed to them at
the moment they are used.

## The region editor

Wherever a tool shows an **Analysis regions** panel, it is the same editor.

```{figure} figures/regions_list.png
:name: fig-regions-list
:width: 100%

The *Analysis regions* panel, here in CLSM Draw, holding a painted mask
(*membrane ring*), a drawn ellipse used inverted (*nucleus*) and a rectangle
switched off (*empty patch*). **Combine regions** reduces the enabled ones to the
one selection the analysis uses.
```

* **Add rectangle / Add ellipse / Add polygon** put an editable shape in the
  centre of the displayed image.
* **Enabled** includes a region in the selection; unticking keeps it without
  using it — which is how you see what a region was contributing.
* **Invert** uses everything *outside* the region. It is a flag rather than
  baked into the geometry, so the region is still there to edit after you toggle
  it.
* **Combine regions** — `and`, `or` or `xor` over the enabled regions.
* Click a region's name to select it. Then **Region name** renames it (names are
  unique: asking for one that is taken gives `cell (2)`), its coordinates are
  editable numbers, and its area and mean intensity are shown against the
  displayed image — the two numbers that say whether a selection is worth
  building a decay from; the full property set is in
  {ref}`concept-region-properties`. **Duplicate region** and **Remove region**
  act on it.
* **Save regions** writes JSON (shapes, names, ticks and rule) or a TIFF/NumPy
  label raster; **Load regions** *adds* to the list rather than replacing it —
  JSON, masks, label images or Cellpose files are each one more source of
  regions.

In CLSM Draw, **Save painted region** keeps whatever you have painted as a mask
region under the name in **Region name**.

```{figure} figures/regions_overlay.png
:name: fig-regions-overlay
:width: 100%

The same regions on the image. The drawn ellipse has grab handles that write its
new geometry straight back into the list. The painted mask (the teal patch)
deliberately has **no** handle: there is no small set of grips that would edit
it, and a bounding box that replaced the mask on the first drag would destroy
what you painted. The switched-off rectangle is not drawn.
```

## The single-molecule imaging workflow

This is the clearest use of all three roles at once. Detection and fit are two
steps of Image Tools: **Spot Finder** finds the molecules and writes them into
each measurement's container, **Region MLE** fits one lifetime per region it
finds there (see {doc}`84_spot_finder`). In Spot Finder add the CLSM file(s)
and — optionally — an **Analysis region**.

```{figure} figures/regions.png
:name: fig-regions
:width: 100%

Left: a frame with eight molecules and a drawn analysis region; only the four
inside it are searched for. Middle: each segmented molecule is its own region,
with the measured centroid marked. Right: the background is the patch *minus the
molecules dilated by a 3-pixel margin* — 13.9 photons/pixel. Taking the plain
complement instead gives 25.2, an **81 % overestimate**, because the pixels
touching a molecule still carry the tail of its point-spread function.
```

Three regions are involved:

1. **The analysis region** — one cell, one illuminated patch. It is applied
   *before* thresholding, so an automatic (Otsu) threshold is computed from that
   region's own pixels. This is the point of restricting an analysis: the rest of
   the frame should not set its threshold. Leave it empty for the whole frame.
2. **The foreground** — the union of the segmented molecules. Each molecule is
   also a region in its own right, so its area, circularity and weighted centre
   sit in the result table beside its fitted lifetime.
3. **The background** — *not* the complement of the foreground. Dilate first,
   as the figure shows, or every molecule looks dimmer than it is.

Tune the segmentation with **Preview** before pressing **▶ Detect**: it draws
the labels on the **Regions** tab, so *Smoothing σ*, *Threshold*, *Peak
footprint* and *Min area (px)* can be set against what they actually produce.
Then, in Region MLE, add an IRF and press **Run**.

The analysis region and the molecules behave differently on purpose:

* the **analysis region** has grab handles — it is a control;
* each **molecule** is an outline of what was measured. It is read-only, because
  a drag there would claim to edit something the analysis owns. The outlines are
  what lets a segmentation be *checked* rather than trusted — one that misses its
  spot, or swallows two, is visible at a glance where a table of areas is not.

In Python a fitted molecule converts to the ellipse with the same second
moments — its centroid, major and minor axis lengths and orientation, the
numbers already in the result table.

The same conversion is available in Python, so a measured object can be gated
with, combined and stored like a drawn one:

```python
for props in result.region_properties():
    region = props.as_ellipse()      # centroid, axes and orientation as a ROI
```

## A region on a data plane

Three of those tools do not gate an image at all. A region carries no axes, so
the same object works wherever there are two of them:

* the **phasor cursor** is an ellipse — or a polygon, for a cluster that is
  neither round nor elliptical — drawn on $(g,s)$. Because the phasor plane and
  the image are two views of the same pixels, a cursor answers *which pixels have
  that lifetime*; the **Selected** dock is the intensity map gated by it.
* the **colocalization gate** is drawn on the joint intensity histogram, whose
  axes carry the intensities themselves. The typed box, a painted population and
  any shape you draw are entries in one list, so "this cloud **and** above that
  threshold" is expressible — previously a painted gate simply overrode the box.
* **ndX's** gates are the same thing under another name. Its selections
  carry per-row *enabled* and *invert* and combine by AND, which is exactly a
  region collection; `chisurf.core.roi.selections` converts between them:

  ```python
  from chisurf.core.roi import collection_from_selections, excluded_mask

  gates = collection_from_selections(ndx_selections, axes=(0, 1))
  hidden = excluded_mask(gates, data, axes=(0, 1))   # ndX's convention
  gates.save("gates.json")                           # every shape survives
  ```

  Note the two conventions: `contains` answers where a point is *inside*, ndX's
  `get_mask` answers where it is *excluded*. `excluded()` names the second so it
  is not re-derived — and re-derived wrongly — at each call site. Saving through
  a collection also fixes a real loss: ndX's own loader rebuilds only
  rectangles, so a saved ellipse or painted population silently disappeared on
  reload.

## Getting a region in

The **Analysis region** list accepts, and tells them apart by content:

* a **ROI JSON** saved by any ChiSurf tool — geometry, name and nested boolean
  combinations, so a union of three polygons reloads as one;
* a **mask image** (TIFF/PNG/NPY) — anything non-zero is inside;
* a **label image**, including a Cellpose or watershed export — several regions
  in one file, which arrive as their union when a single region is wanted.

## Headless

The GUI's **Analysis region** panel and `--roi` are the same setting; the
editor's **Save regions** writes a file the CLI reads.

```bash
csc spot-finder detect --roi cell_patch.json scan_001.ptu
csc region-mle analyze -i irf.ptu --regions scan_001.ptu scan_001.ptu
```

`--regions` names where the regions are: a container the Spot Finder wrote (or a
file beside it, as here), a label image, or a saved region file.

```
Analyzing 1 file(s)…
Processed: ['scan_001.ptu']
Molecules fitted: 4
Output TSVs: ['scan_001_molecules.tsv']
```

Without `--roi` the whole frame is searched. It takes the same three file kinds
as the GUI list, so a segmentation produced elsewhere works as an
analysis mask with no conversion step.

## Python

```python
from chisurf.core.roi import (
    RectangleROI, PolygonROI, MaskROI, RegionCollection, load_region, save_rois,
    regionprops, regionprops_table, labels_to_rois, union_of,
)

# build, combine, store
patch = RectangleROI(14, 14, 74, 74, name="illuminated patch")
cells = union_of([patch, PolygonROI([(80, 10), (95, 40), (70, 45)])])
save_rois([cells], "regions.json")
region = load_region("regions.json")          # several -> their union

# the two questions a region answers
mask = region.to_mask(image.shape)            # which pixels?
hits = region.contains(burst_es_coordinates)  # is this point inside?

# measure — the property names are skimage's, exactly
props = regionprops(label_image, intensity_image=image)
props[0].area, props[0].eccentricity, props[0].centroid_weighted
table = regionprops_table(
    label_image, intensity_image=image,
    properties=("label", "area", "centroid", "intensity_mean"),
)                                             # dict of arrays; centroid-0/-1

# anisotropic pixels: areas, lengths and centroids come out in real units
regionprops(label_image, spacing=(0.08, 0.04))   # µm per pixel, y then x

# a measurement converts back into a selection
rois = labels_to_rois(label_image)            # one region per label
```

The list the editor shows is a `RegionCollection`, and it is the same object
headless:

```python
regions = RegionCollection(combine="and", name="selection")
regions.add(RectangleROI(14, 14, 74, 74, name="patch"))
regions.add(nucleus, invert=True)             # everything outside it
regions.set_enabled("patch", False)           # keep it, stop using it

regions.combined()                            # one ROI, or None if nothing is on
regions.to_mask(image.shape)                  # all-true when nothing is on
regions.contains(points)                      # gate scattered data
regions.excluded(points)                      # the same answer, inverted
regions.properties(image.shape, image=image)  # measure every row

regions.save("regions.json")                  # shapes, names, ticks and rule
RegionCollection.load("regions.json")
```

`combined()` answers `None` when nothing is ticked — deliberately not an
all-true region, so "no regions" and "every region switched off" stay
distinguishable. `to_mask` and `contains` answer *everything* in that case,
because an analysis handed an empty list should run on the whole frame.

The property names, definitions and algorithms follow
`skimage.measure.regionprops` exactly and are checked against it property by
property, so a number reported here is directly comparable to one computed in
any other image-analysis pipeline, and code written for one transfers.

For the molecule-wise workflow specifically:

```python
from chisurf.plugins.microscopy.region_mle.core.region_mle import (
    RegionMleSettings, fit_regions_from_files,
)

# regions: a container (or a file beside it), a label image, or a list of ROIs
settings = RegionMleSettings(regions="scan_001.ptu")
result = fit_regions_from_files("scan_001.ptu", "irf.ptu", settings)

result.molecule_rois()                        # one region per molecule
result.foreground_roi()                       # all of them as one
result.background_roi(margin=3)               # with the PSF tails excluded
result.background_rate(margin=3)              # photons per background pixel
result.region_properties()                    # the shape table
```

Settings cross an RPC boundary as plain data, so `roi=` (the analysis region)
also accepts the serialised form a region takes in a project file — a region set in the GUI
survives a save, a reload and a hop to a headless backend.

## Region MLE: the demo's fit assumptions

**Load example** in Region MLE simulates a four-object field, detects it with
the standard Spot Finder workflow and fills the panel in. It is a lifetime exercise using the **2I\* (P+2S)**
objective. Its individual simulated molecules have frozen dipole orientations. Their
parallel/perpendicular intensity ratios therefore differ from the orientationally
averaged anisotropy assumed by the fixed r0 and rho settings. Inspect **Decay**:
the split-channel residuals can be strongly systematic even when the lifetime
matches the explicit reference. This example does not validate anisotropy or a
good polarized fit. Longer lifetimes also carry the finite 8.192 ns period
bias: a finite laser period wraps the unrelaxed tail ({ref}`concept-tcspc-synthetic-decays`).

```{figure} figures/region_mle_native_wide_counts.png
:name: fig-region-mle-demo
:width: 100%

Region MLE after **Load example** and **▶ Run**: the four detected regions
outlined on the counts image, region 1 fitted at τ = 1.00 ns from 57 492 photons.
```

## Using it well

* **Restrict before you threshold, not after.** Masking the result of a
  whole-frame threshold is not the same analysis: the threshold was already set
  by pixels you meant to exclude.
* **Never take the background as the complement.** A margin of 2–3 pixels is
  enough at typical confocal sampling; the figure above shows what skipping it
  costs.
* **A region is not a crop.** Correlation analyses need the region's *bounding
  box*, because a zeroed pixel is not an absent pixel — see
  {ref}`concept-image-correlation`.
* **Paint when the population is not a box.** On a 2-D histogram the brush
  strokes are bins, so a phasor cluster or a diagonal band can be selected as the
  shape it actually is.

## See also

- The theory, formulas and citations: {ref}`concept-region-properties`.
- Object-based colocalization, which counts and compares segmented objects:
  {doc}`38_colocalization`.
- Confocal images and per-pixel lifetime analysis: {doc}`24_scan_images`.
- Detection: {doc}`84_spot_finder`.
- Tools: **Image Tools** (`chisurf/plugins/microscopy/imaging_tools/`), **Region MLE**
  (`chisurf/plugins/microscopy/region_mle/`).
