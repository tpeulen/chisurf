(plugin-burst_browser)=
# Burst Browser

Inspect burstwise analysis tables and plots.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_browser` |
| Menu path | Spectroscopy → Single-Molecule → **Burst Browser** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `burst_browser` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/burst/burst_browser/`
- Manifest: {src}`chisurf/plugins/burst/burst_browser/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_browser/gui/burst_browser.view.json`
