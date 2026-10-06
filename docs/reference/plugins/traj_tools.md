---
type: Plugin Reference
title: Traj Tools
description: Combined dockable workspace for trajectory alignment, conversion, energy calculation, FRET, joining, clash removal, rotation/translation, topology saving, and trajectory energy tools.
resource: chisurf/plugins/traj/traj_tools/
tags: [reference, plugins, traj-tools, structure, tools]
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
| Menu path | Structure → Structure → **Traj Tools** |
| Categories | Structure, Tools |
| Version | 1.0.0 |
| Surfaces | emtk, gui |
| State namespace | `traj_tools` |

## Parameters

This plugin's window is an EMTK app: its controls and tables are described in the plugin's guide, and the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Theory and workflow

- **Workflow** — [Trajectory tools: align, convert, filter, score and FRET a structure ensemble](/guides/81_trajectory_tools.md)

## Source

- Plugin package: `chisurf/plugins/traj/traj_tools/`
- Manifest: {src}`chisurf/plugins/traj/traj_tools/manifest.json`
