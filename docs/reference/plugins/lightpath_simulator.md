(plugin-lightpath_simulator)=
# Light Path Simulator

Optical light path simulator to calculate crosstalk and R0 overlap integrals.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `lightpath_simulator` |
| Menu path | Spectroscopy → **Light Path Simulator** |
| Categories | Spectroscopy |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `lightpath_simulator` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

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
