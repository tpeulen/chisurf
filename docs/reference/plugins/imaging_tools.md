---
type: Plugin Reference
title: Image Tools
description: 'Unified imaging toolbox: Image Browser, Drift Correction, CLSM Draw, Molecule-wise MLE, Pixel-wise MLE, PSF Determination.'
resource: chisurf/plugins/microscopy/imaging_tools/
tags: [reference, plugins, imaging-tools, spectroscopy]
anchor: plugin-imaging_tools
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-imaging_tools)=
# Image Tools

Unified imaging toolbox: Image Browser, Drift Correction, CLSM Draw, Molecule-wise MLE, Pixel-wise MLE, PSF Determination.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `imaging_tools` |
| Menu path | Spectroscopy → **Image Tools** |
| Categories | Spectroscopy |
| Version | 1.0.0 |
| Surfaces | emtk, gui |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Native window (emtk)

The default window is drawn with emtk (`gui/app.py`): the tools are the accepted native apps of their plugins, built from their manifests on first use.

| Area | Controls |
| --- | --- |
| List | **Search**, the 16 tools in the Qt order (Setup, Browser, Drift, Resolution, Flow, Tracking, 1. Intensity to 6. Pixel-wise MLE, a rule, CLSM Draw, Spot Finder, Region MLE, PSF Determination); the arrow keys step the list |
| Stepper | **Back**, **Next**, **Run all** / **Stop** (the numbered steps, each after the previous has finished), status line |
| Header | the open tool's name and description, the shared **Source** and **HDF5** |
| Shared | detector setup, photon source, imaging HDF5 and IRF / background calibration, applied to every opened tool; settings of every opened tool are remembered |
| Help | **Help**, **Guide** |

## Theory and workflow

- **Guide** — [The imaging workflow in one window](/guides/98_imaging_tools.md)
- **Theory** — [Regions and their properties](/concepts/region_properties.md)
- **Workflow** — [Regions: selecting pixels, measuring what you selected](/guides/48_regions.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/imaging_tools/`
- Manifest: {src}`chisurf/plugins/microscopy/imaging_tools/manifest.json`
