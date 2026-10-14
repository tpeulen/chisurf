---
type: Plugin Reference
title: Boarding Wizard
description: Startup onboarding wizard for first-run ChiSurf configuration.
resource: chisurf/plugins/core/boarding/
tags: [reference, plugins, boarding, help]
anchor: plugin-boarding
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-boarding)=
# Boarding Wizard

Startup onboarding wizard for first-run ChiSurf configuration.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `boarding` |
| Menu path | not in the menus (opened from a hub or another tool); display name Help → **Boarding Wizard** |
| Categories | Help |
| Version | 1.0.0 |
| Surfaces | emtk |
| State namespace | `boarding` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [The application shell: settings, interface, account, help and hubs](/concepts/application_shell.md)
- **Workflow** — [The Settings window: one list, every settings panel](/guides/97_settings_hub.md)

## Source

- Plugin package: `chisurf/plugins/core/boarding/`
- Manifest: {src}`chisurf/plugins/core/boarding/manifest.json`
- UI spec: {src}`chisurf/plugins/core/boarding/boarding.view.json`
- UI spec: {src}`chisurf/plugins/core/boarding/boarding_emtk.view.json`
