---
type: Plugin Reference
title: Generate Decay
description: 'TTTR Histogram (Generate Decay) This plugin provides a graphical interface for generating fluorescence decay histograms from Time-Tagged Time-Resolved (TTTR) data. Features: - Configurable histogram parameters (binning, time range) - Channel selection for multi-channel TTTR data - Interactive visualization of decay curves - Export of histogram data for further analysis The histogram generator is useful for time-resolved fluorescence spectroscopy and lifetime analysis.'
resource: chisurf/plugins/tttr/tttr_histogram/
tags: [reference, plugins, tttr-histogram, tttr]
anchor: plugin-tttr_histogram
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_histogram)=
# Generate Decay

TTTR Histogram (Generate Decay)  This plugin provides a graphical interface for generating fluorescence decay histograms from Time-Tagged Time-Resolved (TTTR) data.  Features: - Configurable histogram parameters (binning, time range) - Channel selection for multi-channel TTTR data - Interactive visualization of decay curves - Export of histogram data for further analysis  The histogram generator is useful for time-resolved fluorescence spectroscopy and lifetime analysis.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_histogram` |
| Menu path | TTTR → **Generate Decay** |
| Categories | TTTR |
| Version | 1.0.0 |
| Surfaces | script |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_histogram/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_histogram/manifest.json`
