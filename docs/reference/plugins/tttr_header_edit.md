---
type: Plugin Reference
title: TTTR Header editor
description: 'View and edit the header tags of any TTTR file tttrlib reads (PTU, HT3, SPC, Photon-HDF5): change, add or remove tags and save the photons unchanged into a new PTU file, the only container that keeps arbitrary tags.'
resource: chisurf/plugins/tttr/tttr_header_edit/
tags: [reference, plugins, tttr-header-edit, file, data]
anchor: plugin-tttr_header_edit
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_header_edit)=
# TTTR Header editor

View and edit the header tags of any TTTR file tttrlib reads (PTU, HT3, SPC, Photon-HDF5): change, add or remove tags and save the photons unchanged into a new PTU file, the only container that keeps arbitrary tags.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_header_edit` |
| Menu path | File → Data → **TTTR Header editor** |
| Categories | File, Data |
| Version | 1.0.0 |
| Surfaces | emtk, script |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| json_text | `json_text` | text |  |  | Live JSON view of the full TTTR header with the edited tags. |

## Theory and workflow

- **Theory** — [File tools: operations on the container, not the measurement](/concepts/file_tools.md)
- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_header_edit/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_header_edit/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_header_edit/gui/header.view.json`
