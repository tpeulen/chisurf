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

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/plugin_manager/`
- Manifest: {src}`chisurf/plugins/core/plugin_manager/manifest.json`
