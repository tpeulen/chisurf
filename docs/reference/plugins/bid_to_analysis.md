---
type: Plugin Reference
title: BID→Analysis
description: 'Turn burst-ID files (first/last photon index per burst) into burst tables of the matching TTTR measurement: a bursts table in its .pto, or a legacy .bur + .mti, SL5 mask or HDF5 table. Scriptable as convert_bid_file(path).'
resource: chisurf/plugins/burst/bid_to_analysis/
tags: [reference, plugins, bid-to-analysis, file, data]
anchor: plugin-bid_to_analysis
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-bid_to_analysis)=
# BID→Analysis

Turn burst-ID files (first/last photon index per burst) into burst tables of the matching TTTR measurement: a bursts table in its .pto, or a legacy .bur + .mti, SL5 mask or HDF5 table. Scriptable as convert_bid_file(path).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `bid_to_analysis` |
| Menu path | File → Data → **BID→Analysis** |
| Categories | File, Data |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [File tools: operations on the container, not the measurement](/concepts/file_tools.md), [Single-molecule FRET: burst analysis (E, S, corrections)](/concepts/smfret_bursts.md)
- **Workflow** — [Exporting burst data](/guides/34_exporting_burst_data.md)

## Source

- Plugin package: `chisurf/plugins/burst/bid_to_analysis/`
- Manifest: {src}`chisurf/plugins/burst/bid_to_analysis/manifest.json`
