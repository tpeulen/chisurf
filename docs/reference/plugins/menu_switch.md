---
type: Plugin Reference
title: Menu Switch
description: Menu Switch Switches the open ChiSurf main window between the traditional menu bar and the ribbon, without a restart. The choice is saved and restored at the next start. Menu Switch opens no window of its own.
resource: chisurf/plugins/core/menu_switch/
tags: [reference, plugins, menu-switch, setup]
anchor: plugin-menu_switch
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-menu_switch)=
# Menu Switch

Menu Switch  Switches the open ChiSurf main window between the traditional menu bar and the ribbon, without a restart. The choice is saved and restored at the next start. Menu Switch opens no window of its own.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `menu_switch` |
| Menu path | Setup → **Menu Switch** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | action |

## Parameters

This plugin opens no window and has no parameters: it is an action on the ChiSurf host. Switch the current ChiSurf window between the menu bar and ribbon, and save the interface preference. It is only available from an open ChiSurf main window.

## Source

- Plugin package: `chisurf/plugins/core/menu_switch/`
- Manifest: {src}`chisurf/plugins/core/menu_switch/manifest.json`
