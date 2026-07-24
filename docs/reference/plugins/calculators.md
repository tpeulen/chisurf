(plugin-calculators)=
# Calculators

Hub that groups ChiSurf's FRET-line, FRET/homoFRET, FCS and phasor-plot calculators and embeds the selected one in a two-panel view.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `calculators` |
| Menu path | Main → Tools → **Calculators** |
| Categories | Tools |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `calculators` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/calculator/hub/`
- Manifest: `chisurf/plugins/calculator/hub/manifest.json`
