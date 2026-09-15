---
type: Plugin Reference
title: BID→Analysis
description: 'BID → Analysis Converter This plugin reads burst ID (BID) files containing start/stop photon indices and generates a burstwise analysis folder next to the corresponding TTTR data. Workflow per BID file: - Infer the TTTR file from the BID file name (same stem, common TTTR extensions) - Load TTTR via tttrlib - Compute burst summary using cs.core.fio.fluorescence.burst.generate_burst_dataframe - Write a BUR file to analysis/bi4_bur/<stem>.bur - Update/create analysis/Info/*.mti with total measurement time The plugin exposes a simple GUI file dialog when launched from the Plugins menu. It can also be called programmatically via convert_bid_file(pathlike).'
resource: chisurf/plugins/burst/bid_to_analysis/
tags: [reference, plugins, bid-to-analysis, tools, converter]
anchor: plugin-bid_to_analysis
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-bid_to_analysis)=
# BID→Analysis

BID → Analysis Converter  This plugin reads burst ID (BID) files containing start/stop photon indices and generates a burstwise analysis folder next to the corresponding TTTR data.  Workflow per BID file: - Infer the TTTR file from the BID file name (same stem, common TTTR extensions) - Load TTTR via tttrlib - Compute burst summary using cs.core.fio.fluorescence.burst.generate_burst_dataframe - Write a BUR file to analysis/bi4_bur/<stem>.bur - Update/create analysis/Info/*.mti with total measurement time  The plugin exposes a simple GUI file dialog when launched from the Plugins menu. It can also be called programmatically via convert_bid_file(pathlike).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `bid_to_analysis` |
| Menu path | Tools → Converter → **BID→Analysis** |
| Categories | Tools, Converter |
| Version | 1.0.0 |
| Surfaces | script |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [Exporting burst data](/guides/34_exporting_burst_data.md)

## Source

- Plugin package: `chisurf/plugins/burst/bid_to_analysis/`
- Manifest: {src}`chisurf/plugins/burst/bid_to_analysis/manifest.json`
