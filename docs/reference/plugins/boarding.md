(plugin-boarding)=
# Boarding Wizard

Startup onboarding wizard for first-run ChiSurf configuration.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `boarding` |
| Menu path | Help → **Boarding Wizard** |
| Categories | Help |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `boarding` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/boarding/`
- Manifest: {src}`chisurf/plugins/core/boarding/manifest.json`
- UI spec: {src}`chisurf/plugins/core/boarding/boarding.view.json`
