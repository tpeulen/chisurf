---
type: Plugin Reference
title: FCS Saturation
description: FCS Saturation Calculator for arbitrary multi-state kinetic schemes (including Cy5).
resource: chisurf/plugins/calculator/fcs_saturation_calc/
tags: [reference, plugins, fcs-saturation, spectroscopy, fluorescence-correlation-spectroscopy]
anchor: plugin-fcs_saturation
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_saturation)=
# FCS Saturation

FCS Saturation Calculator for arbitrary multi-state kinetic schemes (including Cy5).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_saturation` |
| Menu path | Spectroscopy → Fluorescence Correlation Spectroscopy → **FCS Saturation** |
| Categories | Spectroscopy, Fluorescence Correlation Spectroscopy |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `fcs_saturation.compute` | no | Compute unperturbed and saturated FCS curves for arbitrary kinetic scheme. |

## Theory and workflow

- **Theory** — [Optical saturation in FCS](/concepts/fcs_saturation.md)
- **Workflow** — [FCS saturation and focal-volume expansion](/guides/56_fcs_saturation.md)

## Source

- Plugin package: `chisurf/plugins/calculator/fcs_saturation_calc/`
- Manifest: {src}`chisurf/plugins/calculator/fcs_saturation_calc/manifest.json`
