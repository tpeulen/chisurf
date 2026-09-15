---
type: Plugin Reference
title: PTO Inspector
description: 'Inspect a .pto photon container: every object in it, the provenance graph that says how each came to be, the payload as a table or a curve, and the settings that are the recipe. Double-click a step to open the tool that performs it.'
resource: chisurf/plugins/core/pto_inspector/
tags: [reference, plugins, pto-inspector, tttr]
anchor: plugin-pto_inspector
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-pto_inspector)=
# PTO Inspector

Inspect a .pto photon container: every object in it, the provenance graph that says how each came to be, the payload as a table or a curve, and the settings that are the recipe. Double-click a step to open the tool that performs it.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `pto_inspector` |
| Menu path | TTTR → **PTO Inspector** |
| Categories | TTTR |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `pto_inspector` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Container | `filename` | data_source |  |  | The .pto to inspect — one measurement in one file: the instrument data verbatim, and every result computed from it beside it. Dropping a vendor photon file offers to pack it into a container first. |

## Source

- Plugin package: `chisurf/plugins/core/pto_inspector/`
- Manifest: {src}`chisurf/plugins/core/pto_inspector/manifest.json`
- UI spec: {src}`chisurf/plugins/core/pto_inspector/gui/pto.view.json`
