(plugin-traj_energy_calculator)=
# Energy Calculator

Calculate potential energy components for structures and trajectories.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `traj_energy_calculator` |
| Menu path | Structure → Trajectory → **Energy Calculator** |
| Categories | Structure, Trajectory |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `potential_energy` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Stride | `stride` | int |  | 1 … 9999 | Only every Nth frame is scored; also seeds the emitted frame numbers. |

## Source

- Plugin package: `chisurf/plugins/traj/potential_energy/`
- Manifest: `chisurf/plugins/traj/potential_energy/manifest.json`
- UI spec: `chisurf/plugins/traj/potential_energy/calculate_potential.view.json`
