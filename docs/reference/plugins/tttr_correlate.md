---
type: Plugin Reference
title: Correlate
description: 'TTTR Correlate This plugin provides a graphical interface for calculating correlation functions from Time-Tagged Time-Resolved (TTTR) data. Features: - Support for various correlation types (auto, cross) - Configurable correlation parameters - Interactive visualization of correlation curves - Export of correlation results The correlator is essential for analyzing dynamic processes in fluorescence correlation spectroscopy (FCS) and related techniques.'
resource: chisurf/plugins/tttr/tttr_correlate/
tags: [reference, plugins, tttr-correlate, tttr]
anchor: plugin-tttr_correlate
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-tttr_correlate)=
# Correlate

TTTR Correlate  This plugin provides a graphical interface for calculating correlation functions from Time-Tagged Time-Resolved (TTTR) data.  Features: - Support for various correlation types (auto, cross) - Configurable correlation parameters - Interactive visualization of correlation curves - Export of correlation results  The correlator is essential for analyzing dynamic processes in fluorescence correlation spectroscopy (FCS) and related techniques.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `tttr_correlate` |
| Menu path | TTTR → **Correlate** |
| Categories | TTTR |
| Version | 1.0.0 |
| Surfaces | script |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/tttr/tttr_correlate/`
- Manifest: {src}`chisurf/plugins/tttr/tttr_correlate/manifest.json`
