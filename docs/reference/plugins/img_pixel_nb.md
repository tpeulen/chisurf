---
type: Plugin Reference
title: Number & Brightness
description: 'Per-pixel Number & Brightness from TTTR imaging stacks: apparent B and N, molecular brightness and number, cross N&B, analog-detector calibration, bleaching detrending, and gating a brightness population back onto the image.'
resource: chisurf/plugins/microscopy/img_pixel_nb/
tags: [reference, plugins, img-pixel-nb, imaging]
anchor: plugin-img_pixel_nb
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-img_pixel_nb)=
# Number & Brightness

Per-pixel Number & Brightness from TTTR imaging stacks: apparent B and N, molecular brightness and number, cross N&B, analog-detector calibration, bleaching detrending, and gating a brightness population back onto the image.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_pixel_nb` |
| Menu path | Imaging → **Number & Brightness** |
| Categories | Imaging |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `img_pixel_nb` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TTTR file | `filename` | file |  |  | Confocal photon-stream file (PTU/HT3/…) with line and frame markers; N&B needs many frames of the same field. The step-0 detector setup decides which windows are analysed. |

### Stack corrections

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Subtract | `subtract` | choice |  | choices: none, frame_mean, pixel_mean, moving_average | Removed from every frame before the moments are taken: the frame mean (whole-frame intensity changes), the pixel mean over frames (immobile structure) or a sliding box average (slow drifts and immobile structure together). The box is set below. |
| Add back | `add` | choice |  | choices: none, total_mean, frame_mean, pixel_mean, moving_average | Added back after subtracting. B = σ²/⟨k⟩ divides by the mean, so a subtraction must be followed by adding a mean back — the total mean or the pixel mean — or B loses its meaning. |
| Box (px) | `box_pixels` | int |  | 1 … 256 | Lateral edge of the moving-average box (both axes). An even box is centred one pixel early, as the reference implementation does. |
| Box (frames) | `box_frames` | int |  | 1 … 10000 | Temporal length of the moving-average box. It must be long compared with the number fluctuations you want to keep, or the subtraction removes the signal N&B measures. |
| Background | `background` | float |  |  | Constant counts per pixel dwell subtracted at the end (dark counts, scattered light). |
| Detrend segments | `detrend_segments` | int |  | 0 … 1000 | Bleaching correction: fit a straight line to every pixel within each of this many time segments, subtract it and add the pixel mean back. 0 switches it off. A bleaching decay inflates σ² and therefore B; several short lines follow the decay where one cannot. |

### Detector

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Dead time (ns) | `dead_time_ns` | float |  | 0.0 … 1000000.0 | Detector dead time. Counts are corrected as k/(1 − k·τ/T) before the moments; it needs the pixel dwell T below. 0 switches the correction off. |
| Pixel dwell (µs) | `pixel_dwell_us` | float |  | 0.0 … 1000000.0 | Time the beam spends on one pixel; only used by the dead-time correction. |
| Gain S | `gain` | float |  | 0.0 … | Analog detectors only: counts per photon, from a static-gradient calibration (toolbar: Calibrate analog). 1 for a photon-counting detector. |
| Offset | `offset` | float |  |  | Analog detectors only: the signal of zero photons, from the same calibration. 0 for a photon-counting detector. |
| Read variance σ₀² | `read_variance` | float |  | 0.0 … | Analog detectors only: variance of the dark signal (measure it with the shutter closed). 0 for a photon-counting detector. |

### Estimator

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Shape factor γ | `gamma` | float |  | 0.01 … 10.0 | Observation-volume shape factor. ε is divided and n multiplied by γ. 1 reports ε and n as Digman et al. define them; 0.3536 (1/√8, 3-D Gaussian) gives the γ-corrected values of the reference implementation. |
| Moment smoothing | `smoothing` | choice |  | choices: none, average, disk, gaussian | Smooth the mean and standard-deviation maps before forming B and N: a box of Radius pixels, a disk of radius Radius−1, or a Gaussian of σ = Radius/2. Trades resolution for a less noisy brightness map. |
| Radius | `radius` | float |  | 0.0 … 50.0 | Size of the moment smoothing. 1 or less switches the smoothing off. |
| Median filter (ε, n) | `median` | bool |  |  | Pass the ε and n maps through a 3×3 median filter, which removes single hot pixels without blurring edges. |

### Parameter plane / gates

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Plane x | `plane_x` | choice |  | choices: `plane_axis_names` | Horizontal axis of the parameter plane. Intensity ⟨k⟩ against brightness is the classic N&B plot: at equal intensity, monomers and oligomers separate by brightness. |
| Plane y | `plane_y` | choice |  | choices: `plane_axis_names` | Vertical axis of the parameter plane (mean, B, N, epsilon or n). |
| Bins | `plane_bins` | int |  | 8 … 512 | Bins per axis of the parameter-plane histogram. |
| Log counts | `log_histogram` | bool |  |  | Show the parameter-plane histogram on a logarithmic count scale, so a small population stays visible next to the dominant one. |
| Gate regions | `gates` | region_list |  |  | Regions drawn on the parameter plane. The pixels whose (x, y) fall inside are selected and shown in the Gated pixels map — a brightness population, back on the image. Tick to include, ~ for everything outside. |

### Cross N&B

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Cross with | `cross_window` | choice |  | choices: `cross_window_names` | Second detector window for cross N&B with the displayed one. B_cross = cov/√(⟨a⟩⟨b⟩) has no −1: shot noise is uncorrelated between detectors, so B_cross ≈ 0 means the two labels move independently and B_cross > 0 that they move together. |

## Theory and workflow

- **Theory** — [Photon-counting histogram (PCH) and FIDA](/concepts/pch_fida.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/img_pixel_nb/`
- Manifest: {src}`chisurf/plugins/microscopy/img_pixel_nb/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/img_pixel_nb/gui/nb.view.json`
