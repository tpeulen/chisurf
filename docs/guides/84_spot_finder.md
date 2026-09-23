---
type: Guide
title: 'Finding spots and objects in an image'
description: Detecting molecules, puncta, beads or cells in a confocal or camera image with the Spot Finder — watershed, threshold, Laplacian- or difference-of-Gaussian — and writing the regions, with their pixels, into the measurement's container for Region MLE to fit.
tags: [guides, imaging, segmentation, regions]
---

# Finding spots and objects in an image

**What you get:** a label image and a table of regions — centroid, area, shape,
intensity, and for the blob detectors each spot's own width — written into
the measurement's container, where **Region MLE** fits a lifetime per region.
The Spot Finder decides *which pixels are an object*. It fits nothing.

Theory: the detectors, why a LoG threshold is in image units, and what limits
a centroid's precision are in {ref}`concept-particle-tracking`
("Scale-space detectors"). The region measurements are
{ref}`concept-region-properties`; localisation precision is
{ref}`concept-super-resolution`.

## 1. Open the tool

**Spectroscopy → Image Tools**, then **Spot Finder** in the left list, between
*CLSM Draw* and *Region MLE*. The Spot Finder has no menu entry of its own
(its manifest is `menu_hidden`); the Image Tools hub is the only way in from
the menu bar.

```{figure} figures/spot_finder_hub.png
:name: fig-spot-finder-hub
:width: 100%

The Spot Finder in the Image Tools hub, before anything is loaded. Three
tabs: **Detection** (settings), **Regions** (what was found) and **Run**
(one row per input file).
```

## 2. Settings

Add files to **Imaging files** (TIFF stacks, or PTU/HT3 imaging files,
which are reconstructed into an intensity image over all routing channels and
summed over frames), then choose a **Workflow**. Picking a workflow replaces
every setting below it with that recipe's; edit them afterwards to deviate.

| workflow | method | for |
|---|---|---|
| `single_molecule` (standard) | watershed, σ 1, Otsu, footprint 6, clear border | confocal single molecules; what Region MLE has always been fitted on |
| `camera_spots` | LoG, threshold 0.05, σ 1–4 px, 12 scales, min area 2 | diffraction-limited spots of unknown width, hot pixels |
| `objects` | threshold, σ 2, Otsu, min area 25 | cells, nuclei, vesicles; no splitting |

**Detection name** is the stem the regions are stored under; two names on one
field keep two detections side by side. **Analysis region** confines the
search, and the Otsu level is then computed from those pixels only.

| control | meaning |
|---|---|
| **Method** | `watershed` splits touching objects; `threshold` does not; `log`/`dog` find spots and their widths |
| **Threshold** | watershed/threshold: intensity level, < 0 = Otsu. log/dog: minimum of $-\sigma^2\nabla^2 G_\sigma * I$, **in image units** (see below) |
| **Smoothing σ** | Gaussian blur before thresholding (watershed/threshold only) |
| **Peak footprint** | side of the square in which watershed seeds must be maxima; larger merges seeds |
| **min σ / max σ / Scales / Overlap** | the scale ladder of log/dog in pixels (DoG ignores Scales); blobs overlapping by more than **Overlap** are merged |
| **Min / Max area (px)** | drop regions outside this range; max 0 disables |
| **Clear border** | drop regions touching the frame edge |
| **Fit window (px)** | the square a click-pick fits a Gaussian in (**Pick by clicking**) |

**Preview** detects in the first file and writes nothing. **Detect** runs
every file and writes each result into its own container. **Export** writes
the combined region table to TSV/CSV. **Load demo** simulates a PTU with four
objects of known lifetimes.

## 3. A real image

The data: a confocal HT3 image (256 × 256, PicoQuant HydraHarp, Seidel lab)
of a MEF cell expressing GFP-mGBP7 and mCherry-mGBP6, where the proteins
gather in puncta. All channels summed: 9.8 × 10⁶ photons, a median of 108
photons per pixel.

The three shipped workflows, as they are, in `--dry-run`:

| workflow | regions |
|---|---|
| `single_molecule` | 11 |
| `camera_spots` | 2296 |
| `objects` | 2 |

Neither extreme is right, and the reasons are instructive:

* **Otsu picks the wrong two classes.** Its level (186 photons after
  smoothing) separates the *cell* from the dark surround, not the puncta from
  the cytoplasm: 34 % of the frame is foreground. The cell touches the frame
  edge, **Clear border** removes it, and 11 fragments (109 px in total)
  remain. With Clear border off the same level gives 47 regions, the largest
  4006 px of cytoplasm.
* **`camera_spots` has a threshold of 0.05 in image units.** On an image in
  photons per pixel that admits every noise bump. Its threshold was chosen for
  images scaled to about one.

The LoG threshold must be read off the image. Scanning it on this field
(σ 1–4 px, min area 2):

| threshold | 0.05 | 5 | 20 | 50 | 100 |
|---|---|---|---|---|---|
| regions | 2296 | 1715 | 779 | **151** | 29 |
| same, image × 10 | 2296 | 2334 | 2048 | 1715 | 1318 |

The second row is the same image multiplied by ten: the count at threshold 50
on it equals the count at 5 on the original. The threshold scales with the
image. At 50, the regions sit on the puncta and none on the nucleus:

```{figure} figures/spot_finder_detection.png
:name: fig-spot-finder-detection
:width: 100%

**Detection** after a Preview: workflow `camera_spots`, threshold raised to
50, max σ 4. 151 regions in 1 file.
```

```{figure} figures/spot_finder_regions.png
:name: fig-spot-finder-regions
:width: 100%

**Regions**: every detected region drawn as its second-moment ellipse on the
intensity image; the list gives each one's area, and the panel below it the
selected region's measurements. The larger circles are spots whose best scale
was near max σ.
```

The widths: median σ 1.27 px, and 12 of 151 at max σ = 4. Spots at the top of
the ladder are larger than the ladder allows; raise **max σ** until none sit
there, or accept that their width is a floor. DoG at the same threshold finds
72, because its response is a different normalisation.

## 4. Reading the result

Per region the table carries `region.centroid_*` (the shape's centre),
`region.centroid_weighted_*` (intensity-weighted, where the molecule is),
bounding box, area, perimeter, circularity, eccentricity, solidity, axis
lengths, orientation, `region.intensity_sum/mean/min/max/std` and, for
log/dog, `spot.sigma`. On this image the two centroids differ by a median
0.08 px.

**How precise is a position?** For the median spot here, 2660 net photons
($N$, background-subtracted), σ = 1.27 px, and $b$ = 128 photons per pixel,
the mean over pixels away from any region (`background_rate()`). Thompson's
estimate {cite}`thompson2002` with pixel $a$ = 1:

$$
\sigma_{xy}^2 \approx \frac{s^2 + a^2/12}{N} + \frac{8\pi s^4 b^2}{a^2 N^2}
\quad\Rightarrow\quad \sigma_{xy} \approx 0.39\ \text{px},
$$

of which photon counting alone is 0.025 px. The cytoplasmic background is the
limit, not the photons. The weighted centroid and least-squares fits
used here are not efficient estimators; a maximum-likelihood fit with the
right noise model reaches the Cramér–Rao bound {cite}`mortensen2010`.

**Picks.** Clicking the **Regions** image fits a 2-D Gaussian (least squares)
in a **Fit window** square around the click. Clicked 1.8 px off 40 detected
spots, 34 fits converged and landed a median 0.38 px from the weighted
centroid: the fit undoes the click offset, and the remaining disagreement is
the size of the Thompson estimate. **Add picks** adds them only where nothing was found.

## 5. Where the result goes

**Detect** writes an `image_data` label raster and a `region_table` joined
by `label` into each measurement's container, one row per region.
**Region MLE**, the next entry in the hub, fits a lifetime per region from its
pixels' photons. The table can also be exported, or read by any tool that reads
the region contract.

## 6. Headless

```bash
csc spot-finder workflows
csc spot-finder detect --dry-run --workflow camera_spots --threshold 50 FILE
csc spot-finder detect --workflow single_molecule --name spots FILE…   # writes
csc spot-finder run recipe.json FILE…                                   # your own recipe
```

An option you do not type does not override the workflow.

```python
from chisurf.plugins.microscopy.spot_finder.core.spots import (
    SpotFinderSettings, detect, load_intensity)

image = load_intensity(path)                      # all channels, summed over frames
settings = SpotFinderSettings(method="log", threshold=50.0,
                              min_sigma=1.0, max_sigma=4.0, num_sigma=12, min_area=2)
result = detect(image, settings)
print(result.n_regions, "regions; background", round(result.background_rate(), 1), "per pixel")
# 151 regions; background 128.4 per pixel
result.write(path, name="puncta")   # label raster + region table, into the container
```

Over RPC: `spot_finder.detect.run` with `files`, `workflow` and `settings`
overrides (an unknown key is refused).

## Using it well

* **Scan the LoG/DoG threshold on every new kind of image**, and keep it only
  for images of the same brightness scale. Photon counts, camera ADU and a
  normalised TIFF need thresholds orders of magnitude apart.
* **Check what Otsu separated.** Otsu splits the histogram into two classes;
  on a cell with puncta those classes are cell and surround. If the standard
  workflow finds a handful of regions on an obviously crowded field, set a
  fixed threshold, or draw an **Analysis region** inside the cell so the level
  is computed from cytoplasm and puncta only.
* **Set min/max σ from the optics**: σ ≈ 0.21 λ/NA, in pixels.
* **Leave Clear border on** for anything that is fitted; a cut-off object has
  a biased centroid and area.
* **Name each detection.** Re-running under the same name replaces it.

## Known defects

* **The LoG/DoG threshold is described as independent of image units, and it
  is not.** The Threshold tooltip, the `SpotFinderSettings.threshold`
  docstring and the `blob_dog` docstring in `chisurf/core/roi/segmentation.py`
  say it "does not follow the image units". The response is $-\sigma^2\nabla^2 G_\sigma * I$,
  linear in $I$ (measured above: ×10 image, ×10 effective threshold).
* **`camera_spots` ships threshold 0.05**, which only makes sense for an image
  scaled to about one; on photon counts it returns every noise maximum (2296
  regions here).

## See also

- {doc}`48_regions` — drawing, combining and reusing regions.
- {doc}`50_particle_tracking` — the same detection problem, in time.
- {ref}`concept-region-properties` — what each column measures.
