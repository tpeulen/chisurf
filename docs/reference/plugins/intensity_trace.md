---
type: Plugin Reference
title: Intensity trace
description: Intensity Trace Analysis for Single-Molecule Data
resource: chisurf/plugins/tttr/intensity_trace/
tags: [reference, plugins, intensity-trace]
anchor: plugin-intensity_trace
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-intensity_trace)=
# Intensity trace

Intensity Trace Analysis for Single-Molecule Data

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `intensity_trace` |
| Menu path | Spectroscopy → Single-Molecule → **Intensity trace** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/tttr/intensity_trace/`
