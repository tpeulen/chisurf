(plugin-tttr_count_rate_analysis)=
# Count Rate Analysis

Count rates per detector channel across many TTTR files, with mean/std and a per-file plot.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_count_rate_analysis` |
| Menu path | Tools → TTTR → **Count Rate Analysis** |
| Categories | TTTR, Analysis |
| Version | 2.0.0 |
| Surfaces | cli, gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_count_rate_analysis/`
- Manifest: `chisurf/plugins/tttr/tttr_count_rate_analysis/manifest.json`
- UI spec: `chisurf/plugins/tttr/tttr_count_rate_analysis/gui/count_rate.view.json`
