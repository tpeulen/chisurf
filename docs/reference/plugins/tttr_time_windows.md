---
type: Plugin Reference
title: TTTR→Time-Window BIDs
description: Split TTTR files into fixed-duration time-window BID (.bst) files.
resource: chisurf/plugins/tttr/tttr_time_windows/
tags: [reference, plugins, tttr-time-windows, file, data]
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
| Menu path | File → Data → **TTTR→Time-Window BIDs** |
| Categories | File, Data |
| Version | 2.0.0 |
| Surfaces | cli, emtk, services |
| State namespace | `tttr_time_windows` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `tttr_time_windows.jobs.analyze_files` | yes | Split TTTR files into fixed-duration time-window BIDs. |
| `tttr_time_windows.contract.describe` | no | Return the Time Window Bins workflow contract. |

## Theory and workflow

- **Theory** — [File tools: operations on the container, not the measurement](/concepts/file_tools.md)
- **Workflow** — [Handling TTTR files (and Photon-HDF5)](/guides/12_handling_tttr_files.md)

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_time_windows/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_time_windows/manifest.json`
- UI spec: {src}`chisurf/plugins/tttr/tttr_time_windows/gui/window.view.json`
