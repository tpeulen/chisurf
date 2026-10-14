---
type: Plugin Reference
title: Split/Convert
description: Split a TTTR file into files of a fixed photon count, convert it to another container format, or bin its micro-times; one file or a batch.
resource: chisurf/plugins/tttr/tttr_splitter/
tags: [reference, plugins, tttr-splitter, file, data]
anchor: plugin-tttr_splitter
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_splitter)=
# Split/Convert

Split a TTTR file into files of a fixed photon count, convert it to another container format, or bin its micro-times; one file or a batch.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_splitter` |
| Menu path | File → Data → **Split/Convert** |
| Categories | File, Data |
| Version | 1.0.0 |
| Surfaces | emtk, script |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Input / Output

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Input format | `input_format` | choice |  | choices: `input_format_options` | Force an input container type, or Auto to detect it from the file. |
| Output format | `output_format` | choice |  | choices: `output_format_options` | Container format written to disk; differs from input ⇒ transcode. |

### Split options

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Photons/file | `photons_per_file_k` | int |  | 100 … 999999999 (step 100) | Photons per output file (×1000) when 'Split into files' is on. |
| µ-time binning | `microtime_binning` | choice |  | choices: 1, 2, 4, 8, 16 | Micro-time binning factor (clamped to ≥8 for SPC containers). |

### Batch

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| batch_files | `batch_files` | path_list |  |  | Files queued for the batch run. |
| Use file's parent as output folder | `batch_use_parent` | bool |  |  | Write each result next to its source file. |

## Theory and workflow

- **Theory** — [File tools: operations on the container, not the measurement](/concepts/file_tools.md)
- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_splitter/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_splitter/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_splitter/gui/splitter.view.json`
