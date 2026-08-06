---
type: Plugin Reference
title: Phasor-FLIM
description: Per-pixel phasor (g, s) maps and phasor plot from TTTR imaging data.
resource: chisurf/plugins/microscopy/img_pixel_phasor/
tags: [reference, plugins, img-pixel-phasor, imaging, phasor-flim]
anchor: plugin-img_pixel_phasor
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-img_pixel_phasor)=
# Phasor-FLIM

Per-pixel phasor (g, s) maps and phasor plot from TTTR imaging data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_pixel_phasor` |
| Menu path | Imaging → **Phasor-FLIM** |
| Categories | Imaging, Phasor-FLIM |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `img_pixel_phasor` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TTTR file | `filename` | file |  |  | PTU/HT3 imaging file; CLSM markers auto-detected. |
| Min photons | `n_ph_min` | int |  | 1 … 10000 | Minimum photons per pixel for a valid phasor. |
| Frequency (MHz, -1=auto) | `frequency` | float |  | -1.0 … 1000.0 (step 1.0) | Modulation frequency; -1 auto-derives from the TTTR header. |
| Phasor cursors | `cursors` | region_list |  |  | Cursors on the (g, s) plane. Draw an ellipse round a lifetime cluster, a polygon round one that is neither round nor elliptical, or several combined; ~ selects everything outside. The Selected dock shows the pixels they pick out. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `phasor.describe` | no | Return phasor toolkit capabilities and defaults (frequency, harmonic, overlay sets, filters). |
| `phasor.apparent_lifetime` | no | Apparent phase (tau_phi) and modulation (tau_m) lifetimes from g, s maps. |
| `phasor.filter` | no | NaN-safe median or gaussian filtering of g, s phasor maps. |
| `phasor.component_fraction` | no | Fraction of component 1 by projection onto the two-component line. |
| `phasor.unmix` | no | Non-negative, sum-to-one fractions for N >= 2 component phasors. |
| `phasor.cursor_mask` | no | Boolean mask of the pixels a phasor cursor selects (circle, ellipse, or any region). |
| `phasor.pseudo_color` | no | Colorize a stack of boolean masks into an RGB label image. |
| `phasor.overlays` | no | Reference-geometry polylines (semicircle, lifetime grid/ticks, FRET, component line). |

## Theory and workflow

- **Theory** — [FLIM and the phasor approach](/concepts/imaging_flim_phasor.md)
- **Workflow** — [Confocal scan images (CLSM)](/guides/24_scan_images.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/img_pixel_phasor/`
- Manifest: {src}`chisurf/plugins/microscopy/img_pixel_phasor/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/img_pixel_phasor/gui/phasor.view.json`
