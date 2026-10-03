---
type: Guide
title: Confocal scan images (CLSM)
description: A laser-scanning confocal microscope builds an image by rastering the focus across the sample while recording TTTR photons tagged with frame/line/pixel markers.
tags: [guides, imaging, tttr, photons]
---

# Confocal scan images (CLSM)

:::{admonition} Theory
:class: seealso
How CLSM images are reconstructed from a TTTR stream, per-pixel lifetime maps,
and the phasor approach to fit-free FLIM (the universal semicircle, the lever
rule) are explained in the concept page {ref}`concept-imaging-flim-phasor`.
:::

## What it does

A laser-scanning confocal microscope builds an **image** by rastering the focus
across the sample while recording TTTR photons tagged with frame/line/pixel
markers. From that stream ChiSurf reconstructs per-pixel data and computes
pixel-wise observables: intensity, **fluorescence lifetime** (FLIM), FRET,
phasors, and — for immobilised single molecules — per-pixel maximum-likelihood
lifetime fits. This is the imaging counterpart of the burst analyses.

## In ChiSurf

The engine is `tttrlib.CLSMImage`; the `microscopy/` plugin group provides the
tools:

```python
import tttrlib

tttr = tttrlib.TTTR("test/data/clsm/Leica_SP8.ptu")
img = tttrlib.CLSMImage(tttr, channels=[0, 1])  # reconstruct from frame/line/pixel markers
stack = img.intensity                            # frames × lines × pixels: (93, 512, 512)
mean_mt = img.get_mean_micro_time(tttr, minimum_number_of_photons=1)
decays = img.get_fluorescence_decay(             # per-pixel micro-time histograms
    tttr, micro_time_coarsening=16, stack_frames=True)
```

The per-pixel histogram array is frames × lines × pixels × micro-time bins
(uint8), so coarsen the micro-time axis and stack the frames before asking for
it on a full image.

Pixel-wise analyses: `img_pixel_mle` (per-pixel `2I*` lifetime, same harness as
[burst MLE](21_lifetime_from_bursts.md)), `img_pixel_phasor`, `img_pixel_intensity`,
`region_mle` (region-wise lifetime MLE), plus `psf_determination` and
`img_calibration`.

## Selecting pixels

A decay is built from the pixels you select. Paint them with the brush on the
image, then save the selection under a name in the **Regions** tab: each saved
region is listed with what it actually is — *Shape* and a *Measurement* such as
`13496 px, 85.8 ph/px` — so you can tell a real structure from a stray brush
stroke without applying it. Clicking a region makes it the current selection and rebuilds the decay.

**Save** writes `.json` (the region itself: geometry, name, and nested
combinations — the format to prefer) or a `.tif` / `.npy` mask image for tools
that read nothing else. **Load** reads all of those back, plus a Cellpose
`_seg.npy` segmentation, which arrives as one region per detected object.

The tool is **Imaging ▸ CLSM-Draw** (`chisurf/plugins/microscopy/clsm/`). Its left
window holds the controls: **Open TTTR / imaging**, **Build CLSM**,
**Add representation**, **Compute decay**, the exports, the **Setup preset** (PTU,
Leica SP5/SP8, MFIS Olympus), **Detector channels**, the CLSM image and representation
choices, the folded **Acquisition** fields (markers read from the file header,
pixels per line), **Brush & Decay** (brush size/width, select/deselect, live
update, *Image type* Intensity / Mean micro time, *Min #Ph*, micro-time *Coarsen*,
*Frames* mode), **Paint selection**, **Save painted region**, the analysis regions
and **Save / Load settings**. The image and the decay plot are two windows beside it;
**Guide** walks through a first scan and **Help** is the reference.

```{figure} figures/24_clsm_draw_window.png
:name: fig-24-clsm-draw-window
:width: 100%

CLSM-Draw on `test/data/clsm/Leica_SP5.ptu` (channel 0): the scan built, its
intensity representation, a painted selection and the decay of those pixels.
```

```{figure} figures/24_clsm_draw.png
:name: fig-24-clsm-draw
:width: 100%

CLSM-Draw on `test/data/clsm/Leica_SP8.ptu` (preset *Leica SP8*, channels
0,1; 93 frames of 512 × 512 summed). **Left:** the intensity image with the
brightest 5 % of pixels selected (white). **Right:** the decay of that
selection, 1 157 700 photons.
```

```{figure} figures/24_clsm_draw_rois.png
:name: fig-24-clsm-draw-rois
:width: 90%

The selection saved as the region *bright patch*: a mask of 13 496 px at
85.8 photons per pixel. *Combine* sets how enabled regions merge (∪ / ∩).
```

The same regions work headlessly:

```python
from chisurf.plugins.microscopy.clsm.api import clsm

clsm.extract_decay("image.ptu", mask_path="cell.json")   # a stored region
clsm.extract_decay("test/data/clsm/Leica_SP8.ptu", threshold=0.2)   # brightest pixels
# -> {"time_ns", "counts", "noise", "n_photons", "output_path"}
```

A saved region is not only for decays. Point the **Region** field of the
per-pixel MLE tool at the same `.json` and the FLIM fit runs inside it only —
one cell instead of the empty field around it, which is most of the compute in
a typical frame. The pixels outside come back unfitted, exactly as if they were
below the photon threshold.

The theory — what a region is, and the measurements reported for it — is in
{ref}`concept-region-properties`.

## Result

The same photon stream yields two co-registered images: an intensity map and a
lifetime map. The lifetime map is the one that reports on environment and FRET —
here a quenched (FRET) region is indistinguishable from a dim one by intensity
alone, but separates cleanly by lifetime.

```{figure} figures/clsm.png
:name: fig-clsm
:width: 100%

Simulated confocal scan. **Left:** photons per pixel. **Middle:** the per-pixel
lifetime; photon-starved pixels are masked (dark). **Right:** the micro-time
decays of the two regions — 3.2 ns unquenched versus 1.6 ns under FRET.
```

Per-pixel lifetime precision is photon-limited ($\sigma_\tau \approx
\tau/\sqrt{N}$), which is why FLIM images need far more photons per pixel than
intensity images and why dim pixels are masked rather than fitted.

## The Intensity tool

**Intensity** (`img_pixel_intensity`) is the first per-pixel step: it counts the photons of every pixel for each detector window and writes the imaging HDF5 the
other per-pixel tools enrich.

1. Type a path into **TTTR file** and press Enter, press **Browse** or **Database**, or drop a PTU/HT3 file on the window (a drop is also run).
2. Optionally open the **Detectors** tab: it is the Setup tool's detector editor; without a window the channel-0 window is computed.
3. Press **Run**. **Cancel** stops a running calculation.
4. Read the **Intensity**, **Count rate (kHz)** and **Frames (movie)** tabs; **Detector window** chooses the window shown. Wheel zooms, drag pans.
5. **Create imaging HDF5** writes the table, **Save container** writes it beside the photon file, **ndX** explores it, **Next** hands the file on inside the Imaging Tools pipeline.

```{figure} figures/24_intensity_tool.png
:width: 90%

The Intensity tool on a simulated 32 x 32 scan (12 frames, brighter disc on a gradient): settings on the left, the summed photon counts on the right.
```

### Mean micro-time, phasor and pixel-wise MLE

The other per-pixel tools use the same shell as Intensity: **TTTR file**, **Detector window**, **Run** / **Cancel**, **Add ... to HDF5**, **ndX**, **Next**
and the **Detectors** tab.

- **Mean micro-time** (`img_pixel_micro_time`) shows the photon-weighted arrival time per pixel in ns, with **Min. photons** discriminating dim pixels, and a
  per-frame movie. It is not a fitted lifetime.
- **Phasor-FLIM** (`img_pixel_phasor`) computes (g, s) per pixel at the **Frequency** (MHz, -1 reads the header) with the **IRF reference** of each window.
  On the **Phasor plot** add an ellipse, rectangle or polygon cursor under **Analysis regions** and drag its handles; the **Selected** tab shows the pixels
  it picks out.
- **Pixel-wise MLE** (`img_pixel_mle`) fits every pixel by Poisson maximum likelihood: add the photon files and the IRF, name the parallel and perpendicular
  channels, set the fit window and the model, and press **Run**; the **Lifetime map** tab shows tau and each file's table is written beside it.

```{figure} figures/24_micro_time_tool.png
:width: 90%

Mean micro-time of a simulated scan whose left half decays in 1 ns and right half in 3 ns.
```

```{figure} figures/24_phasor_tool.png
:width: 90%

The phasor plot of the same scan with an ellipse cursor round the 1 ns cluster; the universal semicircle is drawn in yellow.
```

```{figure} figures/24_mle_tool.png
:width: 90%

The pixel-wise MLE lifetime map of the simulated two-detector scan.
```

## See also

- `tttrlib.CLSMImage`; plugins in `chisurf/plugins/microscopy/`.
- Fit-free lifetime imaging via phasors and the same MLE estimator per burst:
  {ref}`concept-imaging-flim-phasor`, [lifetime from bursts](21_lifetime_from_bursts.md).
- Tool: **Pixel-wise MLE** (`chisurf/plugins/microscopy/img_pixel_mle/`), **Pixel Phasor** (`chisurf/plugins/microscopy/img_pixel_phasor/`) and **Mean Micro-Time** (`chisurf/plugins/microscopy/img_pixel_micro_time/`).
- Also for images: **Intensity** (`chisurf/plugins/microscopy/img_pixel_intensity/`) for the plain photon-count map, **IRF & BG** (`chisurf/plugins/microscopy/img_calibration/`) for the per-detector calibration the lifetime tools consume, **CLSM-Draw** (`chisurf/plugins/microscopy/clsm/`) to build an image from a stream by hand, **CLSM Generator** (`chisurf/plugins/microscopy/clsm_generator/`) to simulate one whose answer is known, and the **Image Browser** (`chisurf/plugins/tttr/tttr_image_browser/`) to page through a folder ({doc}`86_image_browser`).

## Known defects

- The *Brush & Decay* dock tab of CLSM-Draw reads **Brush _Decay**: the `&` in
  the title is taken as a Qt mnemonic marker.
