---
type: Plugin Reference
title: Trajectory Energy
description: Calculate and analyze trajectory energy time series.
resource: chisurf/plugins/traj/traj_energy/
tags: [reference, plugins, traj-energy, structure, trajectory]
anchor: plugin-traj_energy
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-traj_energy)=
# Trajectory Energy

Calculate and analyze trajectory energy time series.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_energy` |
| Menu path | Structure → Trajectory → **Trajectory Energy** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `traj_energy` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/traj/traj_energy/`
- Manifest: {src}`chisurf/plugins/traj/traj_energy/manifest.json`
