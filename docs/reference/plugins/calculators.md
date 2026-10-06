---
type: Plugin Reference
title: Calculators
description: Hub that groups ChiSurf's FRET-line, FRET/homoFRET, FCS and phasor-plot calculators and embeds the selected one in a two-panel view.
resource: chisurf/plugins/calculator/hub/
tags: [reference, plugins, calculators, tools]
anchor: plugin-calculators
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-calculators)=
# Calculators

Hub that groups ChiSurf's FRET-line, FRET/homoFRET, FCS and phasor-plot calculators and embeds the selected one in a two-panel view.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `calculators` |
| Menu path | Tools → Calculators → **Calculators** |
| Categories | Tools, Calculators |
| Version | 1.0.0 |
| Surfaces | emtk, gui |
| State namespace | `calculators` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/calculator/hub/`
- Manifest: {src}`chisurf/plugins/calculator/hub/manifest.json`
