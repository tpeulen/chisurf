---
type: Plugin Reference
title: ChiMOL
description: Molecular structure viewer and protein analysis plugin for ChiSurf.
resource: chisurf/plugins/chimol/
tags: [reference, plugins, chimol, structure, molecular-viewer]
anchor: plugin-chimol
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-chimol)=
# ChiMOL

Molecular structure viewer and protein analysis plugin for ChiSurf.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `chimol` |
| Menu path | Structure → Structure → **ChiMOL** |
| Categories | Structure, Molecular Viewer |
| Version | 0.2.0 |
| Surfaces | gui |
| State namespace | `chimol` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Contour levels | `levels` | level_histogram |  |  | The map's value distribution, with each contour as a marker on it. Drag a marker to move that level, click empty histogram to add one, right-click a marker to remove it. |

## Theory and workflow

- **Workflow** — [The molecular viewer (ChiMOL)](/guides/44_molecular_viewer.md)

## Source

- Plugin package: `chisurf/plugins/chimol/`
- Manifest: {src}`chisurf/plugins/chimol/manifest.json`
- UI spec: {src}`chisurf/plugins/chimol/chimol/app/volume.view.json`
