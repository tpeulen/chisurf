---
type: Plugin Reference
title: Save Topol
description: Save topology or first-frame structure files from trajectories.
resource: chisurf/plugins/traj/traj_save_topology/
tags: [reference, plugins, traj-save-topology, structure, trajectory]
anchor: plugin-traj_save_topology
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-traj_save_topology)=
# Save Topol

Save topology or first-frame structure files from trajectories.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_save_topology` |
| Menu path | Structure → Trajectory → **Save Topol** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | emtk |
| State namespace | `traj_save_topology` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Structure trajectories: superposition, RMSD, clashes and FRET along a trajectory](/concepts/structure_trajectories.md)
- **Workflow** — [Trajectory tools: align, convert, filter, score and FRET a structure ensemble](/guides/81_trajectory_tools.md)

## Source

- Plugin package: `chisurf/plugins/traj/traj_save_topology/`
- Manifest: {src}`chisurf/plugins/traj/traj_save_topology/manifest.json`
- UI spec: {src}`chisurf/plugins/traj/traj_save_topology/save_topology.view.json`
