---
type: Plugin Reference
title: PSF Determination
description: 3D Gaussian PSF fitting and bead detection for confocal microscopy.
resource: chisurf/plugins/microscopy/psf_determination/
tags: [reference, plugins, psf-determination, imaging]
anchor: plugin-psf_determination
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-psf_determination)=
# PSF Determination

3D Gaussian PSF fitting and bead detection for confocal microscopy.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `psf_determination` |
| Menu path | Imaging → **PSF Determination** |
| Categories | Imaging |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `psf_determination` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### PSF parameters

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Pixel (nm) | `pixel_size_nm` | float |  | 1.0 … 1000.0 (step 1.0) | Lateral camera/scanner pixel size in nm; scales σx/σy to physical FWHM. |
| Z step (nm) | `z_step_nm` | float |  | 1.0 … 10000.0 (step 10.0) | Axial distance between z-slices in nm; scales σz to physical FWHM. |
| ROI xy (px) | `roi_xy` | int |  | 3 … 200 | Lateral ROI size (pixels) cut around a bead for the 3D Gaussian fit. |
| ROI z (sl) | `roi_z` | int |  | 3 … 200 | Axial ROI size (slices) cut around a bead for the 3D Gaussian fit. |

### Detection

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Px/frame | `pixels_per_frame` | int |  | 1 … 100000 | Expected bright pixels per frame; sets the adaptive quantile threshold for bead detection. |
| Min dist (px) | `min_distance` | float |  | 1.0 … 1000.0 (step 1.0) | Minimum lateral distance between accepted beads (pixels); rejects clustered candidates. |
| Min area (px) | `min_area` | int |  | 1 … 10000 | Smallest connected bright region that can be a bead. A bead covers several pixels; a single one is a hot camera pixel. Set to 1 to keep every speck. |

### Fit Results

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| results_text | `results_text` | text |  |  | Latest single-bead fit report or batch summary. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `psf_determination.fit.run` | yes | Fit 3D Gaussian PSF to a bead stack. |
| `psf_determination.contract.describe` | no | Return the RPC contract. |

## Theory and workflow

- **Theory** — [Deconvolution](/concepts/deconvolution.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/psf_determination/`
- Manifest: {src}`chisurf/plugins/microscopy/psf_determination/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/psf_determination/gui/psf.view.json`
