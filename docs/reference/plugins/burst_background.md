(plugin-burst_background)=
# Burst Background Estimation

Estimate detector background rates from TTTR burst data.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_background` |
| Menu path | Spectroscopy → Single-Molecule → **Burst Background Estimation** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `burst_background` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| files | `files` | path_list |  |  |  |

## Source

- Plugin package: `chisurf/plugins/burst/burst_background/`
- Manifest: {src}`chisurf/plugins/burst/burst_background/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_background/gui/background.view.json`
