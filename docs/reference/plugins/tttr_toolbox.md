---
type: Plugin Reference
title: TTTR Tools
description: 'Unified TTTR toolbox: ALEX Creator, Micro-time Shifter, TTTR Header Editor and Split/Convert.'
resource: chisurf/plugins/tttr/tttr_toolbox/
tags: [reference, plugins, tttr-toolbox, tools, tttr]
anchor: plugin-tttr_toolbox
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_toolbox)=
# TTTR Tools

Unified TTTR toolbox: ALEX Creator, Micro-time Shifter, TTTR Header Editor and Split/Convert.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_toolbox` |
| Menu path | Tools → **TTTR Tools** |
| Categories | Tools, TTTR |
| Version | 1.0.0 |
| Surfaces | gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md), [Working with timestamps and bursts (the data model)](/guides/33_timestamps_and_bursts.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_toolbox/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_toolbox/manifest.json`
