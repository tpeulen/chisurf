(plugin-fret_line)=
# FRET Line Generator

Compute static, dynamic, WLC, and mixture FRET lines for parameter ranges. Results are suitable for overlaying on smFRET 2D histograms in ndX.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fret_line` |
| Menu path | Spectroscopy → FRET → **FRET Line Generator** |
| Categories | FRET, Analysis |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `fret_line` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/fret_line/`
- Manifest: `chisurf/plugins/fret_line/manifest.json`
