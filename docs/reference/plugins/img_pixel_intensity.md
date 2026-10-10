---
type: Plugin Reference
title: Intensity
description: Per-pixel intensity map; creates the standard imaging HDF5 (with source back-reference) that N&B / phasor / MLE enrich.
resource: chisurf/plugins/microscopy/img_pixel_intensity/
tags: [reference, plugins, img-pixel-intensity, spectroscopy, imaging]
anchor: plugin-img_pixel_intensity
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-img_pixel_intensity)=
# Intensity

Per-pixel intensity map; creates the standard imaging HDF5 (with source back-reference) that N&B / phasor / MLE enrich.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_pixel_intensity` |
| Menu path | Spectroscopy → Imaging → **Intensity** |
| Categories | Spectroscopy, Imaging |
| Version | 1.0.0 |
| Surfaces | cli, emtk |
| State namespace | `img_pixel_intensity` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Controls

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TTTR file | `filename` | file |  |  | PTU/HT3 imaging file (or drop one onto the window); CLSM markers auto-detected. |

### Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TTTR file | `filename` | str |  |  | PTU/HT3 imaging file with line and frame markers (or drop one onto the window: it is loaded and run). The scanner geometry is read from its header. Press Enter to select a typed path. |
| Detector window | `display_window` | choice |  | choices: `window_names` | The detector window shown in the maps. Every window is computed and written; this only chooses which one is displayed. The windows come from the Detectors tab (or the Imaging Tools setup step); without any, the channel-0 window is used. |

## Theory and workflow

- **Workflow** — [Confocal scan images (CLSM)](/guides/24_scan_images.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/img_pixel_intensity/`
- Manifest: {src}`chisurf/plugins/microscopy/img_pixel_intensity/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/img_pixel_intensity/gui/intensity.view.json`
- UI spec: {src}`chisurf/plugins/microscopy/img_pixel_intensity/gui/intensity_emtk.view.json`
