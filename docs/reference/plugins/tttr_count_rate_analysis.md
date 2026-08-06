---
type: Plugin Reference
title: Count Rate Analysis
description: Count rates per detector channel across many TTTR files, with mean/std and a per-file plot.
resource: chisurf/plugins/tttr/tttr_count_rate_analysis/
tags: [reference, plugins, tttr-count-rate-analysis, tools, tttr, analysis]
anchor: plugin-tttr_count_rate_analysis
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_count_rate_analysis)=
# Count Rate Analysis

Count rates per detector channel across many TTTR files, with mean/std and a per-file plot.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_count_rate_analysis` |
| Menu path | Tools → TTTR → **Count Rate Analysis** |
| Categories | Tools, TTTR, Analysis |
| Version | 2.0.0 |
| Surfaces | cli, gui |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| files | `files` | path_list |  |  |  |

## Theory and workflow

- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_count_rate_analysis/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_count_rate_analysis/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_count_rate_analysis/gui/count_rate.view.json`
