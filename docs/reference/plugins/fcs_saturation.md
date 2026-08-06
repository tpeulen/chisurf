(plugin-fcs_saturation)=
# FCS Saturation

FCS Saturation Calculator for arbitrary multi-state kinetic schemes (including Cy5).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_saturation` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **FCS Saturation** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fcs_saturation.compute` | no | Compute unperturbed and saturated FCS curves for arbitrary kinetic scheme. |

## Source

- Plugin package: `chisurf/plugins/calculator/fcs_saturation_calc/`
- Manifest: {src}`chisurf/plugins/calculator/fcs_saturation_calc/manifest.json`
