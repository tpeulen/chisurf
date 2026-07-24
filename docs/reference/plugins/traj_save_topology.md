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
| Surfaces | gui |
| State namespace | `traj_save_topology` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## Source

- Plugin package: `chisurf/plugins/traj/traj_save_topology/`
- Manifest: `chisurf/plugins/traj/traj_save_topology/manifest.json`
- UI spec: `chisurf/plugins/traj/traj_save_topology/save_topology.view.json`
