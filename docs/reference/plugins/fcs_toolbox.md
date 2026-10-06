---
type: Plugin Reference
title: FCS
description: Unified FCS plugin — a meta tool hosting the FCS workflow behind a rail. Merges the FCS Correlator workflow (detector → files → filter → correlate → merge) with the optional FCS tools (2D-FLCS, Lifetime-FCS Sim, Burst-wise FCS, diffusion/volume calculator, fFCS filter calculator, correlation-channel presets) into a single left-navigation tool. Built on the reusable NavigationPanelTool shell. The ribbon execs this file with __name__ == "plugin".
resource: chisurf/plugins/fcs/fcs_toolbox/
tags: [reference, plugins, fcs-toolbox, spectroscopy, correlation]
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
| Menu path | Spectroscopy → Correlation → **FCS** |
| Categories | Spectroscopy, Correlation |
| Version | 1.0.0 |
| Surfaces | emtk, gui, script |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [FCS toolbox: from photon stream to a curve worth fitting](/guides/75_fcs_toolbox.md)

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_toolbox/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_toolbox/manifest.json`
