---
type: Plugin Reference
title: Traj Tools
description: Combined dockable workspace for trajectory alignment, conversion, energy calculation, FRET, joining, clash removal, rotation/translation, topology saving, and trajectory energy tools.
resource: chisurf/plugins/traj/traj_tools/
tags: [reference, plugins, traj-tools, structure, trajectory, tools]
anchor: plugin-traj_tools
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-traj_tools)=
# Traj Tools

Combined dockable workspace for trajectory alignment, conversion, energy calculation, FRET, joining, clash removal, rotation/translation, topology saving, and trajectory energy tools.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_tools` |
| Menu path | Structure → Trajectory → **Traj Tools** |
| Categories | Structure, Trajectory, Tools |
| Version | 1.0.0 |
| Surfaces | emtk |
| State namespace | `traj_tools` |

## Parameters

This plugin's window is an EMTK app without declarative parameter sections: its controls are described in the plugin's guide. Any fit/model parameter it edits is defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Theory** — [Structure trajectories: superposition, RMSD, clashes and FRET along a trajectory](/concepts/structure_trajectories.md)
- **Workflow** — [Trajectory tools: align, convert, filter, score and FRET a structure ensemble](/guides/81_trajectory_tools.md)

## Source

- Plugin package: `chisurf/plugins/traj/traj_tools/`
- Manifest: {src}`chisurf/plugins/traj/traj_tools/manifest.json`
