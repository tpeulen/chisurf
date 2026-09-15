---
type: Plugin Reference
title: TTTR Header editor
description: 'TTTR Header Editor plugin. This plugin provides a tool for viewing and editing header tags of any time-tagged time-resolved (TTTR) file that :mod:tttrlib can read — PicoQuant PTU and HT3, Becker&Hickl SPC, and Photon-HDF5. tttrlib normalises every container into the same tag list, so the editor is format-agnostic on read. It allows users to: 1. Open and inspect any supported TTTR file (auto-detected container) 2. View all header tags and their values in a tabular format 3. Edit existing tag values 4. Add new custom tags to the header 5. Remove unwanted tags 6. Save the edited header to a new PTU file The plugin features an intuitive table-based interface that displays tag names, types, values, and indices. Users can modify any field and see the changes in real-time. A JSON view is also available to see the complete header structure. This tool is particularly useful for: - Correcting metadata in experimental TTTR files - Adding missing information to headers - Preparing files for specialized analysis - Troubleshooting issues with file metadata - Educational purposes to understand TTTR file structure The photon events of the source file are copied verbatim into the saved file. Output is always a PTU container, because it is the only tttrlib container that persists arbitrary edited header tags without loss.'
resource: chisurf/plugins/tttr/tttr_header_edit/
tags: [reference, plugins, tttr-header-edit, tttr, editor]
anchor: plugin-tttr_header_edit
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_header_edit)=
# TTTR Header editor

TTTR Header Editor plugin.  This plugin provides a tool for viewing and editing header tags of any time-tagged time-resolved (TTTR) file that :mod:`tttrlib` can read — PicoQuant PTU and HT3, Becker&Hickl SPC, and Photon-HDF5. ``tttrlib`` normalises every container into the same tag list, so the editor is format-agnostic on read. It allows users to: 1. Open and inspect any supported TTTR file (auto-detected container) 2. View all header tags and their values in a tabular format 3. Edit existing tag values 4. Add new custom tags to the header 5. Remove unwanted tags 6. Save the edited header to a new PTU file  The plugin features an intuitive table-based interface that displays tag names, types, values, and indices. Users can modify any field and see the changes in real-time. A JSON view is also available to see the complete header structure.  This tool is particularly useful for: - Correcting metadata in experimental TTTR files - Adding missing information to headers - Preparing files for specialized analysis - Troubleshooting issues with file metadata - Educational purposes to understand TTTR file structure  The photon events of the source file are copied verbatim into the saved file. Output is always a PTU container, because it is the only ``tttrlib`` container that persists arbitrary edited header tags without loss.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_header_edit` |
| Menu path | TTTR → Editor → **TTTR Header editor** |
| Categories | TTTR, Editor |
| Version | 1.0.0 |
| Surfaces | script |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| json_text | `json_text` | text |  |  | Live JSON view of the full TTTR header with the edited tags. |

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_header_edit/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_header_edit/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_header_edit/gui/header.view.json`
