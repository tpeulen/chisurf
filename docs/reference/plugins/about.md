---
type: Plugin Reference
title: About ChiSurf
description: ChiSurf About Plugin
resource: chisurf/plugins/core/about/
tags: [reference, plugins, about]
anchor: plugin-about
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-about)=
# About ChiSurf

ChiSurf About Plugin

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `about` |
| Menu path | Help → **About ChiSurf** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/about/`
