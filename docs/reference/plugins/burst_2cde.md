(plugin-burst_2cde)=
# 2CDE

FRET-2CDE / ALEX-2CDE per-burst dynamics feature (Tomov et al. 2012).

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_2cde` |
| Menu path | Spectroscopy → Single-Molecule → **2CDE** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `burst_2cde` |

## Parameters

This plugin builds its interface from custom Qt widgets (no declarative `*.view.json` parameter sections were found). Its controls are shown in the plugin's guide; the fit/model parameters it edits are defined in the [parameter glossary](../parameters.md).

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_2cde.jobs.compute` | yes | Compute the FRET-2CDE / ALEX-2CDE burst feature. |
| `burst_2cde.workflow.prepare` | no | Resolve 2CDE settings and folders from a burst workflow context. |
| `burst_2cde.contract.describe` | no | Return the 2CDE workflow contract. |

## Theory and workflow

- **Theory** — [FRET-2CDE and ALEX-2CDE](/concepts/burst_2cde.md)
- **Workflow** — [FRET-2CDE / ALEX-2CDE burst dynamics](/guides/01_fret_2cde.md)

## Source

- Plugin package: `chisurf/plugins/burst/burst_2cde/`
- Manifest: {src}`chisurf/plugins/burst/burst_2cde/manifest.json`
