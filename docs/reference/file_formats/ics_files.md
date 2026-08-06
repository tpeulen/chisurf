---
type: File Format
title: Image-correlation (ICS) files
description: This section describes how to load image data for image correlation spectroscopy — RICS, STICS, TICS and iMSD — from TTTR files and image stacks into ChiSurf using the Image correlation experiment.
tags: [reference, file-formats, imaging, correlation, tttr, photons]
---

# Image-correlation (ICS) files {#ics-image-correlation}

This section describes how to load image data for **image correlation
spectroscopy** — RICS, STICS, TICS and iMSD — from TTTR files and image stacks
into ChiSurf using the **Image correlation** experiment.

Those four names are readings of one correlation carpet rather than four
analyses; the theory page {doc}`/concepts/image_correlation` explains why, and
this page covers only the loading side.

## Supported input formats

The reader supports two main input types:

- **TTTR files** handled by `tttrlib.TTTR`, typically PicoQuant PTU or similar
  time-tagged formats.
- **Image stacks** (TIFF): single-plane or multi-frame TIFF files that contain
  pre-binned intensity images. Multi-page and LZW-compressed stacks are read
  natively.

## Reader setup: Image correlation (RICS/STICS/TICS/iMSD)

In the main GUI, select:

- **Experiment**: `Image correlation`
- **Setup**: `Image correlation (RICS/STICS/TICS/iMSD)`

Then load either:

- A TTTR file (e.g. `*.ptu`), or
- A TIFF image stack (e.g. `*.tif`, `*.tiff`).

The reader will:

1. For TIFF stacks
   - Read the image data through `chisurf.core.fio.image`.
   - Normalize the stack to shape `(n_frames, ny, nx)`.
   - Optionally select a single colour channel for multi-channel images.
2. For TTTR files
   - Load the TTTR container using `tttrlib.TTTR`.
   - Pass the TTTR data (and selected routing channels) to
     `tttrlib.CLSMImage` to reconstruct a confocal image stack.
   - Read the pixel and line durations from the file header when present.
3. Correlate the stack into a carpet `G(xi, psi, Delta)` — one spatial
   correlation map per frame lag — with options for:
   - ROI selection (`x_range`, `y_range`),
   - average subtraction mode (`subtract_average` = frame/stack),
   - the **maximum frame lag** (`max_frame_lag`), and
   - optional FFT centring of the zero lag (`fftshift`).
4. Build a ChiSurf `DataCurve` whose y-axis is the flattened carpet, with
   uncertainties from the standard error over the frame pairs averaged at each
   lag. The carpet, the lag grids and the scan timing are stored under
   `meta_data['ics']`.

## The setting that chooses the method

**Max frame lag Δ** is the only control that separates the named methods:

| Setting | What you get |
| --- | --- |
| `0` | the zero-lag slice only — a classic **RICS** map |
| `> 0` | the carpet extended along time, from which **STICS**, **TICS** and **iMSD** are all readable, and which the model fits jointly |

Cost grows linearly: each additional lag is another full correlation pass over
all frame pairs at that lag.

## Scan timing

The timing fields convert carpet lags into lag times through
`tau = |xi*t_pixel + psi*t_line + Delta*t_frame|`, so they set the physical
meaning of the whole measurement:

- **Pixel dur [µs]** and **Line dur [ms]** — leave both at `0` to read them from
  the TTTR header of each file; anything you enter overrides the header and is
  kept across reads, which is how a wrong or missing scanner tag is corrected.
  The values a read actually used are reported above the settings. Required for
  any RICS-region fit.
- **Frame dur [ms]** — only matters once `max_frame_lag > 0`. Leaving it at `0`
  estimates it as (lines per frame) × (line time), which is exact only for a
  scanner without inter-frame dead time.
- **Pixel size [nm]** — converts lags into distances.

## Typical workflow

1. Configure the reader (channel, ROI, average subtraction, max frame lag, scan
   timing).
2. Load a TTTR file or TIFF stack recorded with raster scanning.
3. Inspect the intensity image and the correlation carpet in the controller
   preview; with more than one frame lag the preview pages through Δ.
4. Add the **Image correlation** model. It opens as one-component diffusion;
   release `alpha`, `a_T`, `N_imm` or the velocities to add terms.
5. Fit and inspect the residuals. The 2D plot's Δ slider steps through the
   frame lags and its source selector switches between residual, data and model.
