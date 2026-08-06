---
type: Plugin Reference
title: FCS Converter
description: FCS conversion plugin.
resource: chisurf/plugins/fcs/fcs_convert/
tags: [reference, plugins, fcs-convert]
anchor: plugin-fcs_convert
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_convert)=
# FCS Converter

FCS conversion plugin.

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_convert` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **FCS Converter** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_convert/`
