---
type: Plugin Reference
title: Menu Switch
description: This plugin provides a simple toggle to switch between the traditional menu bar and the modern ribbon interface in ChiSurf.
resource: chisurf/plugins/core/menu_switch/
tags: [reference, plugins, menu-switch]
anchor: plugin-menu_switch
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-menu_switch)=
# Menu Switch

This plugin provides a simple toggle to switch between the traditional menu bar and the modern ribbon interface in ChiSurf.

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `menu_switch` |
| Menu path | Setup → **Menu Switch** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/menu_switch/`
