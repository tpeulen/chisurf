---
type: Plugin Reference
title: BID→Analysis
description: BID → Analysis Converter
resource: chisurf/plugins/burst/bid_to_analysis/
tags: [reference, plugins, bid-to-analysis]
anchor: plugin-bid_to_analysis
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-bid_to_analysis)=
# BID→Analysis

BID → Analysis Converter

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `bid_to_analysis` |
| Menu path | Tools → Converter → **BID→Analysis** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [Exporting burst data](/guides/34_exporting_burst_data.md)

## Source

- Plugin package: `chisurf/plugins/burst/bid_to_analysis/`
