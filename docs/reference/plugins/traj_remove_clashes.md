(plugin-traj_remove_clashes)=
# Remove Clashed

Remove frames containing steric clashes from trajectories.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_remove_clashes` |
| Menu path | Structure → Trajectory → **Remove Clashed** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `traj_remove_clashes` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Atom selection | `atom_selection` | text |  |  | mdtraj atom-selection expression. The listed atoms' pairwise distances are tested; a frame is dropped when any pair is closer than the minimum distance. |
| Stride | `stride` | int |  | 1 … 999999 | Read every Nth frame of the source trajectory. |
| Min distance | `min_distance` | float |  | 0.0 … 100.0 (step 0.1) | Minimum allowed atom-atom distance (shown in Ångström). Frames with any selected atom pair closer than this (after a /10 conversion to the trajectory length unit) are removed. |

## Source

- Plugin package: `chisurf/plugins/traj/traj_remove_clashes/`
- Manifest: `chisurf/plugins/traj/traj_remove_clashes/manifest.json`
- UI spec: `chisurf/plugins/traj/traj_remove_clashes/remove_clashes.view.json`
