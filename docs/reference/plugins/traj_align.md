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
| Menu path | not in the menus (opened from a hub or another tool); display name Structure → Trajectory → **Align** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | emtk |
| State namespace | `traj_align` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Atom selection | `atom_selection` | text |  |  | Comma-separated atom ids used as the reference set for the superposition. Leave empty to align on all atoms. |
| Stride | `stride` | int |  | 1 … 999999 | Read every Nth frame of the source trajectory. |

## Theory and workflow

- **Theory** — [Structure trajectories: superposition, RMSD, clashes and FRET along a trajectory](/concepts/structure_trajectories.md)
- **Workflow** — [Trajectory tools: align, convert, filter, score and FRET a structure ensemble](/guides/81_trajectory_tools.md)

## Source

- Plugin package: `chisurf/plugins/traj/traj_align/`
- Manifest: {src}`chisurf/plugins/traj/traj_align/manifest.json`
- UI spec: {src}`chisurf/plugins/traj/traj_align/align_trajectory.view.json`
