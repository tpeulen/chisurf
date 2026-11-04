---
type: Plugin Reference
title: ⇄ .pto
description: 'Convert between a vendor photon file (.ptu, .spc, .ht3, ...) and ChiSurf''s own .pto container, in either direction. Pick photon streams of the Datasets workspace: a vendor file is packed into a .pto beside it, a stream of a .pto unpacks the vendor file(s) it embeds back out. The source is kept and the result verified byte-for-byte before anything is ever deleted; what is written enters the workspace as children of what it came from. Packing is also offered as a one-time nag wherever a plugin loads a vendor file as the working measurement.'
resource: chisurf/plugins/core/tttr_to_pto/
tags: [reference, plugins, tttr-to-pto, file, data]
anchor: plugin-tttr_to_pto
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_to_pto)=
# ⇄ .pto

Convert between a vendor photon file (.ptu, .spc, .ht3, ...) and ChiSurf's own .pto container, in either direction. Pick photon streams of the Datasets workspace: a vendor file is packed into a .pto beside it, a stream of a .pto unpacks the vendor file(s) it embeds back out. The source is kept and the result verified byte-for-byte before anything is ever deleted; what is written enters the workspace as children of what it came from. Packing is also offered as a one-time nag wherever a plugin loads a vendor file as the working measurement.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_to_pto` |
| Menu path | File → Data → **⇄ .pto** |
| Categories | File, Data |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [File tools: operations on the container, not the measurement](/concepts/file_tools.md)
- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/core/tttr_to_pto/`
- Manifest: {src}`chisurf/plugins/core/tttr_to_pto/manifest.json`
- UI spec: {src}`chisurf/plugins/core/tttr_to_pto/gui/tttr_to_pto_emtk.view.json`
