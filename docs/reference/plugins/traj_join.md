(plugin-traj_join)=
# Join

Join or stack molecular dynamics trajectories.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_join` |
| Menu path | Structure → Trajectory → **Join** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `traj_join` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Join mode | `join_mode` | choice |  | choices: time, atoms | By time joins the trajectories along the frame axis (same topology, frames appended). By atoms stacks the trajectories along the atom axis (same number of frames, topologies merged). |
| Reverse trajectory 1 | `reverse_traj_1` | bool |  |  | Reverse each read chunk of trajectory 1 in time before joining. |
| Reverse trajectory 2 | `reverse_traj_2` | bool |  |  | Reverse each read chunk of trajectory 2 in time before joining. |
| Chunk size | `chunk_size` | int |  | 1 … 9999999 | Trajectories are read piecewise to save memory; the chunk size sets the number of frames per read. |

## Source

- Plugin package: `chisurf/plugins/traj/traj_join/`
- Manifest: `chisurf/plugins/traj/traj_join/manifest.json`
- UI spec: `chisurf/plugins/traj/traj_join/join_trajectories.view.json`
