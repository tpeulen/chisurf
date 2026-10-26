---
type: Plugin Reference
title: ChiMOL
description: Molecular structure viewer and protein analysis plugin for ChiSurf; its labelling editor builds fps.json plans (Tools > Labelling), and its RPC checks plans and fetches structures headlessly.
resource: chisurf/plugins/chimol/
tags: [reference, plugins, chimol, structure, modelling, molecular-viewer]
anchor: plugin-chimol
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-chimol)=
# ChiMOL

Molecular structure viewer and protein analysis plugin for ChiSurf; its labelling editor builds fps.json plans (Tools > Labelling), and its RPC checks plans and fetches structures headlessly.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `chimol` |
| Menu path | Structure → Modelling → **ChiMOL** |
| Categories | Structure, Modelling, Molecular Viewer |
| Version | 0.2.0 |
| Surfaces | emtk, services |
| State namespace | `chimol` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `chimol.fps.validate` | no | Check an fps.json payload's sections and references; errors, warnings and a summary. |
| `chimol.fps.summarize` | no | Summarize positions, distances, score sets and unresolved references of an fps.json payload. |
| `chimol.fps.normalize` | no | Return an fps.json payload in canonical form. |
| `chimol.pdb.fetch` | no | Download a structure from RCSB by its four-character PDB ID. |
| `chimol.av.mrc.save` | no | Write accessible-volume points as an MRC density map. |

## Theory and workflow

- **Theory** — [Molecular surfaces and solvent accessibility](/concepts/molecular_surfaces.md), [ChiMOL: why the analysis session has its own molecular viewer](/concepts/molecular_viewer.md)
- **Workflow** — [Accessible-volume (AV) calculations](/guides/23_accessible_volume.md), [The molecular viewer (ChiMOL)](/guides/44_molecular_viewer.md)

## Source

- Plugin package: `chisurf/plugins/chimol/`
- Manifest: {src}`chisurf/plugins/chimol/manifest.json`
- UI spec: {src}`chisurf/plugins/chimol/window.view.json`
