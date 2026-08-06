(plugin-lifetime_analysis)=
# Decay Analysis

Integrated fluorescence lifetime analysis tools with IRF estimation, MaxEnt MEM, Lazy Lifetime Analysis, microtime histograms, and VV/VH G-factor calibration.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `lifetime_analysis` |
| Menu path | Spectroscopy → **Decay Analysis** |
| Categories | Spectroscopy, Fluorescence decay |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `lifetime_analysis` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/fluorescence_decay/lifetime_analysis/`
- Manifest: {src}`chisurf/plugins/fluorescence_decay/lifetime_analysis/manifest.json`
