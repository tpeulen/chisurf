(plugin-burst_analysis)=
# Burst Analysis

Integrated burst workflow with burst selection, BVA, burst MLE, burst browser, and background estimation.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_analysis` |
| Menu path | Spectroscopy → **Burst Analysis** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `burst_analysis` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/burst/burst_analysis/`
- Manifest: `chisurf/plugins/burst/burst_analysis/manifest.json`
