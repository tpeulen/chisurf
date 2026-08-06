---
type: Plugin Reference
title: Rotate/Translate
description: Apply rigid-body rotation and translation to trajectories.
resource: chisurf/plugins/traj/traj_rotate_translate/
tags: [reference, plugins, traj-rotate-translate, structure, trajectory]
anchor: plugin-traj_rotate_translate
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-traj_rotate_translate)=
# Rotate/Translate

Apply rigid-body rotation and translation to trajectories.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_rotate_translate` |
| Menu path | Structure → Trajectory → **Rotate/Translate** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `traj_rotate_translate` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Stride | `stride` | int |  | 1 … 999999 | Read every Nth frame of the source trajectory. |

## Source

- Plugin package: `chisurf/plugins/traj/traj_rotate_translate/`
- Manifest: {src}`chisurf/plugins/traj/traj_rotate_translate/manifest.json`
- UI spec: {src}`chisurf/plugins/traj/traj_rotate_translate/rotate_translate.view.json`
