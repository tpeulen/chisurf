---
type: Plugin Reference
title: FCS Converter
description: FCS conversion plugin. Convert fluorescence correlation spectroscopy files between supported formats directly from the ChiSurf CLI.
resource: chisurf/plugins/fcs/fcs_convert/
tags: [reference, plugins, fcs-convert, spectroscopy, fluorescence-correlation-spectroscopy]
anchor: plugin-fcs_convert
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_convert)=
# FCS Converter

FCS conversion plugin.  Convert fluorescence correlation spectroscopy files between supported formats directly from the ChiSurf CLI.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_convert` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **FCS Converter** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.0.0 |
| Surfaces | cli |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_convert/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_convert/manifest.json`
