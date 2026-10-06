---
type: Plugin Reference
title: File tools
description: 'Everything that acts on a file rather than on the physics inside it: TTTR split/convert, packing and unpacking a .pto container, reading one back, time-window BIDs, BID→Analysis, and the TTTR header editor.'
resource: chisurf/plugins/tttr/filetools/
tags: [reference, plugins, filetools, file, data]
anchor: plugin-filetools
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-filetools)=
# File tools

Everything that acts on a file rather than on the physics inside it: TTTR split/convert, packing and unpacking a .pto container, reading one back, time-window BIDs, BID→Analysis, and the TTTR header editor.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `filetools` |
| Menu path | File → Data → **File tools** |
| Categories | File, Data |
| Version | 1.1.0 |
| Surfaces | emtk, gui |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md), [Intensity traces and file tools](/guides/74_intensity_traces_and_file_tools.md)

## Source

- Plugin package: `chisurf/plugins/tttr/filetools/`
- Manifest: {src}`chisurf/plugins/tttr/filetools/manifest.json`
