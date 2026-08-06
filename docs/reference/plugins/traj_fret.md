---
type: Plugin Reference
title: FRET
description: Calculate FRET observables from molecular dynamics trajectories.
resource: chisurf/plugins/traj/fret_trajectory/
tags: [reference, plugins, traj-fret, structure, trajectory, fret]
anchor: plugin-traj_fret
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-traj_fret)=
# FRET

Calculate FRET observables from molecular dynamics trajectories.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_fret` |
| Menu path | Structure → Trajectory → **FRET** |
| Categories | Structure, Trajectory, FRET |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `fret_trajectory` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Reference

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Stride | `stride` | int |  | 1 … 99999 | Read every Nth frame of the source trajectory. |

### Parameters

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| R0 [Ang] | `forster_radius` | float |  | 0.0 … 9999.0 | Foerster radius of the donor-acceptor dye pair, in Angstrom. |
| tau0 [ns] | `tau0` | float |  | 0.0 … 1000.0 (step 0.1) | Fluorescence lifetime of the donor in the absence of FRET, in nanoseconds. |
| t-step [ns] | `t_step` | float |  | 0.0 … 100000.0 (step 0.1) | Time between successive trajectory frames, in nanoseconds. |
| Dipole (kappa2) | `dipoles` | bool |  |  | If enabled, uses two atoms per fluorophore and computes the orientation factor kappa2 per frame; otherwise only the first atom of each dye defines the distance and the fixed isotropic kappa2 = 2/3 is used. |

## Source

- Plugin package: `chisurf/plugins/traj/fret_trajectory/`
- Manifest: {src}`chisurf/plugins/traj/fret_trajectory/manifest.json`
- UI spec: {src}`chisurf/plugins/traj/fret_trajectory/structure2transfer.view.json`
