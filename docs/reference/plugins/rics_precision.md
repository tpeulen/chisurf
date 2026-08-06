---
type: Plugin Reference
title: RICS-Precision
description: Predict how precisely a raster scan (RICS) will measure a diffusion coefficient, and find the dwell time that measures it best — from the intended settings alone, before the microscope time is spent.
resource: chisurf/plugins/calculator/rics_precision/
tags: [reference, plugins, rics-precision, main, tools]
anchor: plugin-rics_precision
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-rics_precision)=
# RICS-Precision

Predict how precisely a raster scan (RICS) will measure a diffusion coefficient, and find the dwell time that measures it best — from the intended settings alone, before the microscope time is spent.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `rics_precision` |
| Menu path | Main → Tools → **RICS-Precision** |
| Categories | Main, Tools |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `rics_precision` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Sample

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| D [µm²/s] | `diffusion_coefficient` | float |  | 1e-06 … 100000.0 | The diffusion coefficient you expect to measure. This is the awkward part of planning a scan: the best settings depend on the answer you do not have yet, so use a literature value or a guess and check how sensitive the prediction is to it. A free dye is a few hundred; a labelled protein a few tens; a membrane protein below one. |
| Molecules in view | `n_particles` | float |  | 0.01 … 1000000.0 | Number of fluorescent molecules in the illuminated region. Too few and the correlation is noisy; too many and its amplitude (which goes as 1/N) sinks into the background. |
| Brightness [kHz/molecule] | `brightness_khz` | float |  | 0.001 … 100000.0 | Photons per second from a single molecule at the centre of the focus. This is the dominant lever on precision after the number of frames — a dim label cannot be rescued by scanning cleverly. |

### Optics

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| w_r [µm] | `w_r` | float |  | 0.001 … 100.0 | Lateral beam waist. Measure it with the waist calibration rather than guessing: every predicted error scales with it. |
| w_z [µm] | `w_z` | float |  | 0.001 … 1000.0 | Axial beam waist. Only its ratio to w_r matters here. |
| Pixel size [nm] | `pixel_size_nm` | float |  | 1.0 … 100000.0 | Physical pixel size. It should sample the waist several times over — around 4 to 6 pixels across w_r — or the spatial shape of the correlation is undersampled. |
| Membrane (2-D) | `two_d` | bool |  |  | Use the 2-D geometry for a membrane or a surface, which has different shape factors from a 3-D focus. |

### Scan

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Pixel dwell [µs] | `pixel_time_us` | float |  | 0.01 … 100000.0 | The dwell time you plan to use. It is marked on the curve so you can see how far it sits from the optimum. |
| Line overhead × | `line_overhead` | float |  | 1.0 … 100.0 | How much longer a line takes than the sum of its pixels, from flyback and settling. 1.2 means 20 % overhead. The sweep scales the line time with the dwell, because a line cannot stay short as its pixels grow. |
| Pixels per line | `nx` | int |  | 8 … 4096 | Image width. A larger image averages more pixel pairs and so measures better, at the cost of a longer frame. |
| Lines per frame | `ny` | int |  | 8 … 4096 | Image height. |
| Frames | `n_images` | int |  | 1 … 100000 | Frames averaged. Precision improves as the square root of this, so halving the error costs four times the acquisition time. |

### Estimator

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Lags fitted | `n_lags` | int |  | 1 … 15 | Largest lag included on each axis. Cost grows as the fourth power of this, so raising it is expensive; the reference implementation uses 15. It must stay below half the smaller image dimension — a lag is averaged over the pixel pairs that realise it, and a small image holds too few. |
| Repeats | `n_repeats` | int |  | 5 … 2000 | Monte-Carlo realisations behind each point. The predicted error carries an uncertainty of roughly 1/sqrt(2N) itself — about 11 % at 40 — which is why the position of the minimum is only good to an order of magnitude. |
| Seed | `seed` | int |  | 0 … 1000000 | Random seed, so a quoted prediction can be reproduced. |

## Theory and workflow

- **Theory** — [Image correlation: RICS, STICS, TICS and iMSD are one method](/concepts/image_correlation.md), [Scan precision: choosing a dwell time before you measure](/concepts/scan_precision.md)
- **Workflow** — [Planning a scan: which dwell time measures D best?](/guides/45_scan_precision.md)

## Source

- Plugin package: `chisurf/plugins/calculator/rics_precision/`
- Manifest: {src}`chisurf/plugins/calculator/rics_precision/manifest.json`
- UI spec: {src}`chisurf/plugins/calculator/rics_precision/gui/precision.view.json`
