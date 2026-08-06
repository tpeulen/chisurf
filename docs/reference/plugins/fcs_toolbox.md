---
type: Plugin Reference
title: FCS
description: Unified FCS plugin — a meta tool hosting the FCS workflow behind a rail.
resource: chisurf/plugins/fcs/fcs_toolbox/
tags: [reference, plugins, fcs-toolbox]
anchor: plugin-fcs_toolbox
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_toolbox)=
# FCS

Unified **FCS** plugin — a meta tool hosting the FCS workflow behind a rail.

:::{note}
This plugin declares itself in code rather than in a `manifest.json`, so the identity below is what the plugin loader reads from the module and there is no declared RPC surface to list.
:::

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_toolbox` |
| Menu path | Spectroscopy → **FCS** |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_toolbox/`
