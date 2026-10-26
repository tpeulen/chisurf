---
type: Plugin Reference
title: TTTR Inspector
description: 'Inspect any TTTR file tttrlib reads (PTU, HT3, SPC, Photon-HDF5): the photon table -- first events with routing channel, macro and micro time -- and the header tags as an editable table. Edited headers save into a new PTU file, the only container that keeps arbitrary tags, with the photons copied unchanged.'
resource: chisurf/plugins/tttr/tttr_header_edit/
tags: [reference, plugins, tttr-header-edit, file, data]
anchor: plugin-tttr_header_edit
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_header_edit)=
# TTTR Inspector

Inspect any TTTR file tttrlib reads (PTU, HT3, SPC, Photon-HDF5): the photon table -- first events with routing channel, macro and micro time -- and the header tags as an editable table. Edited headers save into a new PTU file, the only container that keeps arbitrary tags, with the photons copied unchanged.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_header_edit` |
| Menu path | File → Data → **TTTR Inspector** |
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
