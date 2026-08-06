---
type: Plugin Reference
title: Align
description: Align molecular dynamics trajectories to a reference frame or structure.
resource: chisurf/plugins/traj/traj_align/
tags: [reference, plugins, traj-align, structure, trajectory]
anchor: plugin-traj_align
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-traj_align)=
# Align

Align molecular dynamics trajectories to a reference frame or structure.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_align` |
| Menu path | Structure → Trajectory → **Align** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `traj_align` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Atom selection | `atom_selection` | text |  |  | Comma-separated atom ids used as the reference set for the superposition. Leave empty to align on all atoms. |
| Stride | `stride` | int |  | 1 … 999999 | Read every Nth frame of the source trajectory. |

## Source

- Plugin package: `chisurf/plugins/traj/traj_align/`
- Manifest: {src}`chisurf/plugins/traj/traj_align/manifest.json`
- UI spec: {src}`chisurf/plugins/traj/traj_align/align_trajectory.view.json`
