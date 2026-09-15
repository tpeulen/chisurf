---
type: Plugin Reference
title: Split/Convert
description: 'TTTR Split / Convert plugin. This plugin provides functionality for splitting large TTTR (Time-Tagged Time-Resolved) files, particularly those in the PicoQuant PTU format, into smaller segments. This is useful for: 1. Breaking down large datasets into manageable chunks 2. Extracting specific time segments from long measurements 3. Creating subsets of data for parallel processing 4. Reducing memory requirements for analysis The plugin features: - Support for various TTTR file formats - Configurable splitting parameters (photons per file, time segments) - Options for micro-time binning to reduce file size - Ability to reset macro-times in the output files - Selection of output container formats (file format conversion) This tool is particularly valuable for handling large datasets from long-duration single-molecule or imaging experiments, making them more manageable for subsequent analysis.'
resource: chisurf/plugins/tttr/tttr_splitter/
tags: [reference, plugins, tttr-splitter, tttr, editor]
anchor: plugin-tttr_splitter
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_splitter)=
# Split/Convert

TTTR Split / Convert plugin.  This plugin provides functionality for splitting large TTTR (Time-Tagged Time-Resolved) files, particularly those in the PicoQuant PTU format, into smaller segments. This is useful for:  1. Breaking down large datasets into manageable chunks 2. Extracting specific time segments from long measurements 3. Creating subsets of data for parallel processing 4. Reducing memory requirements for analysis  The plugin features: - Support for various TTTR file formats - Configurable splitting parameters (photons per file, time segments) - Options for micro-time binning to reduce file size - Ability to reset macro-times in the output files - Selection of output container formats (file format conversion)  This tool is particularly valuable for handling large datasets from long-duration single-molecule or imaging experiments, making them more manageable for subsequent analysis.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_splitter` |
| Menu path | TTTR → Editor → **Split/Convert** |
| Categories | TTTR, Editor |
| Version | 1.0.0 |
| Surfaces | script |

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
| batch_files | `batch_files` | path_list |  |  |  |
| Use file's parent as output folder | `batch_use_parent` | bool |  |  |  |

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_splitter/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_splitter/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_splitter/gui/splitter.view.json`
