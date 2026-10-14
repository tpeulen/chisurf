---
type: Plugin Reference
title: 2CDE
description: FRET-2CDE / ALEX-2CDE per-burst dynamics feature (Tomov et al. 2012).
resource: chisurf/plugins/burst/burst_2cde/
tags: [reference, plugins, burst-2cde, spectroscopy, single-molecule]
anchor: plugin-burst_2cde
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-burst_2cde)=
# 2CDE

FRET-2CDE / ALEX-2CDE per-burst dynamics feature (Tomov et al. 2012).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_2cde` |
| Menu path | not in the menus (opened from a hub or another tool); display name Spectroscopy → Single-Molecule → **2CDE** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | cli, emtk, services |
| State namespace | `burst_2cde` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_2cde.jobs.compute` | yes | Compute the FRET-2CDE / ALEX-2CDE burst feature. |
| `burst_2cde.workflow.prepare` | no | Resolve 2CDE settings and folders from a burst workflow context. |
| `burst_2cde.contract.describe` | no | Return the 2CDE workflow contract. |

## Theory and workflow

- **Theory** — [FRET-2CDE and ALEX-2CDE](/concepts/burst_2cde.md)
- **Workflow** — [FRET-2CDE / ALEX-2CDE burst dynamics](/guides/01_fret_2cde.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_2cde/`
- Manifest: {src}`chisurf/plugins/burst/burst_2cde/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/burst_2cde/gui/window.view.json`
