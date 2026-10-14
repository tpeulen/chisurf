---
type: Plugin Reference
title: FCS
description: 'The FCS workflow in one window: the correlator (detector → files → filter → correlate → merge) and the FCS tools — 2D-FLCS, Lifetime-FCS Sim, burst-wise FCS, the diffusion/volume and fFCS filter calculators and the channel presets — behind one navigation rail.'
resource: chisurf/plugins/fcs/fcs_toolbox/
tags: [reference, plugins, fcs-toolbox, spectroscopy, correlation]
anchor: plugin-fcs_toolbox
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-fcs_toolbox)=
# FCS

The FCS workflow in one window: the correlator (detector → files → filter → correlate → merge) and the FCS tools — 2D-FLCS, Lifetime-FCS Sim, burst-wise FCS, the diffusion/volume and fFCS filter calculators and the channel presets — behind one navigation rail.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `fcs_toolbox` |
| Menu path | Spectroscopy → Correlation → **FCS** |
| Categories | Spectroscopy, Correlation |
| Version | 1.0.0 |
| Surfaces | emtk, script |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [FCS: the correlation curve and its models](/concepts/fcs_correlation.md)
- **Workflow** — [FCS toolbox: from photon stream to a curve worth fitting](/guides/75_fcs_toolbox.md)

## Source

- Plugin package: `chisurf/plugins/fcs/fcs_toolbox/`
- Manifest: {src}`chisurf/plugins/fcs/fcs_toolbox/manifest.json`
