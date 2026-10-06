---
type: Plugin Reference
title: Light Path Simulator
description: Optical light path simulator to calculate crosstalk and R0 overlap integrals.
resource: chisurf/plugins/core/lightpath_simulator/
tags: [reference, plugins, lightpath-simulator, tools, calculators]
anchor: plugin-lightpath_simulator
generator: build_tools/docs/generate_plugin_docs.py
---

(plugin-lightpath_simulator)=
# Light Path Simulator

Optical light path simulator to calculate crosstalk and R0 overlap integrals.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `lightpath_simulator` |
| Menu path | Tools → Calculators → **Light Path Simulator** |
| Categories | Tools, Calculators |
| Version | 1.0.0 |
| Surfaces | cli, emtk, gui, services |
| State namespace | `lightpath_simulator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Graph view

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Show minimap | `show_minimap` | bool |  |  | Show a small overview of the graph for navigating a large optical network. |

### Backend

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Spectra database | `db_path` | str |  |  | Path of the MMFDB spectra database; empty uses the configured database. |

### MMFDB

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Name | `operation_name` | str |  |  | Name stored with the simulation and its MMFDB artifacts when you press Save to MMFDB. |

### Connections

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| From | `source_node` | choice |  | choices: `node_options` | The node producing the optical spectrum or scalar parameter. |
| Out port | `source_port` | int |  | 0 … 99 | Zero-based output-port index on the source node. |
| To | `target_node` | choice |  | choices: `node_options` | The node that consumes the selected source output. |
| In port | `target_port` | int |  | 0 … 99 | Zero-based input-port index on the target node. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `lightpath.simulate` | no | Run a light-path simulation for a JSON graph. |
| `lightpath.save` | no | Persist a light-path graph and simulated outputs as MMFDB artifacts. |
| `lightpath.list` | no | List saved light-path simulations from MMFDB. |
| `lightpath.get` | no | Load one saved light-path simulation from MMFDB. |
| `lightpath.get_probes_info` | no | Return probe metadata used by the light-path simulator palette. |
| `lightpath.contract.describe` | no | Return the light-path simulator workflow contract. |

## Theory and workflow

- **Theory** — [Simulating single-molecule photon streams](/concepts/photophysics_simulation.md)

## Source

- Plugin package: `chisurf/plugins/core/lightpath_simulator/`
- Manifest: {src}`chisurf/plugins/core/lightpath_simulator/manifest.json`
- UI spec: {src}`chisurf/plugins/core/lightpath_simulator/gui/lightpath.view.json`
