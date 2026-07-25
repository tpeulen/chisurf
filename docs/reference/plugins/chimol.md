(plugin-chimol)=
# ChiMOL

Molecular structure viewer and protein analysis plugin for ChiSurf.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `chimol` |
| Menu path | Structure → Structure → **ChiMOL** |
| Categories | Structure, Molecular Viewer |
| Version | 0.2.0 |
| Surfaces | gui |
| State namespace | `chimol` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/chimol/`
- Manifest: `chisurf/plugins/chimol/manifest.json`
