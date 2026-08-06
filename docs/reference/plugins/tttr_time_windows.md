---
type: Plugin Reference
title: TTTR→Time-Window BIDs
description: Split TTTR files into fixed-duration time-window BID (.bst) files.
resource: chisurf/plugins/tttr/tttr_time_windows/
tags: [reference, plugins, tttr-time-windows, tools, converter]
anchor: plugin-tttr_time_windows
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_time_windows)=
# TTTR→Time-Window BIDs

Split TTTR files into fixed-duration time-window BID (.bst) files.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_time_windows` |
| Menu path | Tools → Converter → **TTTR→Time-Window BIDs** |
| Categories | Tools, Converter |
| Version | 2.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `tttr_time_windows` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `tttr_time_windows.jobs.analyze_files` | yes | Split TTTR files into fixed-duration time-window BIDs. |
| `tttr_time_windows.contract.describe` | no | Return the Time Window Bins workflow contract. |

## Theory and workflow

- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_time_windows/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_time_windows/manifest.json`
