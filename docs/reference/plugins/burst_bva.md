(plugin-burst_bva)=
# BVA

Burst Variance Analysis for single-molecule FRET experiments.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_bva` |
| Menu path | Spectroscopy → Single-Molecule → **BVA** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 2.1.0 |
| Surfaces | cli, gui, services |
| State namespace | `burst_bva` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_bva.jobs.compute` | yes | Run Burst Variance Analysis over burst data. |
| `burst_bva.workflow.prepare` | no | Resolve BVA settings and folders from workflow context. |
| `burst_bva.contract.describe` | no | Return the BVA workflow contract. |

## Source

- Plugin package: `chisurf/plugins/burst/burst_bva/`
- Manifest: `chisurf/plugins/burst/burst_bva/manifest.json`
