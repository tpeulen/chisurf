(plugin-img_pixel_nb)=
# Number & Brightness

Per-pixel Number (N) and Brightness (B) maps from TTTR imaging data.

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

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TTTR file | `filename` | file |  |  | PTU/HT3 imaging file; CLSM markers are auto-detected from the header. |

## Theory and workflow

- **Theory** — [Photon-counting histogram (PCH) and FIDA](/concepts/pch_fida.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/img_pixel_nb/`
- Manifest: {src}`chisurf/plugins/microscopy/img_pixel_nb/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/img_pixel_nb/gui/nb.view.json`
