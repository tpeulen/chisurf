(plugin-wizards)=
# Wizards

Hub that lists ChiSurf's guided wizards and embeds the selected one in a two-panel view.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `wizards` |
| Menu path | Main → Tools → **Wizards** |
| Categories | Main, Tools |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `wizards` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/wizards/`
- Manifest: {src}`chisurf/plugins/core/wizards/manifest.json`
