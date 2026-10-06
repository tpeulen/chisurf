---
type: Plugin Reference
title: ChiMOL
description: Molecular structure viewer and protein analysis plugin for ChiSurf.
resource: chisurf/plugins/chimol/
tags: [reference, plugins, chimol, structure, modelling, molecular-viewer]
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
| Menu path | Structure → Modelling → **ChiMOL** |
| Categories | Structure, Modelling, Molecular Viewer |
| Version | 0.2.0 |
| Surfaces | emtk, gui |
| State namespace | `chimol` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [The molecular viewer (ChiMOL)](/guides/44_molecular_viewer.md)

## Source

- Plugin package: `chisurf/plugins/chimol/`
- Manifest: {src}`chisurf/plugins/chimol/manifest.json`
