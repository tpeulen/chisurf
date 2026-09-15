---
type: Plugin Reference
title: FCS
description: Unified FCS plugin — a meta tool hosting the FCS workflow behind a rail. Merges the FCS Correlator workflow (detector → files → filter → correlate → merge) with the optional FCS tools (2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS, diffusion/volume calculator, fFCS filter calculator, correlation-channel presets) into a single left-navigation tool. Built on the reusable NavigationPanelTool shell. The ribbon execs this file with __name__ == "plugin".
resource: chisurf/plugins/fcs/fcs_toolbox/
tags: [reference, plugins, fcs-toolbox, spectroscopy]
anchor: plugin-fcs_toolbox
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_toolbox)=
# FCS

Unified **FCS** plugin — a meta tool hosting the FCS workflow behind a rail.  Merges the FCS *Correlator* workflow (detector → files → filter → correlate → merge) with the optional FCS tools (2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS, diffusion/volume calculator, fFCS filter calculator, correlation-channel presets) into a single left-navigation tool. Built on the reusable ``NavigationPanelTool`` shell. The ribbon execs this file with ``__name__ == "plugin"``.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_toolbox` |
| Menu path | Spectroscopy → **FCS** |
| Categories | Spectroscopy |
| Version | 1.0.0 |
| Surfaces | script |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_toolbox/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_toolbox/manifest.json`
