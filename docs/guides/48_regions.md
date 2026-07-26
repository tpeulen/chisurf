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

| Tool | What a region does there |
|---|---|
| **Imaging → Lifetime → Molecule-wise MLE** | the editor confines the molecule search; every measured molecule is drawn back as a region |
| **Imaging → CLSM-Draw** | the full editor: paint, draw, name, combine, measure; the decay follows the combined region |
| **Imaging → Colocalization** | gates the joint intensity histogram — bright pixels only, or a painted cloud |
| **Imaging → Phasor-FLIM** | the phasor cursor *is* a region on the $(g,s)$ plane |
| **Imaging → Drift Correction** | a structured patch gives a sharper correlation peak than a mostly-dark frame |
| **ndXplorer** | a gate on any two parameters selects the bursts inside it |

They are the same object in all six. A rectangle drawn on a confocal image and a
rectangle drawn on an $E$–$S$ histogram differ only in the axes handed to them at
the moment they are used.

## The region editor

Wherever a tool shows a **Regions** panel, it is the same editor.

```{figure} figures/regions_list.png
:name: fig-regions-list
:width: 100%

The region list, here in the CLSM tool. One row per region: its name, what kind
of shape it is, how big and how bright it is, and two tick boxes. The left tick
includes a region in the selection; unticking keeps it without using it — which
is how you see what a region was contributing. The **~** column uses everything
*outside* that region instead. **Combine** says how the ticked ones reduce to the
one selection the analysis uses, and the footer reports the result: `2 of 3 →
500 px`.
```

Each column earns its place:

* **Region** — double-click to rename. Names are unique; asking for one that is
  taken gives `cell (2)` rather than two rows reading `cell`.
* **Shape** — `rectangle`, `ellipse`, `polygon`, `mask` (painted or loaded) or
  `threshold`. A composite of several regions reads `composite`.
* **Measurement** — area and mean intensity, recomputed against the displayed
  image. These are the two numbers that say whether a selection is worth
  building a decay from; the full property set is in
  {ref}`concept-region-properties`.
* **~** — invert. Kept as a flag rather than baked into the geometry, so the
  region is still there to edit after you toggle it.

The toolbar: a name box and **+** keep whatever you are currently painting as a
named region; **▭ ◯ ⬠** draw a new rectangle, ellipse or polygon; 🗑 and ⧉
remove and duplicate; 📂 and 💾 load and save. Loading *adds* to the list rather
than replacing it — a file is one more source of regions.

```{figure} figures/regions_overlay.png
:name: fig-regions-overlay
:width: 100%

The same three regions on the image. Drawn shapes get grab handles and write
their new geometry straight back into the list; the selected one is drawn
thicker, and a region that is switched off is greyed rather than hidden. A
painted mask (the white patch) deliberately has **no** handle: there is no small
set of grips that would edit it, and a bounding box that replaced the mask on
the first drag would destroy what you painted.
```

## The single-molecule imaging workflow

This is the clearest use of all three roles at once. Open **Imaging → Lifetime →
Molecule-wise MLE**, add the CLSM file(s) and an IRF, and — optionally — an
**Analysis region**.

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

Tune the segmentation with **Preview** before pressing **Run**: it draws the
labels and one row per region, so *Smoothing σ*, *Threshold*, *Peak footprint*
and *Min area (px)* can be set against what they actually produce.

The **Molecules** tab shows both kinds of region at once, and they behave
differently on purpose:

* the **analysis region** has grab handles — it is a control, and moving it
  re-runs the search;
* each **molecule** is drawn as the ellipse with the same second moments as the
  measured object: its centroid, its major and minor axis lengths and its
  orientation, the numbers already in the result table. Those outlines are
  read-only, because a drag there would claim to edit something the analysis
  owns. They are what lets a segmentation be *checked* rather than trusted — an
  ellipse that misses its spot, or swallows two, is visible at a glance where a
  table of areas is not.

The same conversion is available in Python, so a measured object can be gated
with, combined and stored like a drawn one:

```python
for props in result.region_properties():
    region = props.as_ellipse()      # centroid, axes and orientation as a ROI
```

## Getting a region in

The **Analysis region** list accepts, and tells them apart by content:

* a **ROI JSON** saved by any ChiSurf tool — geometry, name and nested boolean
  combinations, so a union of three polygons reloads as one;
* a **mask image** (TIFF/PNG/NPY) — anything non-zero is inside;
* a **label image**, including a Cellpose or watershed export — several regions
  in one file, which arrive as their union when a single region is wanted.

## Headless

The GUI's **Analysis region** panel and this option are the same setting; the
editor's 💾 writes a file the CLI reads.

```bash
sm-image-mle analyze -i irf.ptu --roi cell_patch.json scan_001.ptu
```

```
Analyzing 1 file(s)…
Processed: ['scan_001.ptu']
Molecules fitted: 4
Output TSVs: ['scan_001_molecules.tsv']
```

Without `--roi` the whole frame is searched. The option takes the same three
file kinds as the GUI list, so a segmentation produced elsewhere works as an
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
from chisurf.plugins.microscopy.sm_image_mle.core.molecule_mle import (
    MoleculeMleSettings, fit_molecules_from_files,
)

settings = MoleculeMleSettings(roi=patch)     # a ROI, or its serialised dict
result = fit_molecules_from_files("scan_001.ptu", "irf.ptu", settings)

result.molecule_rois()                        # one region per molecule
result.foreground_roi()                       # all of them as one
result.background_roi(margin=3)               # with the PSF tails excluded
result.background_rate(margin=3)              # photons per background pixel
result.region_properties()                    # the shape table
```

Settings cross an RPC boundary as plain data, so `roi=` also accepts the
serialised form a region takes in a project file — a region set in the GUI
survives a save, a reload and a hop to a headless backend.

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
