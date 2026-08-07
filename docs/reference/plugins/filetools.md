---
type: Plugin Reference
title: File tools
description: 'Everything that acts on a file rather than on the physics inside it: TTTR split/convert, packing and unpacking a.pto container, reading one back, time-window BIDs, BID→Analysis, and the TTTR header editor.'
resource: chisurf/plugins/tttr/filetools/
tags: [reference, plugins, filetools, tools]
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
| Menu path | Tools → **File tools** |
| Categories | Tools |
| Version | 1.1.0 |
| Surfaces | gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/tttr/filetools/`
- Manifest: {src}`chisurf/plugins/tttr/filetools/manifest.json`
