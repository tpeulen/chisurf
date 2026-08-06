---
type: Plugin Reference
title: Mean Micro-Time
description: Per-pixel mean micro-time (arrival time) maps from TTTR imaging data.
resource: chisurf/plugins/microscopy/img_pixel_micro_time/
tags: [reference, plugins, img-pixel-micro-time, imaging]
anchor: plugin-img_pixel_micro_time
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-img_pixel_micro_time)=
# Mean Micro-Time

Per-pixel mean micro-time (arrival time) maps from TTTR imaging data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_pixel_micro_time` |
| Menu path | Imaging → **Mean Micro-Time** |
| Categories | Imaging |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `img_pixel_micro_time` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TTTR file | `filename` | file |  |  | PTU/HT3 imaging file; CLSM markers are auto-detected from the header. |
| Min. photons | `n_ph_min` | int |  |  | Pixels with fewer photons than this are discriminated (set to 0); press Run to apply. |

## Theory and workflow

- **Theory** — [FLIM and the phasor approach](/concepts/imaging_flim_phasor.md)
- **Workflow** — [Confocal scan images (CLSM)](/guides/24_scan_images.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/img_pixel_micro_time/`
- Manifest: {src}`chisurf/plugins/microscopy/img_pixel_micro_time/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/img_pixel_micro_time/gui/micro_time.view.json`
