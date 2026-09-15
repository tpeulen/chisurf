---
type: Plugin Reference
title: Plugins
description: Plugin Manager for ChiSurf
resource: chisurf/plugins/core/plugin_manager/
tags: [reference, plugins, plugin-manager, setup]
anchor: plugin-plugin_manager
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-plugin_manager)=
# Plugins

Plugin Manager for ChiSurf

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `plugin_manager` |
| Menu path | Setup → **Plugins** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Installed plugins

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Show disabled plugins | `show_disabled` | bool |  |  | Include switched-off plugins in the table. Off, they are hidden entirely. |

### Selected plugin

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Disabled | `selected_disabled` | bool |  |  | Switch this plugin off. If other plugins require it, you are told which before the change sticks. |
| Show in main toolbar | `selected_in_toolbar` | bool |  |  | Pin this plugin to the main window toolbar. |
| Remember window state | `selected_statefulness` | choice |  | choices: `selected_statefulness_labels` | Whether this one plugin's window reopens where you left it. 'Plugin default' defers to its manifest and the global setting below. |
| Window state (all plugins) | `statefulness_mode` | choice |  | choices: `statefulness_mode_labels` | Whether plugin windows remember their size and position. 'Plugin default' lets each manifest decide. |

## Source

- Plugin package: `chisurf/plugins/core/plugin_manager/`
- Manifest: {src}`chisurf/plugins/core/plugin_manager/manifest.json`
- UI spec: {src}`chisurf/plugins/core/plugin_manager/gui/plugins.view.json`
