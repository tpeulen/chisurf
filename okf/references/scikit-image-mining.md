---
type: Reference
title: "scikit-image: what is worth taking, and what is already here"
description: A subpackage-by-subpackage assessment of scikit-image against ChiSurf's imaging needs, with a verdict and a priority for each — written when the dependency was removed, so that "we dropped it" does not quietly become "we lost access to those ideas".
resource: junk/scikit-image/
tags: [references, imaging, segmentation, mining, dependencies]
timestamp: '2026-08-10T00:00:00Z'
---

# scikit-image: what is worth taking, and what is already here

scikit-image stopped being a dependency when the five functions the tree
actually imported were reimplemented (see
[regions of interest](/subsystems/roi.md)). Dropping a library is not the same
as deciding its remaining two hundred functions are worthless, and the risk
after a removal is that nobody looks again — so this is the look, taken once,
with a verdict per subpackage and a priority per candidate.

The checkout is `junk/scikit-image/`, annotated in place with
`CHISURF-REVIEWED` / `TAKEN` / `SKIPPED` headers on the files that were read.

## How the verdicts are assigned

* **Already covered** — ChiSurf has it, usually because the removal already
  reimplemented it or because scipy does it. Named so nobody re-derives it.
* **Take** — a real gap with a real consumer in this tree. Ported, or listed
  with what it would serve.
* **Take later** — a real gap with no consumer *yet*. Recorded with the
  capability it would unlock, so it is a decision rather than an oversight.
* **Not ours** — solves a problem fluorescence analysis does not have, or is
  the kind of general-purpose computer vision that belongs in an application
  built on top rather than in this one.

## Verdicts

| Subpackage | Best of it | Verdict | Why |
|---|---|---|---|
| `measure` | `regionprops`, `regionprops_table`, `marching_cubes`, `moments*`, `perimeter*` | **Already covered** | [`chisurf/core/roi/props.py`](/../chisurf/core/roi/props.py) mirrors it property for property under test; marching cubes is in chimol. `find_contours` was the one gap — **taken**. |
| `segmentation` | `watershed`, `clear_border`, `expand_labels`, `find_boundaries`, `relabel_sequential`, `random_walker`, `flood_fill` | **Take** (partly) | The first two came with the removal; the next three are **taken** here. `random_walker` and the level-set family are take-later. |
| `filters` | `gaussian`, `threshold_otsu`, `difference_of_gaussians`, `sobel`, `frangi`/`sato`/`meijering`, `threshold_local`, `median` | **Take** (partly) | First two came with the removal; `difference_of_gaussians` is **taken** (it is what band-passes a spot image). Ridge filters are take-later — they are for filaments, which the imaging tools do not yet analyse. |
| `morphology` | `remove_small_objects`, `remove_small_holes`, `white_tophat`, `skeletonize`, `binary_*`, `h_maxima`, `reconstruction` | **Take** (partly) | `remove_small_objects` / `remove_small_holes` / `white_tophat` **taken**; the binary operators are `scipy.ndimage` one-liners already. `skeletonize` and `reconstruction` are take-later. |
| `feature` | `blob_log`, `blob_dog`, `blob_doh`, `peak_local_max`, `canny`, `match_template`, `structure_tensor`, `graycomatrix` | **Take** (partly) | `peak_local_max` came with the removal; **`blob_log`/`blob_dog` taken** — multi-scale spot detection is what a single-molecule image wants and the tree had only a fixed-scale à trous detector. `match_template` is take-later. The descriptor zoo (ORB, SIFT, BRIEF, HOG, Haar, LBP, daisy, fisher_vector) is **not ours**. |
| `restoration` | `richardson_lucy`, `rolling_ball`, `denoise_tv_chambolle`, `denoise_nl_means`, `wiener`, `estimate_sigma` | **Taken** (deconvolution); rest take-later | `richardson_lucy` and `wiener` are done — the engine is compiled in the photon library's `math` module and the microscope-facing half is `chisurf.core.fluorescence.imaging.restoration`. The PSF source turned out to be already here: the **PSF determination** plugin fits beads and reports σ per axis, which is exactly the kernel builder's input. `rolling_ball` remains the top of the remainder; the `denoise_*` family below it. |
| `registration` | `phase_cross_correlation`, `optical_flow_*` | **Already covered**, with a caveat | [`imaging/drift.py`](/../chisurf/core/fluorescence/imaging/drift.py) does FFT cross-correlation with a parabolic sub-pixel refinement. scikit-image's *upsampled-DFT* refinement is more accurate at high upsampling; worth a measurement before deciding, not a port on faith. Optical flow is take-later (non-rigid drift). |
| `exposure` | `equalize_adapthist` (CLAHE), `rescale_intensity`, `match_histograms` | **Take later** | Display-side, not analysis-side: CLAHE would improve how a CLSM frame *looks* in the image widgets. `rescale_intensity` is three lines and is already written inline in several places — worth collecting when someone touches them. |
| `metrics` | `structural_similarity`, `peak_signal_noise_ratio`, `normalized_mutual_information`, `adapted_rand_error`, `variation_of_information` | **Take later** | SSIM has an unusual consumer: the render-regression tests, which currently compare images by mean pixel difference and therefore cannot tell a shifted image from a corrupted one. The segmentation-comparison metrics would earn their place the moment a second segmenter exists to compare against. |
| `transform` | `warp`, `rotate`, `resize`, `radon`/`iradon`, `pyramid_*`, `hough_*`, `integral_image` | **Mostly not ours** | `scipy.ndimage` covers affine warping and zooming. Radon is tomography, Hough is line/circle finding in machine vision — neither is a fluorescence problem. `downscale_local_mean` (binning) is the exception and is a two-line `reshape`-and-mean already used inline. |
| `graph` | `MCP`, `route_through_array`, `RAG`, `cut_normalized` | **Not ours** | Least-cost paths and region-adjacency graphs serve segmentation refinement of the kind these tools do not do; the [graph layer](/subsystems/graph.md) covers the graph structures the tree actually needs. |
| `util` | `view_as_windows`, `montage`, `block_reduce`, `img_as_*`, `apply_parallel` | **Not ours** | Sliding windows are `numpy.lib.stride_tricks`; the dtype conversions exist to paper over scikit-image's own float/uint conventions, which nothing here shares. |
| `color` | RGB↔Lab↔HSV, `label2rgb` | **Not ours** | ChiSurf's colour handling is colormaps over scalar data, not colour-space science. `label2rgb` is a lookup the plot layer already does. |
| `draw` | `polygon`, `disk`, `line`, `ellipse` rasterisation | **Already covered** | [`chisurf/core/roi/`](/../chisurf/core/roi/) rasterises its own shapes, with the coordinate convention this tree uses. |
| `io` | `imread`, `imsave` | **Deliberately refused** | It routes through `imageio`, a retired dependency. [`chisurf.core.fio.image`](/../chisurf/core/fio/image.py) is the seam, over the photon library's bundled libtiff. A guard test exists for exactly this. |
| `data` | Sample images | **Not ours** | The fixtures here are photon data. |
| `future` / `Cascade` / `fisher_vector` | Object detection, graph cuts | **Not ours** | |

## Taken in this pass

Landed in [`chisurf/core/roi/segmentation.py`](/../chisurf/core/roi/segmentation.py):

| Function | What it earns |
|---|---|
| `remove_small_objects` | Replaces a hand-rolled loop in molecule MLE that was `O(n_labels × frame)`. **Measured**: on a field of 92,016 components the loop takes 17–24 s and the bincount-and-lookup 15 ms — 1100–1550×. On a sparse field (1,500 molecules, few of them small) the two are a wash at 2 ms, because the loop only pays when a label is actually removed. The pathological case is a crowded field, which is exactly what `min_area` exists for. |
| `remove_small_holes` | The other half; a molecule with a dim centre currently segments as an annulus. |
| `relabel_sequential` | Removing objects leaves **gaps in the numbering**, and every consumer that treats a label image as `1..n` — including `regionprops` — then sees phantom empty regions. Molecule MLE had this bug. |
| `expand_labels` | Grow a segmentation into its surroundings without merging neighbours; the honest way to add a background annulus per molecule. |
| `find_boundaries` | One-pixel outlines, which is what a label overlay wants to draw. |
| `find_contours` | Marching squares: turns a mask into *polygons*, so a segmentation can become a `PolygonROI` rather than a `MaskROI` — resolution-independent, and editable in the region GUI. |
| `difference_of_gaussians` | Band-pass; suppresses both shot noise and the slowly varying background in one pass. The natural pre-filter for spot detection. |
| `white_tophat` | Background estimate by morphological opening, for uneven illumination. |
| `blob_log`, `blob_dog` | **Multi-scale** spot detection. The tree had a fixed-scale à trous wavelet detector in `tracking.py`; these find spots whose width is not known in advance and return that width, which is what a diffraction-limited image of unknown focus needs. |

## Where to pick this up

In priority order, and each with what it unlocks rather than just a name:

1. ~~`richardson_lucy` deconvolution~~ — **done**. The PSF source I expected to
   be the real work was already in the tree: the PSF determination plugin fits
   beads and reports σ per axis. The engine is compiled
   (`tttrlib modules/math/Deconvolution.cpp`), exact against the reference to
   1e-12, and the concept page is
   [`docs/concepts/deconvolution.md`](/../docs/concepts/deconvolution.md).
2. **`rolling_ball` background** (`restoration`). `white_tophat`, taken here, is
   the cheap approximation of it; the rolling ball is the one people expect and
   cite.
3. **SSIM for the render-regression tests** (`metrics`). The screenshot
   comparisons in `test/` use mean pixel difference, which cannot distinguish a
   one-pixel shift from a corrupted render. This is a testing-infrastructure
   win, not a feature.
4. **Sub-pixel drift by upsampled DFT** (`registration`). Measure it against the
   parabolic fit already in `drift.py` before porting — the parabolic fit may
   well be enough, and that is a measurement nobody has taken.
5. **CLAHE** (`exposure`), for the image widgets.
6. **`skeletonize` and `reconstruction`** (`morphology`), if filament or
   connectivity analysis ever arrives.

See also: [regions of interest](/subsystems/roi.md) for where the taken
functions live, [image I/O](/subsystems/image-io.md) for why `skimage.io` is
refused, and [Orange3 mining](orange3-mining.md) for the same exercise done on a
different library.
