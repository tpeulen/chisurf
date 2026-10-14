---
type: Plugin Reference
title: FCS Converter
description: Convert correlation-curve files between the supported FCS formats from the command line (csc).
resource: chisurf/plugins/fcs/fcs_convert/
tags: [reference, plugins, fcs-convert, spectroscopy, fluorescence-correlation-spectroscopy, correlation]
anchor: plugin-fcs_convert
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_convert)=
# FCS Converter

Convert correlation-curve files between the supported FCS formats from the command line (csc).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_convert` |
| Menu path | not in the menus; display name Spectroscopy → Correlation → **FCS Converter** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy, Correlation |
| Version | 1.0.0 |
| Surfaces | cli |

## Parameters

This plugin opens no window: it is a command-line tool (`csc fcs-convert --help` lists its options).

## Theory and workflow

- **Theory** — [FCS: the correlation curve and its models](/concepts/fcs_correlation.md)
- **Workflow** — [FCS toolbox: from photon stream to a curve worth fitting](/guides/75_fcs_toolbox.md)

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_convert/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_convert/manifest.json`
