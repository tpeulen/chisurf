(plugin-img_pixel_intensity)=
# Intensity

Per-pixel intensity map; creates the standard imaging HDF5 (with source back-reference) that N&B / phasor / MLE enrich.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_pixel_intensity` |
| Menu path | Imaging → **Intensity** |
| Categories | Imaging |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `img_pixel_intensity` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TTTR file | `filename` | file |  |  | PTU/HT3 imaging file (or drop one onto the window); CLSM markers auto-detected. |

## Theory and workflow

- **Workflow** — [Confocal scan images (CLSM)](/guides/24_scan_images.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/img_pixel_intensity/`
- Manifest: {src}`chisurf/plugins/microscopy/img_pixel_intensity/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/img_pixel_intensity/gui/intensity.view.json`
