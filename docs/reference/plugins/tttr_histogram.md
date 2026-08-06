---
type: Plugin Reference
title: Generate Decay
description: TTTR Histogram (Generate Decay)
resource: chisurf/plugins/tttr/tttr_histogram/
tags: [reference, plugins, tttr-histogram]
anchor: plugin-tttr_histogram
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_histogram)=
# Generate Decay

TTTR Histogram (Generate Decay)

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_histogram` |
| Menu path | TTTR → **Generate Decay** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_histogram/`
