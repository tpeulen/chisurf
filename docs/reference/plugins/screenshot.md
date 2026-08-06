---
type: Plugin Reference
title: Screenshot
description: A minimal plugin that captures a screenshot of the ChiSurf main window and copies it to the clipboard.
resource: chisurf/plugins/core/screenshot/
tags: [reference, plugins, screenshot]
anchor: plugin-screenshot
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-screenshot)=
# Screenshot

A minimal plugin that captures a screenshot of the ChiSurf main window and copies it to the clipboard.

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `screenshot` |
| Menu path | Main → Tools → **Screenshot** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/core/screenshot/`
