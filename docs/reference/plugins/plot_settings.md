---
type: Plugin Reference
title: Plots
description: Configure plot appearance, colors, and rendering backend
resource: chisurf/plugins/core/plot_settings/
tags: [reference, plugins, plot-settings, setup]
anchor: plugin-plot_settings
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-plot_settings)=
# Plots

Configure plot appearance, colors, and rendering backend

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `plot_settings` |
| Menu path | Setup → **Plots** |
| Categories | Setup |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/plot_settings/`
- Manifest: {src}`chisurf/plugins/core/plot_settings/manifest.json`
