---
type: Plugin Reference
title: Correlate
description: This plugin provides a graphical interface for calculating correlation functions from Time-Tagged Time-Resolved (TTTR) data.
resource: chisurf/plugins/tttr/tttr_correlate/
tags: [reference, plugins, tttr-correlate]
anchor: plugin-tttr_correlate
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_correlate)=
# Correlate

This plugin provides a graphical interface for calculating correlation functions from Time-Tagged Time-Resolved (TTTR) data.

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_correlate` |
| Menu path | TTTR → **Correlate** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_correlate/`
