---
type: Plugin Reference
title: Count Rate Analysis
description: Count rates per detector channel across many TTTR files, with mean/std and a per-file plot.
resource: chisurf/plugins/tttr/tttr_count_rate_analysis/
tags: [reference, plugins, tttr-count-rate-analysis, tools, photon-data, tttr, analysis]
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
| Menu path | Tools → Photon data → **Count Rate Analysis** |
| Categories | Tools, Photon data, TTTR, Analysis |
| Version | 2.0.0 |
| Surfaces | cli, emtk |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| files | `files` | path_list |  |  | TTTR files queued for the analysis. |

## Theory and workflow

- **Theory** — [Intensity traces: counting photons in time bins](/concepts/intensity_traces.md)
- **Workflow** — [The photon-data tools and count rates (Tools › Photon data)](/guides/101_photon_data_tools.md), [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_count_rate_analysis/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_count_rate_analysis/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_count_rate_analysis/gui/count_rate.view.json`
