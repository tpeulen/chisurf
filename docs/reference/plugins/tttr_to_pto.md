---
type: Plugin Reference
title: ⇄ .pto
description: Convert between a vendor photon file (.ptu, .spc, .ht3, ...) and ChiSurf's own .pto container, in either direction. Drop a vendor file to pack it into a .pto beside it; drop a .pto to unpack the vendor file(s) it embeds back out. Whichever direction, the dropped file is kept and the result is verified byte-for-byte before anything is ever deleted. Packing is also offered as a one-time nag wherever a plugin drops a vendor file to load it as the working measurement.
resource: chisurf/plugins/core/tttr_to_pto/
tags: [reference, plugins, tttr-to-pto, tttr]
anchor: plugin-tttr_to_pto
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_to_pto)=
# ⇄ .pto

Convert between a vendor photon file (.ptu, .spc, .ht3, ...) and ChiSurf's own .pto container, in either direction. Drop a vendor file to pack it into a .pto beside it; drop a .pto to unpack the vendor file(s) it embeds back out. Whichever direction, the dropped file is kept and the result is verified byte-for-byte before anything is ever deleted. Packing is also offered as a one-time nag wherever a plugin drops a vendor file to load it as the working measurement.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_to_pto` |
| Menu path | TTTR → **⇄ .pto** |
| Categories | TTTR |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/core/tttr_to_pto/`
- Manifest: {src}`chisurf/plugins/core/tttr_to_pto/manifest.json`
