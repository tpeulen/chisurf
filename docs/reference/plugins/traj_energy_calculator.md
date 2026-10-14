---
type: Plugin Reference
title: Energy Calculator
description: Calculate potential energy components for structures and trajectories.
resource: chisurf/plugins/traj/potential_energy/
tags: [reference, plugins, traj-energy-calculator, structure, trajectory]
anchor: plugin-traj_energy_calculator
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-traj_energy_calculator)=
# Energy Calculator

Calculate potential energy components for structures and trajectories.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_energy_calculator` |
| Menu path | not in the menus (opened from a hub or another tool); display name Structure → Trajectory → **Energy Calculator** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | emtk |
| State namespace | `potential_energy` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Stride | `stride` | int |  | 1 … 9999 | Only every Nth frame is scored; also seeds the emitted frame numbers. |

## Theory and workflow

- **Theory** — [Structure trajectories: superposition, RMSD, clashes and FRET along a trajectory](/concepts/structure_trajectories.md)
- **Workflow** — [Trajectory tools: align, convert, filter, score and FRET a structure ensemble](/guides/81_trajectory_tools.md)

## Source

- Plugin package: `chisurf/plugins/traj/potential_energy/`
- Manifest: {src}`chisurf/plugins/traj/potential_energy/manifest.json`
- UI spec: {src}`chisurf/plugins/traj/potential_energy/calculate_potential.view.json`
