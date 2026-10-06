---
type: Plugin Reference
title: MFD Prepare
description: 'Prepare a burst folder for multiparameter-fluorescence (MFD) analysis: resolve photon sources, verify channel counts, compute mean micro times, and inspect the preparation report.'
resource: chisurf/plugins/burst/mfd_prepare/
tags: [reference, plugins, mfd-prepare, tools, burst, mfd]
anchor: plugin-mfd_prepare
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-mfd_prepare)=
# MFD Prepare

Prepare a burst folder for multiparameter-fluorescence (MFD) analysis: resolve photon sources, verify channel counts, compute mean micro times, and inspect the preparation report.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `mfd_prepare` |
| Menu path | Tools → Burst → **MFD Prepare** |
| Categories | Tools, Burst, MFD |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `mfd_prepare` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `mfd_prepare.prepare` | yes | Prepare a burst folder for MFD analysis. |
| `mfd_prepare.describe` | no | Return the plugin contract descriptor. |

## Source

- Plugin package: `chisurf/plugins/burst/mfd_prepare/`
- Manifest: {src}`chisurf/plugins/burst/mfd_prepare/manifest.json`
- UI spec: {src}`chisurf/plugins/burst/mfd_prepare/gui/mfd_prepare.view.json`
