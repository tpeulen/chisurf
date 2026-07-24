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

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/burst/burst_background/`
- Manifest: `chisurf/plugins/burst/burst_background/manifest.json`
- UI spec: `chisurf/plugins/burst/burst_background/gui/background.view.json`
