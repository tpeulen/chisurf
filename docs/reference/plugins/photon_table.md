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
| Menu path | not in the menus (opened from a hub or another tool); display name Tools → TTTR → **Photon Table** |
| Categories | Tools, TTTR |
| Version | 1.0.0 |
| Surfaces | emtk |
| State namespace | `photon_table` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| First record | `first_index` | int |  | 0 … 1000000000000 (step 1) | Index of the first record shown, counted within the filtered selection. A value past the end is moved back so that the page stays full. |
| Rows | `rows_per_page` | int |  | 1 … 20000 (step 1) | Rows shown at once (1 to 20000). Large pages are fine; the table only draws what fits the window. |
| Channel | `channel_filter` | choice |  | choices: `channel_labels` | Show only the records of one routing channel. 'All channels' keeps the file's order. Choosing a channel goes back to its first record. |
| Kind | `kind_filter` | choice |  | choices: `kind_labels` | Show every record, only the photons, only the marker records, or one kind of marker (pixel, line start, line stop, frame, other) the file holds. Works together with the channel filter; choosing a kind goes back to its first record. |

## Theory and workflow

- **Theory** — [The photon container: one measurement, one file](/concepts/photon_container.md)
- **Workflow** — [Reading the photons of a TTTR file](/guides/108_photon_table.md), [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/photon_table/`
- Manifest: {src}`chisurf/plugins/tttr/photon_table/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/photon_table/gui/photon_table_emtk.view.json`
