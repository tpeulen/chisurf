---
type: Plugin Reference
title: Microtime Shifter
description: Apply global and per-channel micro-time shifts to TTTR files.
resource: chisurf/plugins/tttr/tttr_microtime_shifter/
tags: [reference, plugins, microtime-shifter, tools, tttr, editor]
anchor: plugin-microtime_shifter
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-microtime_shifter)=
# Microtime Shifter

Apply global and per-channel micro-time shifts to TTTR files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `microtime_shifter` |
| Menu path | Tools → TTTR → **Microtime Shifter** |
| Categories | Tools, TTTR, Editor |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `microtime_shifter` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `microtime_shift.apply` | no | Apply micro-time shifts to TTTR files. |
| `microtime_shift.load_metadata` | no | Return routing channels and n_mt for a file. |
| `microtime_shift.identify` | no | Look up a file in the MMFDB object store. |
| `microtime_shift.contract.describe` | no | Return the Micro-time Shifter workflow contract. |

## Theory and workflow

- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_microtime_shifter/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_microtime_shifter/manifest.json`
