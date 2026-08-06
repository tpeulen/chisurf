---
type: Plugin Reference
title: FCS-Merger
description: Merge / average multiple FCS correlation curves to improve signal-to-noise.
resource: chisurf/plugins/fcs/fcs_merger/
tags: [reference, plugins, fcs-merger, spectroscopy, fluorescence-correlation-spectroscopy]
anchor: plugin-fcs_merger
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_merger)=
# FCS-Merger

Merge / average multiple FCS correlation curves to improve signal-to-noise.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_merger` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **FCS-Merger** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `fcs_merger` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fcs_merger.merge_folder` | no | Parse, average and optionally save the correlations in a folder. |
| `fcs_merger.average` | no | Weighted-average a list of correlation dicts. |
| `fcs_merger.parse_folder` | no | Load .cor / .json.gz correlation chunks from a folder. |

## Theory and workflow

- **Theory** — [FCS: the correlation curve and its models](/concepts/fcs_correlation.md)
- **Workflow** — [Combining measurements / technical repeats](/guides/35_combining_repeats.md)

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_merger/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_merger/manifest.json`
