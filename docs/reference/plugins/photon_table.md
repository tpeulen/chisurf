---
type: Plugin Reference
title: Photon Table
description: 'Inspect the photons of a TTTR file in a table: routing channel, micro-time and macro-time, one row per photon, with navigation and a channel filter.'
resource: chisurf/plugins/tttr/photon_table/
tags: [reference, plugins, photon-table, tools, tttr]
anchor: plugin-photon_table
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-photon_table)=
# Photon Table

Inspect the photons of a TTTR file in a table: routing channel, micro-time and macro-time, one row per photon, with navigation and a channel filter.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `photon_table` |
| Menu path | Tools → TTTR → **Photon Table** |
| Categories | Tools, TTTR |
| Version | 1.0.0 |
| Surfaces | emtk, gui |
| State namespace | `photon_table` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| First photon | `first_index` | int |  | 0 … 1000000000000 (step 1) | Index of the first photon shown, counted within the filtered selection. A value past the end is moved back so that the page stays full. |
| Rows | `rows_per_page` | int |  | 1 … 20000 (step 1) | Rows shown at once (1 to 20000). Large pages are fine; the table only draws what fits the window. |
| Channel | `channel_filter` | choice |  | choices: `channel_labels` | Show only the photons of one routing channel. 'All channels' keeps the file's order. Choosing a channel goes back to its first photon. |

## Source

- Plugin package: `chisurf/plugins/tttr/photon_table/`
- Manifest: {src}`chisurf/plugins/tttr/photon_table/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/photon_table/gui/photon_table_emtk.view.json`
