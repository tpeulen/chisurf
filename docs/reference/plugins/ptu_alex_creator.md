---
type: Plugin Reference
title: ALEX Creator
description: Convert ALEX macro-time modulation into micro-time (single, batch or merged), for PIE-style analysis of .sm and other TTTR files.
resource: chisurf/plugins/tttr/ptu_alex_creator/
tags: [reference, plugins, ptu-alex-creator, tools, converter, tttr]
anchor: plugin-ptu_alex_creator
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-ptu_alex_creator)=
# ALEX Creator

Convert ALEX macro-time modulation into micro-time (single, batch or merged), for PIE-style analysis of .sm and other TTTR files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `ptu_alex_creator` |
| Menu path | Tools → Converter → **ALEX Creator** |
| Categories | Tools, Converter, TTTR |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Formats

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Input | `input_format` | choice |  | choices: `input_format_options` | Force the input container type, or Auto to detect it from the file. |
| Output | `output_format` | choice |  | choices: `output_format_options` | Container format written when saving (differs from input ⇒ transcode). |

### ALEX modulation

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Period | `alex_period` | int |  | 1 … 1000000 (step 100) | ALEX alternation period (macro-time units) mapped onto micro-time. |
| Shift | `period_shift` | int |  | -1000000 … 1000000 (step 1) | Phase shift of the ALEX period before the macro→micro mapping. |

### Batch

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Mode | `batch_mode` | choice |  | choices: convert, merge | Convert every file to its own ALEX output, or merge them all into one. |
| batch_files | `batch_files` | path_list |  |  |  |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `alex.convert` | yes | Convert one ALEX file per input to micro-time. |
| `alex.merge` | yes | Merge several ALEX files into a single micro-time file. |
| `alex.histogram` | no | Return the ALEX micro-time histogram of a file. |
| `alex.contract.describe` | no | Describe the ALEX Creator workflow contract. |

## Theory and workflow

- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/ptu_alex_creator/`
- Manifest: {src}`chisurf/plugins/tttr/ptu_alex_creator/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/ptu_alex_creator/gui/alex.view.json`
