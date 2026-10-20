---
type: Plugin Reference
title: Image Tools
description: 'The imaging pipeline: the steps that share one detector setup, photon source, imaging HDF5 and IRF & BG calibration -- Setup, Image Browser, FRC Resolution, Flow Maps, Colocalization, the numbered per-pixel maps (Intensity, Number & Brightness, Mean Micro-Time, IRF & BG, Phasor-FLIM, Pixel-wise MLE), CLSM Draw, Spot Finder and Region MLE.'
resource: chisurf/plugins/microscopy/imaging_tools/
tags: [reference, plugins, imaging-tools, spectroscopy, imaging]
anchor: plugin-imaging_tools
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-imaging_tools)=
# Image Tools

The imaging pipeline: the steps that share one detector setup, photon source, imaging HDF5 and IRF & BG calibration -- Setup, Image Browser, FRC Resolution, Flow Maps, Colocalization, the numbered per-pixel maps (Intensity, Number & Brightness, Mean Micro-Time, IRF & BG, Phasor-FLIM, Pixel-wise MLE), CLSM Draw, Spot Finder and Region MLE.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `imaging_tools` |
| Menu path | Spectroscopy → Imaging → **Image Tools** |
| Categories | Spectroscopy, Imaging |
| Version | 1.0.0 |
| Surfaces | emtk |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Regions and their properties](/concepts/region_properties.md)
- **Workflow** — [Regions: selecting pixels, measuring what you selected](/guides/48_regions.md)

## Source

- Plugin package: `chisurf/plugins/microscopy/imaging_tools/`
- Manifest: {src}`chisurf/plugins/microscopy/imaging_tools/manifest.json`
- UI spec: {src}`chisurf/plugins/microscopy/imaging_tools/gui/app.view.json`
