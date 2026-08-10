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
| `registration` | `phase_cross_correlation`, `optical_flow_*` | **Already covered, and better** | [`imaging/drift.py`](/../chisurf/core/fluorescence/imaging/drift.py) does FFT cross-correlation with a parabolic sub-pixel refinement. The caveat that used to sit here — that scikit-image's *upsampled-DFT* refinement might be more accurate — has now been **measured, and it is the other way round**. See below. Optical flow is not ours: non-rigid drift is not a problem these tools have. |
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

## Sub-pixel drift: measured, and the port is refused

The one item on the old list that was a question about *shipping* code rather
than a wish. Twenty random shifts in ±3 px, a 128×128 field of 40 diffraction-
limited spots, error in pixels against the truth:

| | parabolic (`drift.py`) | upsampled DFT (skimage) |
|---|---:|---:|
| circular shift, noiseless | 0.0101 | **0.0072** |
| circular shift, 200k photons | **0.0148** | 0.3435 |
| content leaves the frame, noiseless | **0.0083** | 0.1682 |
| content leaves the frame, 200k photons | **0.0140** | 0.4644 |

The upsampled DFT wins only in the one idealised case — no noise, and a
circular shift that loses nothing off the edge — and by 0.003 px. On photon
data it is **23× worse**, and it degrades again when content leaves the frame.

The reason is structural rather than incidental, which is why this is a refusal
and not a "not yet": phase correlation *whitens* the spectrum, so shot noise at
high spatial frequencies is amplified to the same weight as signal. That is
precisely wrong for photon-limited sparse images. The un-whitened
cross-correlation with a Gaussian smoothing (`smooth=2.0`) before the peak
search is the better estimator here, and it is already what ships.

**Do not port it.** If someone later has drift data where the DFT wins, the
harness above is the thing to re-run first.

## What is left

Nothing that has a consumer. scikit-image is out of the shipped tree entirely —
no module under `chisurf/` imports it, and it appears in no manifest. It
survives only as a **parity oracle** in three test files
(`test_regionprops.py`, `test_segmentation.py`, `test_restoration.py`), which is
what keeps proving the replacements agree with the library they replaced.

The remainder of the library is recorded here as **refused unless a consumer
appears**, rather than as a backlog. Porting on the grounds that a function is
well known is how a dependency comes back one function at a time:

| | why not, until something needs it |
|---|---|
| `rolling_ball` | `white_tophat`, already taken, is the same job. The rolling ball is the one people cite, which is not a reason. |
| `denoise_tv_chambolle`, `denoise_nl_means` | Denoising a photon-counting image discards the statistics the fits depend on. Deconvolution under a Poisson likelihood is the right tool and it is here. |
| `equalize_adapthist` (CLAHE) | Display-side only, and no image widget has asked. |
| `skeletonize`, `reconstruction` | For filament and connectivity analysis, which these tools do not do. |
| `random_walker`, level sets | Segmentation refinement beyond what watershed gives; nothing needs it. |
| `frangi`/`sato`/`meijering` | Ridge filters, i.e. filaments again. |
| `match_template`, `optical_flow_*` | Machine-vision problems, not fluorescence ones. |
| `structural_similarity` | The one with a *plausible* consumer — the render-regression tests compare by mean pixel difference and cannot tell a one-pixel shift from a corrupted render. Left refused deliberately: the project already judges GUI parity by control inventory rather than by a pixel metric, precisely because such a threshold is either always red or so loose it proves nothing. Port it only if a render test is shown to miss a real regression. |

See also: [regions of interest](/subsystems/roi.md) for where the taken
functions live, [image I/O](/subsystems/image-io.md) for why `skimage.io` is
refused, and [Orange3 mining](orange3-mining.md) for the same exercise done on a
different library.
