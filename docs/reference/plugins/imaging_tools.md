---
type: Plugin Reference
title: Image Tools
description: 'Unified imaging toolbox: Image Browser, Drift Correction, FRC Resolution, Flow Maps, Particle Tracking, Colocalization, the per-pixel maps, CLSM Draw, Region MLE, PSF Determination, CLSM Generator.'
resource: chisurf/plugins/microscopy/imaging_tools/
tags: [reference, plugins, imaging-tools, imaging]
anchor: plugin-imaging_tools
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-imaging_tools)=
# Image Tools

Unified imaging toolbox: Image Browser, Drift Correction, FRC Resolution, Flow Maps, Particle Tracking, Colocalization, the per-pixel maps, CLSM Draw, Region MLE, PSF Determination, CLSM Generator.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `imaging_tools` |
| Menu path | Imaging → **Image Tools** |
| Categories | Imaging |
| Version | 1.0.0 |
| Surfaces | emtk, gui |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Regions and their properties](/concepts/region_properties.md)
- **Workflow** — [Regions: selecting pixels, measuring what you selected](/guides/48_regions.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/imaging_tools/`
- Manifest: {src}`chisurf/plugins/microscopy/imaging_tools/manifest.json`
