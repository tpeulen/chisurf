---
type: Plugin Reference
title: Styles
description: Style Manager Plugin for ChiSurf
resource: chisurf/plugins/core/style_manager/
tags: [reference, plugins, style-manager, setup]
anchor: plugin-style_manager
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-style_manager)=
# Styles

Style Manager Plugin for ChiSurf

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `style_manager` |
| Menu path | Setup → **Styles** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [The application shell: settings, interface, account, help and hubs](/concepts/application_shell.md)
- **Workflow** — [The Settings window: one list, every settings panel](/guides/97_settings_hub.md)

## Source

- Plugin package: `chisurf/plugins/core/style_manager/`
- Manifest: {src}`chisurf/plugins/core/style_manager/manifest.json`
- UI spec: {src}`chisurf/plugins/core/style_manager/gui/app.view.json`
