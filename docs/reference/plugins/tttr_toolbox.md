---
type: Plugin Reference
title: TTTR Tools
description: 'Photon-level TTTR toolbox: ALEX Creator, Micro-time Shifter, Photon Table, Count Rate Analysis and Audifier. File-level operations live in File tools.'
resource: chisurf/plugins/tttr/tttr_toolbox/
tags: [reference, plugins, tttr-toolbox, tools, photon-data, tttr]
anchor: plugin-tttr_toolbox
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_toolbox)=
# TTTR Tools

Photon-level TTTR toolbox: ALEX Creator, Micro-time Shifter, Photon Table, Count Rate Analysis and Audifier. File-level operations live in File tools.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_toolbox` |
| Menu path | Tools → Photon data → **TTTR Tools** |
| Categories | Tools, Photon data, TTTR |
| Version | 1.0.0 |
| Surfaces | emtk, gui |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md), [Working with timestamps and bursts (the data model)](/guides/33_timestamps_and_bursts.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_toolbox/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_toolbox/manifest.json`
